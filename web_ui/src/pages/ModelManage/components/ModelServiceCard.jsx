/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Button, Typography, Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import { Card, Icon } from '@/components';
import { ModelItem } from './index';
import styles from '../index.module.less';

const { Title, Text } = Typography;

/**
 * ModelServiceCard Component - Model service card component
 * 模型服务卡片组件
 *
 * @returns {JSX.Element} ModelServiceCard component
 */
const ModelServiceCard = ({
  models,
  onAddModel,
  onEditModel,
  onDeleteModel,
  // onRefreshModels
  cudaInfo,
  codexStatus,
  onSetModelLoaded,
  modelLoadingStates,
}) => {
  const { t } = useTranslation();
  const cloudModels = models.filter(model => model.local === false && model.providerType !== 'codex_login');
  const codexModels = models.filter(model => model.providerType === 'codex_login');
  const localModels = models.filter(model => model.local === true);

  return (
    <div
      className={styles.modelServiceCard}
    >
      <div className={styles.modelList}>
        <Card className={styles.modelCategory} contentClassName={styles.modelCategoryContent}>
          <div className={styles.modelCategoryTitle}>
            <Title style={{ marginBottom: 0 }} level={5}>{t('modelModal.cloudModels')}</Title>
            <Button
              type="primary"
              icon={<Icon name="add" size={14} style={{ color: 'white' }} />}
              onClick={() => { onAddModel() }}
            >
              {t('modelModal.addModel')}
            </Button>
          </div>
          <div className={styles.contentWrap}>
            {cloudModels.length > 0 ? (
              cloudModels.map(model => (
                <ModelItem
                  key={model.id}
                  model={model}
                  canEdit={model.editable !== false}
                  canDelete={model.deletable !== false}
                  onEdit={onEditModel}
                  onDelete={onDeleteModel}
                // onRefresh={onRefreshModels}
                />
              ))
            ) : (
              <Empty description={t('modelModal.noCloudModels')} />
            )}
          </div>
        </Card>

        <Card className={styles.modelCategory} contentClassName={styles.modelCategoryContent}>
          <div className={styles.modelCategoryTitle}>
            <Title style={{ marginBottom: 0 }} level={5}>{t('modelModal.codexModels')}</Title>
          </div>
          <div className={styles.contentWrap}>
            {codexModels.length > 0 ? (
              codexModels.map(model => (
                <ModelItem
                  key={model.id}
                  model={model}
                  canEdit={false}
                  canDelete={false}
                />
              ))
            ) : (
              <Empty description={codexStatus?.logged_in ? t('modelModal.noCodexModels') : t('modelModal.codexNotLoggedIn')} />
            )}
            {codexStatus?.codex_home && (
              <Text type="secondary">{t('modelModal.codexCredentialDir')}: {codexStatus.codex_home}</Text>
            )}
          </div>
        </Card>

        <Card
          className={styles.modelCategory} contentClassName={styles.modelCategoryContent}>
          <div className={styles.modelCategoryTitle}>
            <Title style={{ marginBottom: 0 }} level={5}>{t('modelModal.localModels')}</Title>
          </div>
          <div className={styles.contentWrap}>
            {localModels.length > 0 ? (
              localModels.map(model => (
                <ModelItem
                  key={model.id}
                  model={model}
                  canEdit={false}
                  canDelete={false}
                  cudaInfo={cudaInfo}
                  onSetModelLoaded={onSetModelLoaded}
                  modelLoadingStates={modelLoadingStates}
                />
              ))
            ) : (
              <Empty description={t('modelModal.noLocalModels')} />
            )}
          </div>
        </Card>
      </div>
    </div>
  );
};

export default ModelServiceCard;
