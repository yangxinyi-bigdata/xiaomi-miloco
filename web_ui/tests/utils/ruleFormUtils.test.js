/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { describe, expect, it } from 'vitest';
import {
  formDataUtils,
  TRIGGER_PERIOD_MODES,
  triggerTimeRangeUtils,
} from '@/utils/ruleFormUtils';

describe('ruleFormUtils trigger time ranges', () => {
  it('converts custom time ranges to backend time_ranges', () => {
    const result = formDataUtils.toSubmitFormat({
      triggerPeriodMode: TRIGGER_PERIOD_MODES.CUSTOM,
      triggerTimeRanges: [
        { start: '09:30', end: '11:15' },
        { start: '20:00', end: '21:00' },
      ],
      triggerIntervalHours: 0,
      triggerIntervalMinutes: 1,
      triggerIntervalSeconds: 30,
    });

    expect(result.period).toBeNull();
    expect(result.time_ranges).toEqual([
      { start: '09:30', end: '11:15' },
      { start: '20:00', end: '21:00' },
    ]);
    expect(result.interval).toBe(90);
  });

  it('keeps all day as no time range restriction', () => {
    const result = formDataUtils.toSubmitFormat({
      triggerPeriodMode: TRIGGER_PERIOD_MODES.ALL_DAY,
      triggerTimeRanges: [{ start: '09:30', end: '11:15' }],
      triggerIntervalHours: 0,
      triggerIntervalMinutes: 0,
      triggerIntervalSeconds: 2,
    });

    expect(result.period).toBeNull();
    expect(result.time_ranges).toBeNull();
  });

  it('maps legacy cron presets to form state', () => {
    expect(formDataUtils.toFormFormat({ period: '* * * * *', interval: 2 })).toMatchObject({
      triggerPeriodMode: TRIGGER_PERIOD_MODES.ALL_DAY,
    });
    expect(formDataUtils.toFormFormat({ period: '* 6-17 * * *', interval: 2 })).toMatchObject({
      triggerPeriodMode: TRIGGER_PERIOD_MODES.CUSTOM,
      triggerTimeRanges: [{ start: '06:00', end: '18:00' }],
    });
    expect(formDataUtils.toFormFormat({ period: '* 18-23,0-5 * * *', interval: 2 })).toMatchObject({
      triggerPeriodMode: TRIGGER_PERIOD_MODES.CUSTOM,
      triggerTimeRanges: [{ start: '18:00', end: '06:00' }],
    });
  });

  it('rejects empty, invalid, and zero-length custom ranges', () => {
    expect(triggerTimeRangeUtils.validateTimeRanges([])).toMatchObject({
      valid: false,
      messageKey: 'timeRangeRequired',
    });
    expect(triggerTimeRangeUtils.validateTimeRanges([{ start: '24:00', end: '25:00' }])).toMatchObject({
      valid: false,
      messageKey: 'invalidTimeRange',
    });
    expect(triggerTimeRangeUtils.validateTimeRanges([{ start: '09:00', end: '09:00' }])).toMatchObject({
      valid: false,
      messageKey: 'timeRangeSameTime',
    });
  });

  it('normalizes overlapping and cross-day ranges', () => {
    expect(triggerTimeRangeUtils.normalizeTimeRanges([
      { start: '09:00', end: '10:00' },
      { start: '09:30', end: '11:00' },
      { start: '22:00', end: '02:00' },
    ])).toEqual([
      { start: '09:00', end: '11:00' },
      { start: '22:00', end: '02:00' },
    ]);
  });
});
