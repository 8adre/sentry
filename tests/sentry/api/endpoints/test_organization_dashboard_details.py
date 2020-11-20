from __future__ import absolute_import

import six
import pytest

from django.core.urlresolvers import reverse
from sentry.models import (
    Dashboard,
    DashboardWidget,
    DashboardWidgetQuery,
    DashboardWidgetDisplayTypes,
)
from sentry.testutils import OrganizationDashboardWidgetTestCase
from sentry.utils.compat import zip


class OrganizationDashboardDetailsTestCase(OrganizationDashboardWidgetTestCase):
    def setUp(self):
        super(OrganizationDashboardDetailsTestCase, self).setUp()
        self.widget_1 = DashboardWidget.objects.create(
            dashboard=self.dashboard,
            order=1,
            title="Widget 1",
            display_type=DashboardWidgetDisplayTypes.LINE_CHART,
        )
        self.widget_2 = DashboardWidget.objects.create(
            dashboard=self.dashboard,
            order=2,
            title="Widget 2",
            display_type=DashboardWidgetDisplayTypes.TABLE,
        )
        self.widget_1_data_1 = DashboardWidgetQuery.objects.create(
            widget=self.widget_1,
            name=self.anon_users_query["name"],
            fields=self.anon_users_query["fields"],
            conditions=self.anon_users_query["conditions"],
            interval=self.anon_users_query["interval"],
            order=1,
        )
        self.widget_1_data_2 = DashboardWidgetQuery.objects.create(
            widget=self.widget_1,
            name=self.known_users_query["name"],
            fields=self.known_users_query["fields"],
            conditions=self.known_users_query["conditions"],
            interval=self.known_users_query["interval"],
            order=2,
        )
        self.widget_2_data_1 = DashboardWidgetQuery.objects.create(
            widget=self.widget_2,
            name=self.geo_errors_query["name"],
            fields=self.geo_errors_query["fields"],
            conditions=self.geo_errors_query["conditions"],
            interval=self.geo_errors_query["interval"],
            order=1,
        )

    def url(self, dashboard_id):
        return reverse(
            "sentry-api-0-organization-dashboard-details",
            kwargs={"organization_slug": self.organization.slug, "dashboard_id": dashboard_id},
        )

    def assert_serialized_widget(self, data, expected_widget):
        if "id" in data:
            assert data["id"] == six.text_type(expected_widget.id)
        if "title" in data:
            assert data["title"] == expected_widget.title
        if "displayType" in data:
            assert data["displayType"] == DashboardWidgetDisplayTypes.get_type_name(
                expected_widget.display_type
            )

    def assert_serialized_dashboard(self, data, dashboard):
        assert data["id"] == six.text_type(dashboard.id)
        assert data["organization"] == six.text_type(dashboard.organization.id)
        assert data["title"] == dashboard.title
        assert data["createdBy"] == six.text_type(dashboard.created_by.id)

    def assert_serialized_widget_query(self, data, widget_data_source):
        if "id" in data:
            assert data["id"] == six.text_type(widget_data_source.id)
        if "name" in data:
            assert data["name"] == widget_data_source.name
        if "fields" in data:
            assert data["fields"] == widget_data_source.fields
        if "conditions" in data:
            assert data["conditions"] == widget_data_source.conditions
        if "interval" in data:
            assert data["interval"] == widget_data_source.interval


class OrganizationDashboardDetailsGetTest(OrganizationDashboardDetailsTestCase):
    def test_get(self):
        response = self.client.get(self.url(self.dashboard.id))
        assert response.status_code == 200, response.content

        self.assert_serialized_dashboard(response.data, self.dashboard)
        assert len(response.data["widgets"]) == 2
        widgets = response.data["widgets"]
        self.assert_serialized_widget(widgets[0], self.widget_1)
        self.assert_serialized_widget(widgets[1], self.widget_2)

        widget_queries = widgets[0]["queries"]
        assert len(widget_queries) == 2
        self.assert_serialized_widget_query(widget_queries[0], self.widget_1_data_1)
        self.assert_serialized_widget_query(widget_queries[1], self.widget_1_data_2)

        assert len(widgets[1]["queries"]) == 1
        self.assert_serialized_widget_query(widgets[1]["queries"][0], self.widget_2_data_1)

    def test_dashboard_does_not_exist(self):
        response = self.client.get(self.url(1234567890))
        assert response.status_code == 404
        assert response.data == {u"detail": "The requested resource does not exist"}


class OrganizationDashboardDetailsDeleteTest(OrganizationDashboardDetailsTestCase):
    def test_delete(self):
        response = self.client.delete(self.url(self.dashboard.id))
        assert response.status_code == 204

        assert self.client.get(self.url(self.dashboard.id)).status_code == 404

        assert not Dashboard.objects.filter(id=self.dashboard.id).exists()
        assert not DashboardWidget.objects.filter(id=self.widget_1.id).exists()
        assert not DashboardWidget.objects.filter(id=self.widget_2.id).exists()
        assert not DashboardWidgetQuery.objects.filter(widget_id=self.widget_1.id).exists()
        assert not DashboardWidgetQuery.objects.filter(widget_id=self.widget_2.id).exists()

    def test_dashboard_does_not_exist(self):
        response = self.client.delete(self.url(1234567890))
        assert response.status_code == 404
        assert response.data == {u"detail": "The requested resource does not exist"}


