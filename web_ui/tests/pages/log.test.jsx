/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k) => k }),
}));

vi.mock('@/components', () => ({
  Header: ({ title, rightContent }) => (
    <div>
      <h1>{title}</h1>
      <div>{rightContent}</div>
    </div>
  ),
  Card: ({ children, className, contentClassName }) => (
    <div data-testid="card" className={className}>
      <div className={contentClassName}>{children}</div>
    </div>
  ),
  PageContent: ({ Header: HeaderNode, children, showEmptyContent, emptyContentProps, contentContainerClassName }) => (
    <div data-testid="page-content" className={contentContainerClassName}>
      {HeaderNode}
      {showEmptyContent ? (
        <div>{emptyContentProps?.description}</div>
      ) : (
        children
      )}
    </div>
  ),
  Icon: ({ name, onClick }) => (
    <button data-testid={`icon-${name}`} onClick={onClick} />
  ),
  LogViewerModal: () => null,
}));

vi.mock('@/stores/logViewerStore', () => ({
  useLogViewerStore: () => ({
    openModalWithLogId: vi.fn(),
  }),
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual('antd');
  return {
    ...actual,
    Table: ({ dataSource, columns, locale, scroll }) => (
      <div data-testid="table" data-scroll-y={scroll?.y || ''}>
        {dataSource && dataSource.length > 0 ? (
          <div>
            {dataSource.map((record, index) => (
              <div key={index} data-testid={`table-row-${index}`}>
                {columns.map((col) => {
                  const content = col.render
                    ? col.render(null, record, index)
                    : record[col.dataIndex];
                  return (
                    <div key={col.key} data-testid={`table-cell-${col.key}`}>
                      {typeof content === 'string' ? content : <div>{content}</div>}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        ) : (
          <div>{locale?.emptyText}</div>
        )}
      </div>
    ),
    Empty: ({ description }) => <div>{description}</div>,
    Button: ({ children, onClick }) => <button onClick={onClick}>{children}</button>,
  };
});

const mockGetRuleTriggerLogs = vi.fn();
const mockGetRuleTriggerLogStats = vi.fn();
const mockScrollIntoView = vi.fn();
vi.mock('@/api', () => ({
  getRuleTriggerLogs: (...args) => mockGetRuleTriggerLogs(...args),
  getRuleTriggerLogStats: (...args) => mockGetRuleTriggerLogStats(...args),
}));

import LogManage from '@/pages/LogManage';

beforeEach(() => {
  mockGetRuleTriggerLogs.mockReset();
  mockGetRuleTriggerLogStats.mockReset();
  mockScrollIntoView.mockReset();
  Element.prototype.scrollIntoView = mockScrollIntoView;
});

describe('pages/LogManage', () => {
  it('initialize load, display title, statistics card numbers and table data, and can click refresh', async () => {
    const now = Date.now();
    mockGetRuleTriggerLogs.mockResolvedValueOnce({
      code: 0,
      data: {
        total_items: 5,
        rule_logs: [
          {
            id: 'log-1',
            timestamp: now,
            trigger_rule_name: 'Rule A',
            trigger_rule_condition: 'if A',
            status: 'triggered',
            condition_results: [
              {
                camera_info: { name: 'Cam1' },
                channel: 1,
                result: true,
                images: [{ data: 'http://example.com/a.jpg', timestamp: now }],
              },
            ],
            execute_result: {
              ai_recommend_execute_type: 'static',
              ai_recommend_action_execute_results: [
                {
                  action: {
                    mcp_server_name: 'server1',
                    introduction: 'Action X',
                  },
                  result: true,
                },
              ],
              automation_action_execute_results: [],
              notify_result: {
                notify: { content: 'Notify Y' },
                result: false,
              },
            },
          },
        ],
      },
    });
    mockGetRuleTriggerLogStats.mockResolvedValueOnce({
      code: 0,
      data: {
        total_log_count: 5,
        enabled_rule_count: 1,
      },
    });

    render(<LogManage />);

    expect(await screen.findByText('home.menu.logManage')).toBeInTheDocument();
    expect((await screen.findByTestId('page-content')).className).toContain('logManageContentContainer');

    expect(await screen.findByText('5')).toBeInTheDocument();
    expect((await screen.findAllByText('1')).length).toBeGreaterThan(0);

    expect(await screen.findByText('Rule A')).toBeInTheDocument();
    expect(await screen.findByText('if A')).toBeInTheDocument();
    expect(await screen.findByText('Action X')).toBeInTheDocument();
    expect(await screen.findByText(/logManage.sendNotification/)).toBeInTheDocument();

    mockGetRuleTriggerLogs.mockResolvedValueOnce({ code: 0, data: { total_items: 5, rule_logs: [] } });
    mockGetRuleTriggerLogStats.mockResolvedValueOnce({
      code: 0,
      data: {
        total_log_count: 5,
        enabled_rule_count: 1,
      },
    });

    const refreshButtons = await screen.findAllByTestId('icon-refresh');
    fireEvent.click(refreshButtons[0]);

    await waitFor(() => {
      expect(mockGetRuleTriggerLogs).toHaveBeenCalledTimes(2);
      expect(mockGetRuleTriggerLogStats).toHaveBeenCalledTimes(2);
    });
  });

  it('no data, show empty state', async () => {
    mockGetRuleTriggerLogs.mockResolvedValueOnce({ code: 0, data: { total_items: 0, rule_logs: [] } });
    mockGetRuleTriggerLogStats.mockResolvedValueOnce({
      code: 0,
      data: {
        total_log_count: 0,
        enabled_rule_count: 0,
      },
    });

    render(<LogManage />);

    expect(await screen.findByText('home.menu.logManage')).toBeInTheDocument();
    expect(await screen.findByText('logManage.noRuleRecord')).toBeInTheDocument();
  });

  it('groups no-match records with completed checks and failed records in the issue section', async () => {
    const now = Date.now();
    mockGetRuleTriggerLogs.mockResolvedValueOnce({
      code: 0,
      data: {
        total_items: 3,
        rule_logs: [
          {
            id: 'log-no-match',
            timestamp: now,
            trigger_rule_name: 'Room Presence',
            trigger_rule_condition: 'detect whether someone is in the room',
            condition_results: [
              {
                camera_info: { name: 'Living Room Camera' },
                channel: 0,
                result: false,
                llm_reason: 'No person is visible in the scene',
                images: [{ data: 'http://example.com/no-match.jpg', timestamp: now }],
              },
            ],
            execute_result: null,
            status: 'skipped',
            reason_code: 'no_condition_match',
            message: 'No person is visible in the scene',
          },
          {
            id: 'log-failed',
            timestamp: now,
            trigger_rule_name: 'Rule Failed',
            trigger_rule_condition: 'if failed',
            condition_results: [],
            execute_result: null,
            status: 'failed',
            reason_code: 'llm_timeout',
            message: 'LLM call timeout',
          },
          {
            id: 'log-skipped',
            timestamp: now,
            trigger_rule_name: 'Rule Skipped',
            trigger_rule_condition: 'if skipped',
            condition_results: [],
            execute_result: null,
            status: 'skipped',
            reason_code: 'same_action_skipped',
            message: 'Same action already happened',
          },
        ],
      },
    });
    mockGetRuleTriggerLogStats.mockResolvedValueOnce({
      code: 0,
      data: {
        total_log_count: 3,
        enabled_rule_count: 1,
      },
    });

    render(<LogManage />);

    expect(await screen.findByText('logManage.ruleCheckRecords')).toBeInTheDocument();
    expect(await screen.findByText('Room Presence')).toBeInTheDocument();
    expect((await screen.findAllByText('No person is visible in the scene')).length).toBeGreaterThan(0);
    expect(await screen.findByText('logManage.statusNoConditionMatch')).toBeInTheDocument();

    expect(await screen.findByText('logManage.issueRecordTitle')).toBeInTheDocument();
    expect(await screen.findByText('Rule Failed')).toBeInTheDocument();
    expect(await screen.findByText('Rule Skipped')).toBeInTheDocument();
    expect((await screen.findAllByText('LLM call timeout')).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('Same action already happened')).length).toBeGreaterThan(0);
    expect(await screen.findByText('logManage.statusFailed')).toBeInTheDocument();
    expect(await screen.findByText('logManage.statusSameActionSkipped')).toBeInTheDocument();
  });

  it('renders independent scroll areas and jumps to them from the summary cards', async () => {
    mockGetRuleTriggerLogs.mockResolvedValueOnce({ code: 0, data: { total_items: 0, rule_logs: [] } });
    mockGetRuleTriggerLogStats.mockResolvedValueOnce({
      code: 0,
      data: {
        total_log_count: 0,
        enabled_rule_count: 0,
      },
    });

    render(<LogManage />);

    const tables = await screen.findAllByTestId('table');
    tables.forEach(table => {
      expect(table.getAttribute('data-scroll-y')).toBe('520');
    });

    fireEvent.click(screen.getByTestId('completed-checks-stat'));
    expect(mockScrollIntoView).toHaveBeenLastCalledWith({ behavior: 'smooth', block: 'start' });

    fireEvent.click(screen.getByTestId('issue-records-stat'));
    expect(mockScrollIntoView).toHaveBeenCalledTimes(2);
  });
});
