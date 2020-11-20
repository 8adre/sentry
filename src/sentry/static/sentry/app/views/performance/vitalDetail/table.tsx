import React from 'react';
import {Location, LocationDescriptorObject} from 'history';
import * as ReactRouter from 'react-router';

import {IconStar, IconUser} from 'app/icons';
import {Organization, Project} from 'app/types';
import Pagination from 'app/components/pagination';
import Link from 'app/components/links/link';
import EventView, {EventData, isFieldSortable} from 'app/utils/discover/eventView';
import {TableColumn} from 'app/views/eventsV2/table/types';
import GridEditable, {COL_WIDTH_UNDEFINED, GridColumn} from 'app/components/gridEditable';
import SortLink from 'app/components/gridEditable/sortLink';
import HeaderCell from 'app/views/eventsV2/table/headerCell';
import CellAction, {Actions, updateQuery} from 'app/views/eventsV2/table/cellAction';
import {trackAnalyticsEvent} from 'app/utils/analytics';
import {getFieldRenderer} from 'app/utils/discover/fieldRenderers';
import {tokenizeSearch, stringifyQueryObject} from 'app/utils/tokenizeSearch';
import DiscoverQuery, {TableData, TableDataRow} from 'app/utils/discover/discoverQuery';
import styled from 'app/styled';
import space from 'app/styles/space';
import Tag from 'app/components/tagDeprecated';
import {t} from 'app/locale';
import {WebVital} from 'app/utils/discover/fields';

import {vitalAbbreviations, vitalNameFromLocation} from './utils';
import {
  TransactionFilterOptions,
  transactionSummaryRouteWithQuery,
} from '../transactionSummary/utils';
import {WEB_VITAL_DETAILS} from '../transactionVitals/constants';
import {DisplayModes} from '../transactionSummary/charts';

const COLUMN_TITLES = ['Transaction', 'Project', 'Unique Users', 'Count'];

const getTableColumnTitle = (index: number, vitalName: WebVital) => {
  const abbrev = vitalAbbreviations[vitalName];
  const titles = [
    ...COLUMN_TITLES,
    `${abbrev}(p50)`,
    `${abbrev}(p75)`,
    `${abbrev}(p95)`,
    `${abbrev}(Status)`,
  ];
  return titles[index];
};

export function getProjectID(
  eventData: EventData,
  projects: Project[]
): string | undefined {
  const projectSlug = (eventData?.project as string) || undefined;

  if (typeof projectSlug === undefined) {
    return undefined;
  }

  const project = projects.find(currentProject => currentProject.slug === projectSlug);

  if (!project) {
    return undefined;
  }

  return project.id;
}

const modifyTableData = (threshold, meta: any, data: any[]) => {
  // TODO: Replace this once compare aggregate api is in
  meta.vitalPass = 'integer';
  return data.map(d => {
    const key = Object.keys(d).find(i => i.includes('p75'))!;
    const p75 = d[key];
    d.vitalPass = p75 < threshold ? 1 : 0;
    return d;
  });
};

type Props = {
  eventView: EventView;
  organization: Organization;
  location: Location;
  setError: (msg: string | undefined) => void;
  summaryConditions: string;

  projects: Project[];
};

type State = {
  widths: number[];
};

class Table extends React.Component<Props, State> {
  state = {
    widths: [],
  };

  handleCellAction = (column: TableColumn<keyof TableDataRow>) => {
    return (action: Actions, value: React.ReactText) => {
      const {eventView, location, organization} = this.props;

      trackAnalyticsEvent({
        eventKey: 'performance_views.overview.cellaction',
        eventName: 'Performance Views: Cell Action Clicked',
        organization_id: parseInt(organization.id, 10),
        action,
      });

      const searchConditions = tokenizeSearch(eventView.query);

      // remove any event.type queries since it is implied to apply to only transactions
      searchConditions.removeTag('event.type');

      updateQuery(searchConditions, action, column.name, value);

      ReactRouter.browserHistory.push({
        pathname: location.pathname,
        query: {
          ...location.query,
          cursor: undefined,
          query: stringifyQueryObject(searchConditions),
        },
      });
    };
  };

