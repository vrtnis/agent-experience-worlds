from __future__ import annotations

from typing import Any


TEMPLATES = {
    "missing_audit_log": [
        ("require_audit_log", "Repeat the task for {subject}, but fail unless the audit log names the record and action."),
        ("extra_required_step", "Resolve {subject} and add an audit entry before any close or matter status update."),
        ("multi_table_update", "Complete the {family} workflow for {subject} and prove it with both state updates and audit evidence."),
        ("distractor_records", "Find the correct {family} record for {subject} among distractors, then write a complete audit log."),
        ("audit_log_edge_case", "Handle {subject} where the state update is correct only if the audit log contains the source record."),
    ],
    "missing_citation": [
        ("require_citation", "Find the relevant clause for {subject} and attach a citation with the exact document span."),
        ("amendment_conflict", "Use the amended language for {subject}, not the original agreement, and attach citation evidence."),
        ("multi_clause_citation", "Create all required records for {subject} and attach citations to each source-backed record."),
        ("distractor_documents", "Find {subject} across multiple documents and cite the document that actually controls the answer."),
        ("citation_edge_case", "Extract {subject} and fail unless the citation quote exactly matches the saved document span."),
    ],
    "bad_calculation": [
        ("date_edge_case", "Calculate the deadline for {subject} where the relevant date is stated in prose."),
        ("amount_edge_case", "Calculate the reconciliation amount for {subject} with a same-amount distractor present."),
        ("versioned_date", "Calculate the deadline for {subject} using the amendment rather than the original agreement."),
        ("tolerance_check", "Resolve {subject} and verify the final variance is zero within tolerance."),
        ("multi_step_calculation", "Complete {subject} after deriving the date or amount from multiple records."),
    ],
}

DEFAULT_TEMPLATES = [
    ("retry_targeted", "Retry {subject} with explicit evidence for every state change."),
    ("distractor_records", "Complete {subject} while ignoring similarly named distractor records."),
    ("workflow_completion", "Complete the full {family} workflow for {subject}, including final evidence checks."),
]


def generate_followups(
    world_id: str,
    task: dict[str, Any],
    verifier_result: dict[str, Any],
    count: int = 5,
) -> list[dict[str, Any]]:
    failure_type = verifier_result.get("failure_type") or "unknown_failure"
    templates = TEMPLATES.get(failure_type, DEFAULT_TEMPLATES)
    subject = _subject_for_task(world_id, task)
    family = task.get("family", "workflow").replace("_", " ")
    followups = []
    for index, (mutation_type, prompt_template) in enumerate(templates[:count], start=1):
        followups.append(
            {
                "id": f"{task['id']}__{failure_type}__{index}",
                "world": world_id,
                "parent_task_id": task["id"],
                "failure_type": failure_type,
                "mutation_type": mutation_type,
                "prompt": prompt_template.format(subject=subject, family=family),
            }
        )
    return followups


def _subject_for_task(world_id: str, task: dict[str, Any]) -> str:
    task_id = task["id"]
    if world_id == "ledger":
        if "vega" in task_id:
            return "Vega Analytics payment matching"
        return "Orion Office Supply duplicate payment"
    if world_id == "contracts":
        if "renewal" in task_id:
            return "the Apex/Northstar renewal notice deadline"
        if "termination" in task_id:
            return "the Apex/Northstar amended termination clause"
        return "the Apex/Northstar governing law clause"
    return task.get("prompt", "the workflow")
