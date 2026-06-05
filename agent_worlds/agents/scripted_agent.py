from __future__ import annotations

from typing import Any, Protocol


class ToolCaller(Protocol):
    def call(self, tool_name: str, **arguments: Any) -> dict[str, Any]:
        ...


def run(world_id: str, task: dict[str, Any], tools: ToolCaller) -> None:
    if world_id == "ledger":
        _run_ledger(task, tools)
        return
    if world_id == "contracts":
        _run_contracts(task, tools)
        return
    raise ValueError(f"Unsupported scripted world: {world_id}")


def _run_ledger(task: dict[str, Any], tools: ToolCaller) -> None:
    task_id = task["id"]
    if task_id in {"duplicate_payment", "duplicate_payment_missing_audit"}:
        tools.call("search_vendors", name="Orion")
        tools.call("search_payments", vendor_id="ven_orion")
        tools.call(
            "flag_duplicate_payment",
            payment_id="pay_orion_002",
            duplicate_of_payment_id="pay_orion_001",
        )
        if task_id != "duplicate_payment_missing_audit":
            tools.call(
                "write_audit_log",
                task_id=task_id,
                action="flag_duplicate_payment",
                record_id="pay_orion_002",
                summary="Flagged duplicate payment for Orion Office Supply against pay_orion_001.",
            )
        return

    if task_id == "match_vega_payment":
        tools.call("search_vendors", name="Vega")
        tools.call("search_payments", vendor_id="ven_vega", status="unmatched")
        tools.call("search_invoices", vendor_id="ven_vega", status="open")
        tools.call("match_payment_to_invoice", payment_id="pay_vega_001", invoice_id="inv_vega_2001")
        tools.call(
            "write_audit_log",
            task_id=task_id,
            action="match_payment",
            record_id="pay_vega_001",
            summary="Matched Vega Analytics payment pay_vega_001 to invoice inv_vega_2001.",
        )
        return

    raise ValueError(f"Unsupported scripted ledger task: {task_id}")


def _run_contracts(task: dict[str, Any], tools: ToolCaller) -> None:
    task_id = task["id"]
    if task_id == "governing_law":
        tools.call("search_documents", query="governing law")
        tools.call("get_document", document_id="doc_apex_original")
        clause = tools.call(
            "extract_clause",
            document_id="doc_apex_original",
            clause_type="governing_law",
        )
        tools.call(
            "attach_citation",
            source_table="clauses",
            source_id=clause["clause_id"],
            document_id=clause["document_id"],
            start_char=clause["start_char"],
            end_char=clause["end_char"],
            quote=clause["text"],
        )
        tools.call(
            "write_audit_log",
            task_id=task_id,
            action="extract_governing_law",
            record_id=clause["clause_id"],
            summary="Extracted governing law clause and attached citation evidence.",
        )
        return

    if task_id == "renewal_deadline":
        tools.call("search_documents", query="renewal notice")
        clause = tools.call(
            "extract_clause",
            document_id="doc_apex_original",
            clause_type="renewal_notice",
        )
        obligation = tools.call(
            "create_obligation",
            contract_id=clause["contract_id"],
            obligation_type="renewal_notice",
            description="Renewal notice must be delivered no later than May 1, 2026.",
            source_clause_id=clause["clause_id"],
        )
        tools.call(
            "create_deadline",
            obligation_id=obligation["obligation_id"],
            due_date="2026-05-01",
            description="Renewal notice deadline from Section 8.",
        )
        tools.call(
            "attach_citation",
            source_table="obligations",
            source_id=obligation["obligation_id"],
            document_id=clause["document_id"],
            start_char=clause["start_char"],
            end_char=clause["end_char"],
            quote=clause["text"],
        )
        tools.call(
            "write_audit_log",
            task_id=task_id,
            action="create_renewal_deadline",
            record_id=obligation["obligation_id"],
            summary="Created renewal notice obligation and 2026-05-01 deadline with citation evidence.",
        )
        return

    if task_id == "termination_missing_citation":
        tools.call("search_documents", query="termination")
        tools.call(
            "compare_versions",
            original_document_id="doc_apex_original",
            amended_document_id="doc_apex_amendment_1",
            topic="termination",
        )
        clause = tools.call(
            "extract_clause",
            document_id="doc_apex_amendment_1",
            clause_type="termination",
        )
        tools.call(
            "write_audit_log",
            task_id=task_id,
            action="extract_termination_amendment",
            record_id=clause["clause_id"],
            summary="Extracted amended termination language from Amendment No. 1 but did not attach citation.",
        )
        return

    raise ValueError(f"Unsupported scripted contract task: {task_id}")
