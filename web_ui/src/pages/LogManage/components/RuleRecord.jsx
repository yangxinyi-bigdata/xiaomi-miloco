/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useRef } from 'react';
import { Table, Empty, Button, Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import { Card, Icon, LogViewerModal } from '@/components';
import { useLogViewerStore } from '@/stores/logViewerStore';
import EmptyHistory from '@/assets/images/empty-history.png';
import styles from '../index.module.less';
import ImageRecordModal from './ImageRecordModal';
import useLog from '../hooks/useLog';

/**
 * RuleRecord Component - Rule record component
 * 规则记录组件
 *
 * @returns {JSX.Element} RuleRecord component
 */
const RuleRecord = () => {
  const { t } = useTranslation();
  const completedSectionRef = useRef(null);
  const issueSectionRef = useRef(null);

  const {
    mainRecordData,
    issueRecordData,
    completedCount,
    errorCount,
    totalItems,
    rulesLength,
    loading,
    imageModalVisible,
    currentImageData,
    initData,
    handleImageClick,
    handleCloseImageModal
  } = useLog();

  const handleViewDynamicLog = (item) => {
    const { rawData } = item;
    const logId = rawData?.id;

    if (!logId) {
      console.error('handleViewDynamicLog: cannot get log_id');
      return;
    }

    useLogViewerStore.getState().openModalWithLogId(logId);
  };

  const getStatusMeta = (item) => {
    const { status = 'triggered', reasonCode = '' } = item;
    if (status === 'triggered') {
      return { color: 'success', text: t('logManage.statusTriggered') };
    }
    if (reasonCode === 'no_condition_match') {
      return { color: 'processing', text: t('logManage.statusNoConditionMatch') };
    }
    if (reasonCode === 'same_action_skipped') {
      return { color: 'warning', text: t('logManage.statusSameActionSkipped') };
    }
    if (status === 'failed') {
      return { color: 'error', text: t('logManage.statusFailed') };
    }
    if (status === 'skipped') {
      return { color: 'warning', text: t('logManage.statusSkipped') };
    }
    return { color: 'default', text: status };
  };

  const renderStatus = (item) => {
    const meta = getStatusMeta(item);
    return <Tag color={meta.color}>{meta.text}</Tag>;
  };

  const getModelDecisionText = (item) => {
    const { status, reasonCode } = item;
    if (status === 'triggered') {
      return t('logManage.modelMatched');
    }
    if (reasonCode === 'no_condition_match') {
      return t('logManage.modelNoMatch');
    }
    if (reasonCode === 'same_action_skipped') {
      return t('logManage.modelSameAction');
    }
    if (status === 'failed') {
      return t('logManage.modelCheckFailed');
    }
    return t('logManage.modelNotExecuted');
  };

  const renderModelJudgement = (item) => {
    const cameraText = item.cameraResults
      .map(condition => {
        const cameraName = condition.camera_info?.name || condition.camera_info?.did || t('logManage.unknownCamera');
        return `${cameraName} ${t('logManage.channel')} ${condition.channel ?? 0}`;
      })
      .join(' / ');
    const reason = item.modelReason || item.message || item.reasonCode || t('logManage.noModelReason');

    return (
      <div className={styles.judgementCell}>
        <div className={styles.judgementTitle}>{getModelDecisionText(item)}</div>
        {cameraText && <div className={styles.judgementMeta}>{cameraText}</div>}
        <div className={styles.judgementReason}>{reason}</div>
      </div>
    );
  };

  const renderExecutionResult = (item) => {
    const {
      executionResults,
      notifyResult,
      triggerCondition,
      isDynamic,
      status,
      message: logMessage,
      reasonCode
    } = item;

    const allResults = [...executionResults];
    if (notifyResult) {
      allResults.push(notifyResult);
    }

    const diagnosticText = status === 'failed' || status === 'skipped'
      ? (logMessage || reasonCode || t('logManage.noExecutionAction'))
      : t('logManage.noExecutionAction');
    let executionContent;

    if (isDynamic) {
      const actionElements = allResults.length > 0 ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {allResults.map((result, index) => {
            const statusIcon = result.success ? (
              <Icon name="toolCallSuccess" size={14} style={{ marginRight: 4 }} />
            ) : (
              <Icon name="toolCallFail" size={14} style={{ marginRight: 4 }} />
            );

            const displayText = result.isNotification
              ? `${t('logManage.sendNotification')}: ${result.text}`
              : result.text;

            return (
              <span key={index} style={{ display: 'flex', alignItems: 'center' }}>
                {statusIcon}
                {displayText}
                <span>; </span>
              </span>
            );
          })}
        </div>
      ) : null;

      const { aiRecommendActionDescriptions = [] } = item;

      const buttonText = aiRecommendActionDescriptions.length > 0
        ? `${t('logManage.viewDynamicExecutionLogButtonText')}`
        : '';

      executionContent = (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {actionElements}
          {!actionElements && !buttonText && diagnosticText}
          {buttonText && (
            <Button
              type="link"
              size="small"
              onClick={() => handleViewDynamicLog(item)}
              style={{ padding: 0, height: 'auto', color: 'blue' }}
            >
              {buttonText}
            </Button>
          )}
        </div>
      );
    } else {
      if (allResults.length > 0) {
        executionContent = (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {allResults.map((result, index) => {
              const statusIcon = result.success ? (
                <Icon name="toolCallSuccess" size={14} style={{ marginRight: 4 }} />
              ) : (
                <Icon name="toolCallFail" size={14} style={{ marginRight: 4 }} />
              );

              const displayText = result.isNotification
                ? `${t('logManage.sendNotification')}: ${result.text}`
                : result.text;

              return (
                <span key={index} style={{ display: 'flex', alignItems: 'center' }}>
                  {statusIcon}
                  {displayText}
                  <span>; </span>
                </span>
              );
            })}
          </div>
        );
      } else {
        executionContent = diagnosticText;
      }
    }

    return (
      <div className={styles.executionCell}>
        <span style={{ fontWeight: 500 }}>{triggerCondition}</span>
        <span>→</span>
        {executionContent}
      </div>
    );
  };

  const renderImages = (record) => {
    if (!record.hasImages) {
      return (
        <span className={styles.disabledImageIcon}>
          <Icon name="ruleRecordImages" size={18} />
        </span>
      );
    }

    return (
      <Icon
        onClick={() => handleImageClick(record.cameraResults)}
        style={{ cursor: 'pointer' }}
        name="ruleRecordImages"
        size={18}
      />
    );
  };

  const recordColumns = [
    {
      title: t('logManage.triggerTime'),
      dataIndex: 'time',
      key: 'time',
      width: 100,
      render: (text) => (
        <div style={{ whiteSpace: 'pre-line' }}>{text}</div>
      )
    },
    { title: t('logManage.ruleName'), dataIndex: 'rule', key: 'rule', width: 120 },
    {
      title: t('logManage.status'),
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (_, record) => renderStatus(record)
    },
    {
      title: t('logManage.modelJudgement'),
      dataIndex: 'modelJudgement',
      key: 'modelJudgement',
      width: 280,
      render: (_, record) => renderModelJudgement(record)
    },
    {
      title: t('logManage.executionEffect'),
      dataIndex: 'result',
      key: 'result',
      render: (_, record) => renderExecutionResult(record)
    },
    {
      title: t('common.images'),
      dataIndex: 'images',
      key: 'images',
      width: 70,
      render: (_, record) => renderImages(record)
    },
  ];

  const scrollToSection = sectionRef => {
    sectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const renderRecordTable = (title, dataSource, emptyText, sectionRef, sectionTestId) => (
    <div ref={sectionRef} className={styles.recordSection} data-testid={sectionTestId}>
      <Card className={styles.recordCard}>
        <div className={styles.statList}>
          <span className={styles.statListTitle}>{title}</span>
          <div className={styles.update}>
            <Icon name="refresh" size={16} onClick={initData} />
          </div>
        </div>

        <Table
          columns={recordColumns}
          dataSource={dataSource}
          pagination={false}
          loading={loading}
          bordered={false}
          size="small"
          scroll={{ y: 520 }}
          className={styles.tableFont}
          locale={{
            emptyText: (
              <div className={styles.emptyState}>
                <Empty
                  description={emptyText}
                  imageStyle={{ width: 75, height: 75 }}
                  image={EmptyHistory}
                />
              </div>
            ),
          }}
        />
      </Card>
    </div>
  );

  return (
    <div className={styles.record}>
      <div className={styles.statsRow}>
        <Card className={styles.statCard} contentClassName={styles.statCardContent} >
          <div className={styles.statCardTitle}>
            <div className={styles.title}>{t('logManage.triggerRules')}</div>
            <div className={styles.subtitle}>{t('logManage.totalTriggeredRules')}</div>
          </div>
          <div className={styles.statCardValue}>{totalItems || 0}</div>
        </Card>
        <Card className={styles.statCard} contentClassName={styles.statCardContent}>
          <div className={styles.statCardTitle}>
            <div className={styles.title}>{t('logManage.activeRules')}</div>
            <div className={styles.subtitle}>{t('logManage.activeRulesCount')}:</div>
          </div>

          <div className={styles.statCardValue}>{rulesLength}</div>
        </Card>
        <button
          type="button"
          className={styles.statCardButton}
          data-testid="completed-checks-stat"
          onClick={() => scrollToSection(completedSectionRef)}
        >
          <Card className={styles.statCard} contentClassName={styles.statCardContent}>
            <div className={styles.statCardTitle}>
              <div className={styles.title}>{t('logManage.completedChecks')}</div>
              <div className={styles.subtitle}>{t('logManage.completedChecksCount')}</div>
            </div>
            <div className={styles.statCardValue}>{completedCount}</div>
          </Card>
        </button>
        <button
          type="button"
          className={styles.statCardButton}
          data-testid="issue-records-stat"
          onClick={() => scrollToSection(issueSectionRef)}
        >
          <Card className={styles.statCard} contentClassName={styles.statCardContent}>
            <div className={styles.statCardTitle}>
              <div className={styles.title}>{t('logManage.issueRecords')}</div>
              <div className={styles.subtitle}>{t('logManage.issueRecordsCount')}</div>
            </div>
            <div className={styles.statCardValue}>{errorCount}</div>
          </Card>
        </button>
      </div>
      {renderRecordTable(
        t('logManage.ruleCheckRecords'),
        mainRecordData,
        t('logManage.noRuleRecord'),
        completedSectionRef,
        'rule-check-records-section',
      )}
      {renderRecordTable(
        t('logManage.issueRecordTitle'),
        issueRecordData,
        t('logManage.noIssueRecord'),
        issueSectionRef,
        'issue-records-section',
      )}
      <ImageRecordModal
        visible={imageModalVisible}
        onCancel={handleCloseImageModal}
        imageData={currentImageData}
      />
      <LogViewerModal />
    </div>
  );
};

export default RuleRecord;
