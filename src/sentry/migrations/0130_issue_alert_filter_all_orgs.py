# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2020-07-28 16:24
from __future__ import unicode_literals

from django.db import migrations, transaction

from sentry.utils.query import RangeQuerySetWrapperWithProgressBar

import logging

conditions_to_filters = {
    "sentry.rules.conditions.tagged_event.TaggedEventCondition": "sentry.rules.filters.tagged_event.TaggedEventFilter",
    "sentry.rules.conditions.event_attribute.EventAttributeCondition": "sentry.rules.filters.event_attribute.EventAttributeFilter",
    "sentry.rules.conditions.level.LevelCondition": "sentry.rules.filters.level.LevelFilter",
}
every_event_condition = "sentry.rules.conditions.every_event.EveryEventCondition"
filter_prefix = "sentry.rules.filters"


def get_migration_func(rule):
    data = rule.data

    conditions = data.get("conditions") or []
    has_old_conditions = False
    has_migrated_conditions = False
    for condition in conditions:
        if condition["id"] in conditions_to_filters:
            has_migrated_conditions = True
        elif not condition["id"].startswith(filter_prefix):
            has_old_conditions = True

    if data.get("action_match") == "none":
        # If the rule contains any conditions that are not migrated, then we must run a more complex
        # migration on the 'none' rules because the 'none' action match does not exist anymore.
        if has_old_conditions:
            return modify_none_rule
    elif data.get("action_match") == "any":
        # If the rule contains some conditions that are migrated and some that aren't with an 'any'
        # match then migrating the rule will cause functionality to change. We will need to split
        # these rules into two rules to maintain the same functionality.
        if has_migrated_conditions and has_old_conditions:
            return split_alert_rule

    # all other cases can be handled with a simple migration
    return simple_migrate_alert_rule


# Returns a filter version of the given condition, or the original condition
def migrate_condition(condition):
    # attempt to change the condition id to the filter version, if the condition does not need
    # to be migrated, then just keep the original id
    condition["id"] = conditions_to_filters.get(condition["id"], condition["id"])
    return condition


# Migrate the alert rule by moving certain conditions to become filters and applying the correct match
def simple_migrate_alert_rule(rule, Rule):
    data = rule.data
    action_match = data.get("action_match")
    conditions = data.get("conditions") or []

    # if a migration is necessary
    if any([condition["id"] in conditions_to_filters for condition in conditions]):
        rule.data["conditions"] = [migrate_condition(cond) for cond in conditions]
        rule.data["filter_match"] = action_match

        if action_match == "none":
            rule.data["action_match"] = "all"

        rule.save()


# In the case where the alert rule has an 'any' match with filters/conditions, we must split this rule into two
def split_alert_rule(rule, Rule):
    data = rule.data
    action_match = data.get("action_match")
    conditions = data.get("conditions") or []
    actions = data.get("actions")
    frequency = data.get("frequency")
    original_name = rule.label

    # split the conditions into a filters and triggers array
    filters = [migrate_condition(condition) for condition in conditions if condition["id"] in conditions_to_filters or condition["id"].startswith(filter_prefix)]
    triggers = [condition for condition in conditions if not (condition["id"] in conditions_to_filters or condition["id"].startswith(filter_prefix))]

    # the original rule will only have the triggers
    rule.data["conditions"] = triggers
    rule.label = original_name + " (1)"
    rule.save()

    # create a new rule with just the filters and same actions
    rule_args = {
        "data": {
            "filter_match": "any",
            "action_match": "any",
            "actions": actions,
            "conditions": filters,
            "frequency": frequency,
        },
        "label": original_name + " (2)",
        "environment_id": rule.environment_id,
        "project": rule.project,
    }
    filter_rule = Rule.objects.create(**rule_args)


# In the case where the alert rule has a 'none' match with migrated conditions, we migrate all applicable conditions and then set the match to 'any'
# this doesn't persist the functionality of the rule, but because the 'none' match doesn't exist on conditions it is the best we can do.
def modify_none_rule(rule, Rule):
    data = rule.data
    conditions = data.get("conditions") or []

    # remove the event occurs condition if it exists and migrate all conditions that should be filters
    migrated_conditions = [migrate_condition(cond) for cond in conditions if cond["id"] != every_event_condition]
    rule.data["conditions"] = migrated_conditions
    rule.data["filter_match"] = "none"

    # set the match to be 'any'
    rule.data["action_match"] = "any"
    rule.save()


def migrate_project_alert_rules(project, Rule):
    with transaction.atomic():
        rules = Rule.objects.filter(project=project, status=0)
        for rule in rules:
            migration_func = get_migration_func(rule)
            migration_func(rule, Rule)
            project.flags.has_alert_filters = True
            project.save()


def migrate_all_orgs(apps, schema_editor):
    """
    Migrate an org's projects' rules over to conditions/filters
    and turn on issue alert filters for each.
    """
    Organization = apps.get_model("sentry", "Organization")
    Project = apps.get_model("sentry", "Project")
    Rule = apps.get_model("sentry", "Rule")

    for org in RangeQuerySetWrapperWithProgressBar(Organization.objects.filter(status=0)):
        # We migrate a project at a time, but we prefer to group by org so that for the
        # most part an org will see the changes all at once.
        for project in Project.objects.filter(organization=org, status=0):
            try:
                migrate_project_alert_rules(project, Rule)
            except Exception:
                # If a project fails we'll just log and continue. We shouldn't see any
                # failures, but if we do we can analyze them and re-run this migration,
                # since it is idempotent.
                logging.exception("Error migrating project {}".format(project.id))


class Migration(migrations.Migration):
    # This flag is used to mark that a migration shouldn't be automatically run in
    # production. We set this to True for operations that we think are risky and want
    # someone from ops to run manually and monitor.
    # General advice is that if in doubt, mark your migration as `is_dangerous`.
    # Some things you should always mark as dangerous:
    # - Large data migrations. Typically we want these to be run manually by ops so that
    #   they can be monitored. Since data migrations will now hold a transaction open
    #   this is even more important.
    # - Adding columns to highly active tables, even ones that are NULL.
    is_dangerous = True

    # This flag is used to decide whether to run this migration in a transaction or not.
    # By default we prefer to run in a transaction, but for migrations where you want
    # to `CREATE INDEX CONCURRENTLY` this needs to be set to False. Typically you'll
    # want to create an index concurrently when adding one to an existing table.
    atomic = False

    dependencies = [
        ('sentry', '0129_remove_dashboard_keys'),
    ]

    operations = [migrations.RunPython(code=migrate_all_orgs)]