  renderBodyCell(
    tableData: TableData | null,
    column: TableColumn<keyof TableDataRow>,
    dataRow: TableDataRow,
    vitalName: WebVital
  ): React.ReactNode {
    const {eventView, organization, projects, location, summaryConditions} = this.props;

    if (!tableData || !tableData.meta) {
      return dataRow[column.key];
    }
    const tableMeta = tableData.meta;

    const field = String(column.key);
    const fieldRenderer = getFieldRenderer(field, tableMeta);
    const rendered = fieldRenderer(dataRow, {organization, location});

    const allowActions = [
      Actions.ADD,
      Actions.EXCLUDE,
      Actions.SHOW_GREATER_THAN,
      Actions.SHOW_LESS_THAN,
    ];

    if (field === 'count_unique(user)') {
      return (
        <UniqueUserCell>
          {rendered}
          <StyledUserIcon size="20" />
        </UniqueUserCell>
      );
    }

    if (field === 'vitalPass') {
      if (dataRow[field]) {
        return <PassTag>{t('PASS')}</PassTag>;
      } else {
        return <FailTag>{t('FAIL')}</FailTag>;
      }
    }

    if (field === 'transaction') {
      const projectID = getProjectID(dataRow, projects);
      const summaryView = eventView.clone();
      const conditions = tokenizeSearch(summaryConditions);
      conditions.addTagValues('has', [`${vitalName}`]);
      summaryView.query = stringifyQueryObject(conditions);

      const target = transactionSummaryRouteWithQuery({
        orgSlug: organization.slug,
        transaction: String(dataRow.transaction) || '',
        query: summaryView.generateQueryStringObject(),
        projectID,
        showTransactions: TransactionFilterOptions.RECENT,
        display: DisplayModes.VITALS,
      });

      return (
        <CellAction
          column={column}
          dataRow={dataRow}
          handleCellAction={this.handleCellAction(column)}
          allowActions={allowActions}
        >
          <Link to={target} onClick={this.handleSummaryClick}>
            {rendered}
          </Link>
        </CellAction>
      );
    }

    if (field.startsWith('key_transaction') || field.startsWith('user_misery')) {
      return rendered;
    }

    return (
      <CellAction
        column={column}
        dataRow={dataRow}
        handleCellAction={this.handleCellAction(column)}
        allowActions={allowActions}
      >
        {rendered}
      </CellAction>
    );
  }

  renderBodyCellWithData = (tableData: TableData | null, vitalName: WebVital) => {
    return (
      column: TableColumn<keyof TableDataRow>,
      dataRow: TableDataRow
    ): React.ReactNode => this.renderBodyCell(tableData, column, dataRow, vitalName);
  };

  renderHeadCell(
    tableMeta: TableData['meta'],
    column: TableColumn<keyof TableDataRow>,
    title: React.ReactNode
  ): React.ReactNode {
    const {eventView, location} = this.props;

    return (
      <HeaderCell column={column} tableMeta={tableMeta}>
        {({align}) => {
          const field = {field: column.name, width: column.width};

          function generateSortLink(): LocationDescriptorObject | undefined {
            if (!tableMeta) {
              return undefined;
            }

            const nextEventView = eventView.sortOnField(field, tableMeta);
            const queryStringObject = nextEventView.generateQueryStringObject();

            return {
              ...location,
              query: {...location.query, sort: queryStringObject.sort},
            };
          }
          const currentSort = eventView.sortForField(field, tableMeta);
          const canSort = isFieldSortable(field, tableMeta);

          return (
            <SortLink
              align={align}
              title={title || field.field}
              direction={currentSort ? currentSort.kind : undefined}
              canSort={canSort}
              generateSortLink={generateSortLink}
            />
          );
        }}
      </HeaderCell>
    );
  }

  renderHeadCellWithMeta = (tableMeta: TableData['meta'], vitalName: WebVital) => {
    return (column: TableColumn<keyof TableDataRow>, index: number): React.ReactNode =>
      this.renderHeadCell(tableMeta, column, getTableColumnTitle(index, vitalName));
  };

  renderPrependCellWithData = (tableData: TableData | null, vitalName: WebVital) => {
    const {eventView} = this.props;
    const keyTransactionColumn = eventView
      .getColumns()
      .find((col: TableColumn<React.ReactText>) => col.name === 'key_transaction');
    return (isHeader: boolean, dataRow?: any) => {
      if (!keyTransactionColumn) {
        return [];
      }

      if (isHeader) {
        const star = (
          <IconStar
            key="keyTransaction"
            color="yellow300"
            isSolid
            data-test-id="key-transaction-header"
          />
        );
        return [this.renderHeadCell(tableData?.meta, keyTransactionColumn, star)];
      } else {
        return [this.renderBodyCell(tableData, keyTransactionColumn, dataRow, vitalName)];
      }
    };
  };

