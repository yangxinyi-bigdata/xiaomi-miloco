import datetime

from miloco_server.schema.trigger_schema import (
    ExecuteInfo,
    TriggerFilter,
    TriggerRule,
    TriggerTimeRange,
)
from miloco_server.utils.trigger_filter import RuleTriggerFilter


REAL_DATETIME = datetime.datetime


def _dt(hour: int, minute: int) -> datetime.datetime:
    return REAL_DATETIME(2026, 1, 1, hour, minute)


def _range(start: str, end: str) -> TriggerTimeRange:
    return TriggerTimeRange(start=start, end=end)


def _rule(trigger_filter: TriggerFilter) -> TriggerRule:
    return TriggerRule(
        id="rule-1",
        enabled=True,
        name="Test Rule",
        cameras=[],
        condition="if something happens",
        execute_info=ExecuteInfo(),
        filter=trigger_filter,
    )


def test_match_regular_time_range():
    rule_filter = RuleTriggerFilter()
    time_ranges = [_range("09:30", "11:15")]

    assert rule_filter._match_time_ranges(_dt(9, 30), time_ranges)
    assert rule_filter._match_time_ranges(_dt(10, 0), time_ranges)
    assert rule_filter._match_time_ranges(_dt(11, 14), time_ranges)
    assert not rule_filter._match_time_ranges(_dt(9, 29), time_ranges)
    assert not rule_filter._match_time_ranges(_dt(11, 15), time_ranges)


def test_match_cross_day_time_range():
    rule_filter = RuleTriggerFilter()
    time_ranges = [_range("22:00", "06:30")]

    assert rule_filter._match_time_ranges(_dt(23, 0), time_ranges)
    assert rule_filter._match_time_ranges(_dt(2, 0), time_ranges)
    assert rule_filter._match_time_ranges(_dt(6, 29), time_ranges)
    assert not rule_filter._match_time_ranges(_dt(6, 30), time_ranges)
    assert not rule_filter._match_time_ranges(_dt(21, 59), time_ranges)


def test_match_multiple_time_ranges_as_or():
    rule_filter = RuleTriggerFilter()
    time_ranges = [_range("08:00", "09:00"), _range("20:00", "21:00")]

    assert rule_filter._match_time_ranges(_dt(8, 30), time_ranges)
    assert rule_filter._match_time_ranges(_dt(20, 30), time_ranges)
    assert not rule_filter._match_time_ranges(_dt(12, 0), time_ranges)


def test_pre_filter_keeps_legacy_cron_when_time_ranges_absent(monkeypatch):
    rule_filter = RuleTriggerFilter()
    monkeypatch.setattr(rule_filter, "_now_datetime", lambda: _dt(7, 0))

    assert rule_filter.pre_filter(_rule(TriggerFilter(period="* 6-17 * * *")))
    assert not rule_filter.pre_filter(_rule(TriggerFilter(period="* 18-23,0-5 * * *")))


def test_pre_filter_prefers_time_ranges_over_legacy_cron(monkeypatch):
    rule_filter = RuleTriggerFilter()
    monkeypatch.setattr(rule_filter, "_now_datetime", lambda: _dt(7, 0))

    assert not rule_filter.pre_filter(_rule(TriggerFilter(
        period="* 6-17 * * *",
        time_ranges=[_range("20:00", "21:00")],
    )))
