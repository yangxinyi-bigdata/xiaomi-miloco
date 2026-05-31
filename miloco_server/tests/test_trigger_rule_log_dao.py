import time

from miloco_server.dao.trigger_dao import TriggerRuleDAO
from miloco_server.dao.trigger_rule_log_dao import TriggerRuleLogDAO
from miloco_server.schema.trigger_log_schema import (
    TriggerRuleLog,
    TriggerRuleLogReason,
    TriggerRuleLogStatus,
)
from miloco_server.utils import database as database_module
from miloco_server.utils.database import SQLiteConnector


def _setup_temp_database(tmp_path, monkeypatch):
    connector = SQLiteConnector()
    connector.db_path = tmp_path / "miloco.db"
    connector.initialize_database()
    monkeypatch.setattr(database_module, "db_connector", connector)
    return connector


def _make_log(
    *,
    status=TriggerRuleLogStatus.TRIGGERED,
    reason_code=None,
    message=None,
):
    return TriggerRuleLog(
        timestamp=int(time.time() * 1000),
        trigger_rule_id="rule-1",
        trigger_rule_name="Test Rule",
        trigger_rule_condition="if something happens",
        condition_results=[],
        execute_result=None,
        status=status,
        reason_code=reason_code,
        message=message,
    )


def test_failed_or_skipped_logs_are_deduplicated_on_write(tmp_path, monkeypatch):
    _setup_temp_database(tmp_path, monkeypatch)
    dao = TriggerRuleLogDAO()

    first_id = dao.create(_make_log(
        status=TriggerRuleLogStatus.FAILED,
        reason_code=TriggerRuleLogReason.LLM_TIMEOUT,
        message="LLM call timeout",
    ))
    duplicate_id = dao.create(_make_log(
        status=TriggerRuleLogStatus.FAILED,
        reason_code=TriggerRuleLogReason.LLM_TIMEOUT,
        message="  LLM   call timeout  ",
    ))

    assert duplicate_id == first_id
    assert dao.count_all() == 1


def test_triggered_logs_are_not_deduplicated(tmp_path, monkeypatch):
    _setup_temp_database(tmp_path, monkeypatch)
    dao = TriggerRuleLogDAO()

    first_id = dao.create(_make_log())
    second_id = dao.create(_make_log())

    assert first_id != second_id
    assert dao.count_all() == 2


def test_status_update_deduplicates_failed_logs(tmp_path, monkeypatch):
    _setup_temp_database(tmp_path, monkeypatch)
    dao = TriggerRuleLogDAO()

    first_id = dao.create(_make_log())
    second_id = dao.create(_make_log())

    assert dao.update_status(
        first_id,
        TriggerRuleLogStatus.FAILED,
        TriggerRuleLogReason.DYNAMIC_EXECUTE_FAILED,
        "Dynamic executor timeout",
    )
    assert dao.update_status(
        second_id,
        TriggerRuleLogStatus.FAILED,
        TriggerRuleLogReason.DYNAMIC_EXECUTE_FAILED,
        "  Dynamic executor   timeout ",
    )
    logs = dao.get_all()

    assert dao.count_all() == 1
    assert logs[0].id == first_id
    assert logs[0].status == TriggerRuleLogStatus.FAILED


def test_legacy_logs_default_to_triggered_status(tmp_path, monkeypatch):
    connector = _setup_temp_database(tmp_path, monkeypatch)
    dao = TriggerRuleLogDAO()
    connector.execute_update(
        """
        INSERT INTO trigger_rule_log (
            id, timestamp, trigger_rule_id, trigger_rule_name,
            trigger_rule_condition, camera_condition_results, execute_result
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "legacy-log",
            int(time.time() * 1000),
            "rule-1",
            "Legacy Rule",
            "if legacy",
            "[]",
            None,
        ),
    )

    logs = dao.get_all()

    assert logs[0].status == TriggerRuleLogStatus.TRIGGERED
    assert logs[0].reason_code is None
    assert logs[0].message is None


def test_enabled_rule_count_uses_database_value(tmp_path, monkeypatch):
    connector = _setup_temp_database(tmp_path, monkeypatch)
    connector.execute_update(
        """
        INSERT INTO trigger_rule (
            id, name, enabled, camera_dids, condition, execute_info, filter
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("rule-enabled", "Enabled", 1, "[]", "if enabled", "{}", None),
    )
    connector.execute_update(
        """
        INSERT INTO trigger_rule (
            id, name, enabled, camera_dids, condition, execute_info, filter
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("rule-disabled", "Disabled", 0, "[]", "if disabled", "{}", None),
    )

    assert TriggerRuleDAO().count_enabled() == 1