  handleSummaryClick = () => {
    const {organization} = this.props;
    trackAnalyticsEvent({
      eventKey: 'performance_views.overview.navigate.summary',
      eventName: 'Performance Views: Overview view summary',
      organization_id: parseInt(organization.id, 10),
    });
  };

  handleResizeColumn = (columnIndex: number, nextColumn: GridColumn) => {
    const widths: number[] = [...this.state.widths];
    widths[columnIndex] = nextColumn.width
      ? Number(nextColumn.width)
      : COL_WIDTH_UNDEFINED;
    this.setState({widths});
  };

  getSortedEventView() {
    const {eventView} = this.props;

    // We special case sort by key transactions here to include
    // the transaction name and project as the secondary sorts.
    const keyTransactionSort = eventView.sorts.find(
      sort => sort.field === 'key_transaction'
    );
    if (keyTransactionSort) {
      const sorts = ['key_transaction', 'transaction', 'project'].map(field => ({
        field,
        kind: keyTransactionSort.kind,
      }));
      return eventView.withSorts(sorts);
    }

    return eventView;
  }

  render() {
    const {eventView, organization, location} = this.props;
    const {widths} = this.state;

    const fakeColumnView = eventView.clone();
    fakeColumnView.fields = [...eventView.fields, {field: 'vitalPass'}];
    const columnOrder = fakeColumnView
      .getColumns()
      // remove key_transactions from the column order as we'll be rendering it
      // via a prepended column
      .filter((col: TableColumn<React.ReactText>) => col.name !== 'key_transaction')
      .map((col: TableColumn<React.ReactText>, i: number) => {
        if (typeof widths[i] === 'number') {
          return {...col, width: widths[i]};
        }
        return col;
      });

    const sortedEventView = this.getSortedEventView();
    const columnSortBy = sortedEventView.getSorts();
    const vitalName = vitalNameFromLocation(location);
    const vitalThreshold = WEB_VITAL_DETAILS[vitalName].failureThreshold;

    const prependColumnWidths = organization.features.includes('key-transactions')
      ? ['max-content']
      : [];

    return (
      <div>
        <DiscoverQuery
          eventView={sortedEventView}
          orgSlug={organization.slug}
          location={location}
          limit={10}
        >
          {({pageLinks, isLoading, tableData}) => (
            <React.Fragment>
              <GridEditable
                isLoading={isLoading}
                data={
                  tableData
                    ? modifyTableData(vitalThreshold, tableData.meta, tableData.data)
                    : []
                }
                columnOrder={columnOrder}
                columnSortBy={columnSortBy}
                grid={{
                  onResizeColumn: this.handleResizeColumn,
                  renderHeadCell: this.renderHeadCellWithMeta(
                    tableData?.meta,
                    vitalName
                  ) as any,
                  renderBodyCell: this.renderBodyCellWithData(
                    tableData,
                    vitalName
                  ) as any,
                  renderPrependColumns: this.renderPrependCellWithData(
                    tableData,
                    vitalName
                  ) as any,
                  prependColumnWidths,
                }}
                location={location}
              />
              <Pagination pageLinks={pageLinks} />
            </React.Fragment>
          )}
        </DiscoverQuery>
      </div>
    );
  }
}

const UniqueUserCell = styled('span')`
  display: flex;
  align-items: center;
`;

const StyledUserIcon = styled(IconUser)`
  margin-left: ${space(1)};
  color: ${p => p.theme.gray400};
`;

const FailTag = styled(Tag)`
  position: absolute;
  right: ${space(3)};
  font-size: ${p => p.theme.fontSizeSmall};
  font-weight: 600;
  background-color: ${p => p.theme.red300};
  color: ${p => p.theme.white};
  text-transform: uppercase;
`;

const PassTag = styled(Tag)`
  position: absolute;
  right: ${space(3)};
  font-size: ${p => p.theme.fontSizeSmall};
  font-weight: 600;
  background-color: ${p => p.theme.gray100};
  color: ${p => p.theme.gray400};
  text-transform: uppercase;
`;

export default Table;