# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Rule trigger filter utility for managing trigger frequency and conditions.
Provides functionality to filter trigger rules based on frequency, period, and condition changes.
"""

import datetime
import logging
from collections import deque
from typing import Dict, OrderedDict

from croniter import croniter

from miloco_server.schema.trigger_schema import (
    TriggerRule,
    TriggerFrequencyFilter,
    TriggerTimeRange,
)

logger = logging.getLogger(name=__name__)


class RuleTriggerFilter:
    """Rule trigger filter class"""
    _CONTINUOUS_CHECK_INTERVAL: int = 1000 * 10    # Post-processing continuous non-trigger detection interval ms
    _TRIGGER_INTERVAL_MIN: int = 1000 * 10  # Post-processing trigger interval minimum value ms

    # Record trigger time queue for specified rule
    _trigger_history: Dict[str, deque]

    def __init__(self):
        self._trigger_history = {}

    def _default_rule_state(self, rule_id: str, filter_frequency: int = 1):
        """Default rule state."""
        self._trigger_history.setdefault(rule_id, deque(maxlen=filter_frequency))

    def _now_datetime(self) -> datetime.datetime:
        """Return current local server time."""
        return datetime.datetime.now()

    def _time_to_minutes(self, time_text: str) -> int:
        """Convert HH:mm to minutes from day start."""
        hours, minutes = time_text.split(":")
        return int(hours) * 60 + int(minutes)

    def _match_time_ranges(
            self,
            now: datetime.datetime,
            time_ranges: list[TriggerTimeRange]) -> bool:
        """Return whether local server time is inside any configured range."""
        if not time_ranges:
            return True

        current_minutes = now.hour * 60 + now.minute
        for time_range in time_ranges:
            start_minutes = self._time_to_minutes(time_range.start)
            end_minutes = self._time_to_minutes(time_range.end)
            if start_minutes < end_minutes:
                if start_minutes <= current_minutes < end_minutes:
                    return True
            elif start_minutes > end_minutes:
                if current_minutes >= start_minutes or current_minutes < end_minutes:
                    return True

        return False

    def pre_filter(self, rule: TriggerRule) -> bool:
        """Pre Trigger filter."""
        now_datetime = self._now_datetime()
        ts_now = int(now_datetime.timestamp() * 1000)
        if not rule.enabled:
            return False

        if not rule.filter:
            return True

        frequency = rule.filter.frequency.frequency if rule.filter.frequency else 1
        self._default_rule_state(rule.id, filter_frequency=frequency)

        # Check trigger period
        if rule.filter.time_ranges is not None:
            if not self._match_time_ranges(now_datetime, rule.filter.time_ranges):
                logger.info(
                    "trigger_pre_filter rule-%s: time_ranges: %s mismatch now_timestamp: %d, Not Exec",
                    rule.id, rule.filter.time_ranges, ts_now)
                return False
        else:
            cron_expression = rule.filter.period
            if cron_expression and croniter.is_valid(cron_expression) and not croniter.match(
                    cron_expression, now_datetime):
                logger.info(
                    "trigger_pre_filter rule-%s: period_cron: %s mismatch now_timestamp: %d, Not Exec",
                    rule.id, cron_expression, ts_now)
                return False

        # Check trigger frequency
        trigger_queue: deque = self._trigger_history[rule.id]
        filters = [rule.filter.frequency] if rule.filter.frequency else []
        if rule.filter.interval:
            filters.append(TriggerFrequencyFilter(frequency=1, period=rule.filter.interval))

        for freq_filter in filters:
            if (len(trigger_queue) >= freq_filter.frequency and
                    ts_now - trigger_queue[-freq_filter.frequency] < freq_filter.period * 1000):
                logger.info(
                    "trigger_pre_filter rule-%s: over frequency: %d/%ds, Not Exec",
                    rule.id, freq_filter.frequency, freq_filter.period)
                return False

        return True

    def post_filter(self, rule_id: str, result: bool) -> bool:
        """Post Trigger filter."""
        ts_now = int(datetime.datetime.now().timestamp() * 1000)
        self._default_rule_state(rule_id)

        # Check if the last trigger time is too close
        if (len(self._trigger_history[rule_id]) > 0 and
                ts_now - self._trigger_history[rule_id][-1] <
                self._TRIGGER_INTERVAL_MIN):
            logger.info(
                "trigger_post_filter rule-%s: last_trigger_time-%d "
                "too close to current_trigger_time-%d, Not Exec",
                rule_id, self._trigger_history[rule_id][-1], ts_now)
            return False

        # Same rule different condition has been filtered by TRIGGER_INTERVAL_MIN
        if result:
            self._trigger_history[rule_id].append(ts_now)

        return result


trigger_filter = RuleTriggerFilter()
