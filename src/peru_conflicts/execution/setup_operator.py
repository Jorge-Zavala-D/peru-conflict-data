"""Thin installed operator lifecycle. No caller-selected authority or private paths."""

from pathlib import Path

from .access_policy import ACCESS_POLICY_V2
from .setup_context import require_context
from .setup_deployment import installed_source
from .setup_evidence import EvidenceJournal

OPERATIONS = frozenset({"admit", "next", "capture", "import", "status", "recover"})


def _summary(journal: EvidenceJournal) -> dict[str, object]:
    records = journal.records
    pending = journal.pending
    outcomes = [r for r in records if r["kind"] == "outcome"]
    checks = {
        r["order"]["check_id"]: r["payload"]["result"] for r in outcomes if r["order"]["check_id"]
    }
    controls = {c.control_id: "NOT_RUN" for c in ACCESS_POLICY_V2.application_controls}
    controls.update(
        {
            r["order"]["control_id"]: r["payload"]["result"]
            for r in outcomes
            if r["order"]["control_id"]
        }
    )
    result = outcomes[-1]["payload"]["result"] if outcomes else "NOT_RUN"
    if pending is not None:
        state = (
            "UNKNOWN"
            if any(
                r["kind"] == "dispatch" and r["order"]["sequence"] == pending.sequence
                for r in records
            )
            else "INTENT_PENDING"
        )
        result = "UNKNOWN" if state == "UNKNOWN" else "NOT_RUN"
        if pending.check_id:
            checks[pending.check_id] = result
        if pending.control_id:
            controls[pending.control_id] = result
    elif journal.stopped:
        state = "STOPPED"
    elif result == "PENDING":
        state = "PENDING"
    else:
        try:
            journal.preview()
        except StopIteration:
            state = "COMPLETED"
        except ValueError:
            state = "BLOCKED"
        else:
            state = "READY"
    return {
        "state": state,
        "result": result,
        "exit_code": 0,
        "checks": checks,
        "controls": controls,
        "not_run": sorted(
            row.check_id
            for row in ACCESS_POLICY_V2.acl_expectations
            if checks.get(row.check_id, "NOT_RUN") == "NOT_RUN"
        ),
    }


def operate(operation: str, admission: object) -> dict[str, object]:
    """One action, or inspection. Reopening never renews a resident release.

    Exit 0 means the requested inspection/action returned, not setup acceptance;
    2 is rejected admission/history/arguments; 3 is stopped/incomplete action.
    Only explicit admit may initialize. Kernel writer locking is shared with the
    journal; immutable history is never repaired, rewritten or initialized by status.
    """
    journal = None
    result: dict[str, object] = {"state": "REJECTED", "result": "NOT_RUN", "exit_code": 2}
    try:
        if operation not in OPERATIONS:
            return result
        context = require_context(admission)
        pin = installed_source(context).installation
        journal = EvidenceJournal(
            Path(pin.store.path), Path(pin.checkpoint.path), context, create=operation == "admit"
        )
        result = _summary(journal)
        if operation in {"admit", "status", "recover", "next"}:
            # next is only a detached preview: no executable release crosses processes.
            if operation == "next" and result["state"] in {"READY", "PENDING"}:
                order = journal.preview()
                result.update(action=order.action, sequence=order.sequence)
            return result
        if operation == "capture":
            if journal.pending is not None or journal.stopped:
                return {**result, "exit_code": 3}
            try:
                order = journal.next()
            except StopIteration:
                return _summary(journal)
            if order.action == "control":
                journal.run_component()
            else:
                from .setup_transport import capture_once

                capture_once(journal)
        else:
            journal.import_capture_file()
        result = _summary(journal)
        if result["state"] in {"STOPPED", "UNKNOWN", "BLOCKED", "INTENT_PENDING", "PENDING"}:
            result["exit_code"] = 3
    except Exception:
        # No exception text/chain or raw private records reach ordinary output.
        if journal is not None:
            result = {**_summary(journal), "exit_code": 3}
    finally:
        if journal is not None:
            journal.close()
    return result