class OrganizationDashboardDetailsPutTest(OrganizationDashboardDetailsTestCase):
    def setUp(self):
        super(OrganizationDashboardDetailsPutTest, self).setUp()
        self.widget_3 = DashboardWidget.objects.create(
            dashboard=self.dashboard,
            order=3,
            title="Widget 3",
            display_type=DashboardWidgetDisplayTypes.LINE_CHART,
        )
        self.widget_4 = DashboardWidget.objects.create(
            dashboard=self.dashboard,
            order=4,
            title="Widget 4",
            display_type=DashboardWidgetDisplayTypes.LINE_CHART,
        )
        self.widget_ids = [self.widget_1.id, self.widget_2.id, self.widget_3.id, self.widget_4.id]

    def get_widgets(self, dashboard_id):
        return DashboardWidget.objects.filter(dashboard_id=dashboard_id).order_by("order")

    def get_widget_queries(self, widget):
        return DashboardWidgetQuery.objects.filter(widget=widget).order_by("order")

    def assert_no_changes(self):
        self.assert_dashboard_and_widgets(self.widget_ids)

    def assert_dashboard_and_widgets(self, widget_ids):
        assert Dashboard.objects.filter(
            organization=self.organization, id=self.dashboard.id
        ).exists()

        widgets = self.get_widgets(self.dashboard)
        assert len(widgets) == len(list(widget_ids))

        for widget, id in zip(widgets, widget_ids):
            assert widget.id == id

    def test_dashboard_does_not_exist(self):
        response = self.client.put(self.url(1234567890))
        assert response.status_code == 404
        assert response.data == {u"detail": u"The requested resource does not exist"}

    def test_change_dashboard_title(self):
        response = self.client.put(self.url(self.dashboard.id), data={"title": "Dashboard Hello"})
        assert response.status_code == 200, response.data
        assert Dashboard.objects.filter(
            title="Dashboard Hello", organization=self.organization, id=self.dashboard.id
        ).exists()

    def test_add_widget(self):
        data = {
            "title": "First dashboard",
            "widgets": [
                {"id": six.text_type(self.widget_1.id)},
                {"id": six.text_type(self.widget_2.id)},
                {"id": six.text_type(self.widget_3.id)},
                {"id": six.text_type(self.widget_4.id)},
                {
                    "title": "Errors over time",
                    "displayType": "line",
                    "queries": [
                        {
                            "name": "Errors",
                            "fields": ["count()"],
                            "conditions": "event.type:error",
                            "interval": "5m",
                        }
                    ],
                },
            ],
        }
        response = self.client.put(self.url(self.dashboard.id), data=data)
        assert response.status_code == 200, response.data

        widgets = self.get_widgets(self.dashboard.id)
        assert len(widgets) == 5

        last = list(widgets).pop()
        self.assert_serialized_widget(data["widgets"][4], last)

        queries = last.queries.all()
        assert len(queries) == 1
        self.assert_serialized_widget_query(data["widgets"][4]["queries"][0], queries[0])

    @pytest.mark.skip(reason="will be done in a future set of changes")
    def test_add_widget_invalid_query(self):
        pass

    @pytest.mark.skip(reason="will be done in a future set of changes")
    def test_add_widget_invalid_fields(self):
        pass

    def test_update_widget_title(self):
        data = {
            "title": "First dashboard",
            "widgets": [
                {"id": six.text_type(self.widget_1.id), "title": "New title"},
                {"id": six.text_type(self.widget_2.id)},
                {"id": six.text_type(self.widget_3.id)},
                {"id": six.text_type(self.widget_4.id)},
            ],
        }
        response = self.client.put(self.url(self.dashboard.id), data=data)
        assert response.status_code == 200

        widgets = self.get_widgets(self.dashboard.id)
        self.assert_serialized_widget(data["widgets"][0], widgets[0])

    def test_update_widget_add_query(self):
        data = {
            "title": "First dashboard",
            "widgets": [
                {
                    "id": six.text_type(self.widget_1.id),
                    "title": "New title",
                    "queries": [
                        {"id": six.text_type(self.widget_1_data_1.id)},
                        {
                            "name": "transactions",
                            "fields": ["count()"],
                            "conditions": "event.type:transaction",
                        },
                    ],
                },
                {"id": six.text_type(self.widget_2.id)},
            ],
        }
        response = self.client.put(self.url(self.dashboard.id), data=data)
        assert response.status_code == 200, response.data

        # two widgets should be removed
        widgets = self.get_widgets(self.dashboard.id)
        assert len(widgets) == 2
        self.assert_serialized_widget(data["widgets"][0], widgets[0])

        queries = self.get_widget_queries(widgets[0])
        assert len(queries) == 2
        assert data["widgets"][0]["queries"][0]["id"] == six.text_type(queries[0].id)
        self.assert_serialized_widget_query(data["widgets"][0]["queries"][1], queries[1])

    def test_update_widget_remove_and_update_query(self):
        data = {
            "title": "First dashboard",
            "widgets": [
                {
                    "id": six.text_type(self.widget_1.id),
                    "title": "New title",
                    "queries": [
                        {
                            "id": six.text_type(self.widget_1_data_1.id),
                            "name": "transactions",
                            "fields": ["count()"],
                            "conditions": "event.type:transaction",
                        },
                    ],
                },
            ],
        }
        response = self.client.put(self.url(self.dashboard.id), data=data)
        assert response.status_code == 200, response.data

        # only one widget should remain
        widgets = self.get_widgets(self.dashboard.id)
        assert len(widgets) == 1
        self.assert_serialized_widget(data["widgets"][0], widgets[0])

        queries = self.get_widget_queries(widgets[0])
        assert len(queries) == 1
        self.assert_serialized_widget_query(data["widgets"][0]["queries"][0], queries[0])

    def test_remove_widget_and_add_new(self):
        # Remove a widget from the middle of the set and put a new widget there
        data = {
            "title": "First dashboard",
            "widgets": [
                {"id": six.text_type(self.widget_1.id)},
                {"id": six.text_type(self.widget_2.id)},
                {
                    "title": "Errors over time",
                    "displayType": "line",
                    "queries": [
                        {
                            "name": "Errors",
                            "fields": ["count()"],
                            "conditions": "event.type:error",
                            "interval": "5m",
                        }
                    ],
                },
                {"id": six.text_type(self.widget_4.id)},
            ],
        }
        response = self.client.put(self.url(self.dashboard.id), data=data)
        assert response.status_code == 200, response.data

        widgets = self.get_widgets(self.dashboard.id)
        assert len(widgets) == 4
        # Check ordering
        assert self.widget_1.id == widgets[0].id
        assert self.widget_2.id == widgets[1].id
        self.assert_serialized_widget(data["widgets"][2], widgets[2])
        assert self.widget_4.id == widgets[3].id

    @pytest.mark.skip(reason="not done yet")
    def test_update_widget_invalid_query(self):
        pass

    @pytest.mark.skip(reason="not done yet")
    def test_update_widget_invalid_fields(self):
        pass

    def test_remove_widgets(self):
        data = {
            "title": "First dashboard",
            "widgets": [
                {"id": six.text_type(self.widget_1.id), "title": "New title"},
                {"id": six.text_type(self.widget_2.id), "title": "Other title"},
            ],
        }
        response = self.client.put(self.url(self.dashboard.id), data=data)
        assert response.status_code == 200

        widgets = self.get_widgets(self.dashboard.id)
        assert len(widgets) == 2
        self.assert_serialized_widget(data["widgets"][0], widgets[0])
        self.assert_serialized_widget(data["widgets"][1], widgets[1])

    def test_reorder_widgets(self):
        response = self.client.put(
            self.url(self.dashboard.id),
            data={
                "widgets": [
                    {"id": self.widget_3.id},
                    {"id": self.widget_2.id},
                    {"id": self.widget_1.id},
                    {"id": self.widget_4.id},
                ]
            },
        )
        assert response.status_code == 200
        self.assert_dashboard_and_widgets(
            [self.widget_3.id, self.widget_2.id, self.widget_1.id, self.widget_4.id]
        )

    def test_partial_reordering_deletes_widgets(self):
        response = self.client.put(
            self.url(self.dashboard.id),
            data={
                "title": "Changed the title",
                "widgets": [{"id": self.widget_3.id}, {"id": self.widget_4.id}],
            },
        )
        assert response.status_code == 200
        self.assert_dashboard_and_widgets([self.widget_3.id, self.widget_4.id])
        deleted_widget_ids = [self.widget_1.id, self.widget_2.id]
        assert not DashboardWidget.objects.filter(id__in=deleted_widget_ids).exists()
        assert not DashboardWidgetQuery.objects.filter(widget_id__in=deleted_widget_ids).exists()

    def test_widget_does_not_belong_to_dashboard(self):
        widget = DashboardWidget.objects.create(
            order=5,
            dashboard=Dashboard.objects.create(
                organization=self.organization, title="Dashboard 2", created_by=self.user
            ),
            title="Widget 200",
            display_type=DashboardWidgetDisplayTypes.LINE_CHART,
        )
        response = self.client.put(
            self.url(self.dashboard.id),
            data={"widgets": [{"id": self.widget_4.id}, {"id": widget.id}]},
        )
        assert response.status_code == 400
        assert response.data == [u"You cannot update widgets that are not part of this dashboard."]
        self.assert_no_changes()

    def test_widget_does_not_exist(self):
        response = self.client.put(
            self.url(self.dashboard.id),
            data={"widgets": [{"id": self.widget_4.id}, {"id": 1234567890}]},
        )
        assert response.status_code == 400
        assert response.data == [u"You cannot update widgets that are not part of this dashboard."]
        self.assert_no_changes()
