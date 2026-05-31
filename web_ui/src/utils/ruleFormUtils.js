/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */



/**
 * rule form tool function
 * handle time conversion, cron expression etc.
 */

export const TRIGGER_PERIOD_MODES = {
  ALL_DAY: 'all_day',
  CUSTOM: 'custom',
};

// trigger period mode options
export const TRIGGER_PERIOD_MODE_OPTIONS = [
  { label: '全天', value: TRIGGER_PERIOD_MODES.ALL_DAY },
  { label: '自定义时间段', value: TRIGGER_PERIOD_MODES.CUSTOM },
];

export const DEFAULT_TRIGGER_TIME_RANGE = { start: '09:00', end: '18:00' };

// trigger interval options (hour, minute, second)
export const TRIGGER_INTERVAL_OPTIONS = {
  hours: Array.from({ length: 24 }, (_, i) => ({ label: `${i}小时`, value: i })),
  minutes: Array.from({ length: 60 }, (_, i) => ({ label: `${i}分钟`, value: i })),
  seconds: Array.from({ length: 60 }, (_, i) => ({ label: `${i}秒`, value: i })),
};


const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;
const MINUTES_PER_DAY = 24 * 60;

const formatMinutes = (minutes) => {
  const normalized = ((minutes % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY;
  const hours = Math.floor(normalized / 60);
  const mins = normalized % 60;
  return `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;
};

const timeToMinutes = (time) => {
  if (!TIME_PATTERN.test(time)) {
    return null;
  }
  const [hours, minutes] = time.split(':').map(Number);
  return hours * 60 + minutes;
};

/**
 * trigger time range conversion tool
 */
export const triggerTimeRangeUtils = {
  parseTimeRange: (range) => {
    if (!range || typeof range.start !== 'string' || typeof range.end !== 'string') {
      return null;
    }

    const start = range.start.trim();
    const end = range.end.trim();
    const startMinutes = timeToMinutes(start);
    const endMinutes = timeToMinutes(end);

    if (startMinutes === null || endMinutes === null) {
      return null;
    }

    return {
      start,
      end,
      startMinutes,
      endMinutes,
    };
  },

  validateTimeRanges: (ranges) => {
    if (!Array.isArray(ranges) || ranges.length === 0) {
      return { valid: false, messageKey: 'timeRangeRequired' };
    }

    for (const range of ranges) {
      const parsed = triggerTimeRangeUtils.parseTimeRange(range);
      if (!parsed) {
        return { valid: false, messageKey: 'invalidTimeRange' };
      }
      if (parsed.startMinutes === parsed.endMinutes) {
        return { valid: false, messageKey: 'timeRangeSameTime' };
      }
    }

    return { valid: true };
  },

  normalizeTimeRanges: (ranges) => {
    const validation = triggerTimeRangeUtils.validateTimeRanges(ranges);
    if (!validation.valid) {
      return [];
    }

    const segments = [];
    ranges.forEach((range) => {
      const parsed = triggerTimeRangeUtils.parseTimeRange(range);
      if (parsed.startMinutes < parsed.endMinutes) {
        segments.push({ start: parsed.startMinutes, end: parsed.endMinutes });
      } else {
        segments.push({ start: parsed.startMinutes, end: MINUTES_PER_DAY });
        segments.push({ start: 0, end: parsed.endMinutes });
      }
    });

    const merged = segments
      .sort((a, b) => a.start - b.start)
      .reduce((result, segment) => {
        const previous = result[result.length - 1];
        if (previous && segment.start <= previous.end) {
          previous.end = Math.max(previous.end, segment.end);
        } else {
          result.push({ ...segment });
        }
        return result;
      }, []);

    if (merged.length === 1 && merged[0].start === 0 && merged[0].end === MINUTES_PER_DAY) {
      return [];
    }

    if (
      merged.length > 1 &&
      merged[0].start === 0 &&
      merged[merged.length - 1].end === MINUTES_PER_DAY
    ) {
      const first = merged.shift();
      const last = merged.pop();
      merged.push({ start: last.start, end: first.end });
    }

    return merged.map(segment => ({
      start: formatMinutes(segment.start),
      end: formatMinutes(segment.end),
    }));
  },

  cronToTimeRangeMode: (cron) => {
    if (!cron) {
      return {
        triggerPeriodMode: TRIGGER_PERIOD_MODES.ALL_DAY,
        triggerTimeRanges: [DEFAULT_TRIGGER_TIME_RANGE],
      };
    }

    try {
      const parts = cron.split(' ');
      if (parts.length !== 5) {
        return {
          triggerPeriodMode: TRIGGER_PERIOD_MODES.ALL_DAY,
          triggerTimeRanges: [DEFAULT_TRIGGER_TIME_RANGE],
        };
      }

      const [minute, hour, day, month, weekday] = parts;

      // check if it is all day
      if (minute === '*' && hour === '*' && day === '*' && month === '*' && weekday === '*') {
        return {
          triggerPeriodMode: TRIGGER_PERIOD_MODES.ALL_DAY,
          triggerTimeRanges: [DEFAULT_TRIGGER_TIME_RANGE],
        };
      }

      // check if it is daytime (6:00-17:59)
      if (minute === '*' && hour === '6-17' && day === '*' && month === '*' && weekday === '*') {
        return {
          triggerPeriodMode: TRIGGER_PERIOD_MODES.CUSTOM,
          triggerTimeRanges: [{ start: '06:00', end: '18:00' }],
        };
      }

      // check if it is nighttime (18:00-23:59, 0:00-5:59)
      if (minute === '*' && hour === '18-23,0-5' && day === '*' && month === '*' && weekday === '*') {
        return {
          triggerPeriodMode: TRIGGER_PERIOD_MODES.CUSTOM,
          triggerTimeRanges: [{ start: '18:00', end: '06:00' }],
        };
      }

      return {
        triggerPeriodMode: TRIGGER_PERIOD_MODES.ALL_DAY,
        triggerTimeRanges: [DEFAULT_TRIGGER_TIME_RANGE],
      };
    } catch (error) {
      console.error('Invalid cron expression:', error);
      return {
        triggerPeriodMode: TRIGGER_PERIOD_MODES.ALL_DAY,
        triggerTimeRanges: [DEFAULT_TRIGGER_TIME_RANGE],
      };
    }
  },
};

/**
 * trigger interval conversion tool
 */
export const triggerIntervalUtils = {
  // convert time selector value to seconds
  timeToSeconds: (hours = 0, minutes = 0, seconds = 0) => {
    return hours * 3600 + minutes * 60 + seconds;
  },

  // convert seconds to time selector value
  secondsToTime: (totalSeconds) => {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return { hours, minutes, seconds };
  },

  // validate time selector value
  validateTime: (hours, minutes, seconds) => {
    return hours >= 0 && hours <= 23 &&
           minutes >= 0 && minutes <= 59 &&
           seconds >= 0 && seconds <= 59;
  },
};

/**
 * trigger frequency conversion tool
 */
export const triggerFrequencyUtils = {
  // convert frequency selector value to object
  timeToFrequencyObject: (periodHours = 0, periodMinutes = 0, periodSeconds = 0, frequency = 1) => {
    console.log('periodHours', periodHours, periodMinutes, periodSeconds, frequency);
    const period = triggerIntervalUtils.timeToSeconds(periodHours, periodMinutes, periodSeconds);
    return {
      frequency: Math.min(frequency, 99),
      period: period,
    };
  },

  // convert object to frequency selector value
  frequencyObjectToTime: (obj) => {
    if (!obj || typeof obj.frequency !== 'number' || typeof obj.period !== 'number') {
      return { periodHours: 0, periodMinutes: 0, periodSeconds: 0, frequency: 1 };
    }

    const time = triggerIntervalUtils.secondsToTime(obj.period);
    return {
      periodHours: time.hours,
      periodMinutes: time.minutes,
      periodSeconds: time.seconds,
      frequency: Math.min(obj.frequency, 99),
    };
  },

  // validate frequency selector value
  validateFrequency: (periodHours, periodMinutes, periodSeconds, frequency) => {
    const isValidTime = triggerIntervalUtils.validateTime(periodHours, periodMinutes, periodSeconds);
    const isValidFrequency = frequency >= 1 && frequency <= 99;
    return isValidTime && isValidFrequency;
  },
};

/**
 * form data conversion tool
 */
export const formDataUtils = {
  // convert form data to submit format
  toSubmitFormat: (formData) => {
    const {
      triggerPeriodMode,
      triggerTimeRanges,
      triggerIntervalHours,
      triggerIntervalMinutes,
      triggerIntervalSeconds,
      ...otherData
    } = formData;

    const normalizedRanges = triggerPeriodMode === TRIGGER_PERIOD_MODES.CUSTOM
      ? triggerTimeRangeUtils.normalizeTimeRanges(triggerTimeRanges)
      : null;

    return {
      ...otherData,
      period: null,
      time_ranges: normalizedRanges && normalizedRanges.length > 0 ? normalizedRanges : null,
      interval: triggerIntervalUtils.timeToSeconds(
        triggerIntervalHours || 0,
        triggerIntervalMinutes || 0,
        triggerIntervalSeconds
      ),
    };
  },

  // convert backend data to form format
  toFormFormat: (backendData) => {
    const {
      period,
      time_ranges,
      interval,
      // frequency,
      ...otherData
    } = backendData;

    const intervalTime = triggerIntervalUtils.secondsToTime(interval || 2);
    const hasTimeRangesField = Array.isArray(time_ranges);
    const normalizedRanges = hasTimeRangesField
      ? triggerTimeRangeUtils.normalizeTimeRanges(time_ranges)
      : [];
    const legacyPeriod = triggerTimeRangeUtils.cronToTimeRangeMode(period);
    const triggerPeriodMode = hasTimeRangesField
      ? (normalizedRanges.length > 0 ? TRIGGER_PERIOD_MODES.CUSTOM : TRIGGER_PERIOD_MODES.ALL_DAY)
      : legacyPeriod.triggerPeriodMode;
    const triggerTimeRanges = hasTimeRangesField
      ? (normalizedRanges.length > 0 ? normalizedRanges : [DEFAULT_TRIGGER_TIME_RANGE])
      : legacyPeriod.triggerTimeRanges;

    return {
      ...otherData,
      triggerPeriodMode,
      triggerTimeRanges,
      triggerIntervalHours: intervalTime.hours,
      triggerIntervalMinutes: intervalTime.minutes,
      triggerIntervalSeconds: intervalTime.seconds,
    };
  },
};
