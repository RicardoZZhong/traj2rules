"""把一次在线执行写成逐任务记录。"""

from __future__ import annotations

from .analyze import count_request_reasons


def task_run_record(domain: str, method: str, result, task_id: str, run_id: str) -> dict:
    reasons = count_request_reasons(result.request_events)
    return {
        "domain": domain,
        "method": method,
        "official_task_id": task_id,
        "run_id": run_id,
        "terminal_score": result.score,
        "success": int(bool(result.success)),
        "termination_reason": result.termination,
        "model_requests": result.requests,
        "request_initial": reasons["initial_proposal"],
        "request_format_retry": reasons["format_retry"],
        "request_conflict_reselection": reasons["conflict_reselection"],
        "pre_call_takeovers": result.precall,
        "post_call_repairs": result.repairs,
        "rejections": result.rejections,
        "env_actions": result.steps,
        "rule_actions": result.rule_actions,
        "rule_actions_confirmed": result.confirmed,
        "programs_started": result.program_started,
        "programs_completed": result.program_completed,
        "programs_aborted": result.program_aborted,
        "terminal_rule_actions": result.terminal_rule_actions,
    }
