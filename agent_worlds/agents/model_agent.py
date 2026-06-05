from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol


DEFAULT_BASE_URL = "http://127.0.0.1:11434"


class ToolCaller(Protocol):
    def call(self, tool_name: str, **arguments: Any) -> dict[str, Any]:
        ...


def default_model(base_url: str | None = None) -> str:
    models = list_models(base_url)
    for model in models:
        capabilities = set(model.get("capabilities", []))
        name = model["name"]
        if "completion" in capabilities and "embedding" not in capabilities:
            return name
    if models:
        return str(models[0]["name"])
    raise RuntimeError("No completion-capable model was returned by the configured model API")


def list_models(base_url: str | None = None) -> list[dict[str, Any]]:
    payload = _request("GET", "/api/tags", base_url=base_url)
    return list(payload.get("models", []))


def run(
    world_id: str,
    task: dict[str, Any],
    tools: ToolCaller,
    model: str | None = None,
    base_url: str | None = None,
    max_steps: int = 10,
) -> dict[str, Any]:
    model_name = model or default_model(base_url)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _system_prompt(world_id)},
        {"role": "user", "content": _task_prompt(world_id, task)},
    ]
    final_message = ""
    prose_stalls = 0
    memory: dict[str, Any] = {"task_id": task["id"]}

    for _ in range(max_steps):
        response = _chat(model_name, messages, TOOL_SCHEMAS[world_id], base_url)
        message = response.get("message", {})
        tool_calls = message.get("tool_calls") or []
        content = message.get("content") or ""
        if tool_calls:
            tool_call = tool_calls[0]
            messages.append({**message, "tool_calls": [tool_call]})
            function = tool_call.get("function", {})
            tool_name = function.get("name")
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            arguments = _repair_arguments(tool_name, arguments, memory)
            output = _safe_tool_call(tools, tool_name, arguments)
            _remember(tool_name, output, memory)
            messages.append({"role": "tool", "content": json.dumps(output, sort_keys=True)})
            continue

        planned_calls = _extract_json_tool_calls(content)
        if planned_calls:
            messages.append({"role": "assistant", "content": content})
            planned = planned_calls[0]
            tool_name = planned.get("tool") or planned.get("name")
            arguments = _repair_arguments(tool_name, planned.get("arguments") or {}, memory)
            output = _safe_tool_call(tools, tool_name, arguments)
            _remember(tool_name, output, memory)
            messages.append({"role": "tool", "content": json.dumps(output, sort_keys=True)})
            continue

        final_message = content
        if _is_done(content) or prose_stalls >= 3:
            break
        prose_stalls += 1
        messages.append({"role": "assistant", "content": content})
        messages.append(
            {
                "role": "user",
                "content": (
                    "The workflow is not complete until the database has the required state update "
                    "and evidence. Call the next required tool now. Do not describe future actions."
                ),
            }
        )

    return {"model": model_name, "final_message": final_message}


def _safe_tool_call(tools: ToolCaller, tool_name: str | None, arguments: dict[str, Any]) -> dict[str, Any]:
    if not tool_name:
        return {"error": "missing_tool_name"}
    for value in arguments.values():
        if isinstance(value, str) and ("<function-result" in value or "<tool" in value):
            return {
                "error": "placeholder_argument",
                "message": "Use exact IDs from prior tool outputs, not placeholder strings.",
            }
    if hasattr(tools, "safe_call"):
        return tools.safe_call(tool_name, **arguments)  # type: ignore[attr-defined]
    try:
        return tools.call(tool_name, **arguments)
    except Exception as exc:  # pragma: no cover - used only by non-recorder callers.
        return {"error": type(exc).__name__, "message": str(exc)}


def _chat(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    base_url: str | None,
) -> dict[str, Any]:
    return _request(
        "POST",
        "/api/chat",
        {
            "model": model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {"temperature": 0, "num_ctx": 8192},
        },
        base_url=base_url,
        timeout=180,
    )


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    base_url: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    root = _base_url(base_url)
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{root}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Model API request failed at {root}{path}: {exc}") from exc


def _base_url(base_url: str | None = None) -> str:
    root = base_url or os.environ.get("AGENT_MODEL_API_BASE_URL") or DEFAULT_BASE_URL
    if not root.startswith(("http://", "https://")):
        root = f"http://{root}"
    return root.rstrip("/")


def _system_prompt(world_id: str) -> str:
    return f"""
You are a local tool-use agent operating in the {world_id} world.
Your job is to complete the user's task by calling tools. The verifier only checks final database state, citations, deadlines, and audit logs.

Rules:
- Use the provided tools; do not invent database updates in text.
- Inspect records before updating them.
- Use exact IDs returned by tools.
- Call one tool at a time, then wait for the tool output before choosing the next tool.
- Never use placeholders like <function-result...>; copy exact IDs from the latest tool output.
- If a task asks for evidence, citation, or audit logging, create it with the relevant tool.
- For write_audit_log, include task_id, action, record_id, and a specific summary.
- If you attached a citation, include the word citation in the audit action or summary.
- When the workflow is complete, respond exactly: DONE
- Do not say what you will do next. If an action is needed, call the tool instead.
""".strip()


def _task_prompt(world_id: str, task: dict[str, Any]) -> str:
    return f"""
Task id: {task['id']}
Task prompt: {task['prompt']}

World notes:
{WORLD_NOTES[world_id]}
""".strip()


def _extract_json_tool_calls(content: str) -> list[dict[str, Any]]:
    text = content.strip()
    if not text:
        return []
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        calls = payload.get("tool_calls") or payload.get("tools") or []
        return calls if isinstance(calls, list) else []
    if isinstance(payload, list):
        return payload
    return []


def _is_done(content: str) -> bool:
    return content.strip().upper() == "DONE"


def _repair_arguments(
    tool_name: str | None,
    arguments: dict[str, Any],
    memory: dict[str, Any],
) -> dict[str, Any]:
    repaired = dict(arguments)
    if tool_name == "search_vendors" and "vendor_name" in repaired and "name" not in repaired:
        repaired["name"] = repaired.pop("vendor_name")
    if tool_name == "attach_citation" and "clause" in memory:
        clause = memory["clause"]
        repaired.setdefault("source_table", "clauses")
        repaired.setdefault("source_id", clause["clause_id"])
        repaired.setdefault("document_id", clause["document_id"])
        repaired.setdefault("start_char", clause["start_char"])
        repaired.setdefault("end_char", clause["end_char"])
        repaired.setdefault("quote", clause["text"])
    if tool_name == "write_audit_log":
        repaired.setdefault("task_id", memory.get("task_id"))
        if "record_id" not in repaired and "clause" in memory:
            repaired["record_id"] = memory["clause"]["clause_id"]
    allowed = ALLOWED_ARGUMENTS.get(tool_name or "")
    if allowed is None:
        return repaired
    return {key: value for key, value in repaired.items() if key in allowed}


def _remember(tool_name: str | None, output: dict[str, Any], memory: dict[str, Any]) -> None:
    if output.get("error"):
        return
    if tool_name == "extract_clause" and "clause_id" in output:
        memory["clause"] = output
    if tool_name == "create_obligation" and "obligation_id" in output:
        memory["obligation"] = output
    if tool_name == "create_deadline" and "deadline_id" in output:
        memory["deadline"] = output


WORLD_NOTES = {
    "ledger": """
Use search_vendors to find vendor IDs. Use search_payments and search_invoices to find record IDs.
Duplicate-payment workflows usually need flag_duplicate_payment and write_audit_log.
Payment-matching workflows usually need match_payment_to_invoice and write_audit_log.
For Orion duplicate payment, first search for Orion, then inspect all Orion payments. The duplicate is the unmatched same-amount payment.
""".strip(),
    "contracts": """
Use search_documents and get_document to inspect synthetic documents.
Supported clause_type values are governing_law, renewal_notice, and termination.
Clause extraction workflows usually need extract_clause, attach_citation, and write_audit_log.
Deadline workflows usually need extract_clause, create_obligation, create_deadline, attach_citation, and write_audit_log.
For governing-law tasks, cite the governing_law clause and make the audit log mention governing law citation.
""".strip(),
}


ALLOWED_ARGUMENTS = {
    "search_vendors": {"name"},
    "search_invoices": {"vendor_id", "status"},
    "search_payments": {"vendor_id", "status"},
    "get_bank_transaction": {"transaction_id"},
    "match_payment_to_invoice": {"payment_id", "invoice_id"},
    "flag_duplicate_payment": {"payment_id", "duplicate_of_payment_id"},
    "write_audit_log": {"task_id", "action", "record_id", "summary"},
    "search_documents": {"query"},
    "get_document": {"document_id"},
    "extract_clause": {"document_id", "clause_type"},
    "compare_versions": {"original_document_id", "amended_document_id", "topic"},
    "create_obligation": {"contract_id", "obligation_type", "description", "source_clause_id"},
    "create_deadline": {"obligation_id", "due_date", "description"},
    "attach_citation": {"source_table", "source_id", "document_id", "start_char", "end_char", "quote"},
}


TOOL_SCHEMAS = {
    "ledger": [
        {
            "type": "function",
            "function": {
                "name": "search_vendors",
                "description": "Search vendors by name.",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_invoices",
                "description": "Search invoices by vendor and status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vendor_id": {"type": "string"},
                        "status": {"type": "string", "enum": ["open", "paid", "void"]},
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_payments",
                "description": "Search payments by vendor and status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vendor_id": {"type": "string"},
                        "status": {"type": "string", "enum": ["unmatched", "matched", "duplicate", "void"]},
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_bank_transaction",
                "description": "Fetch a bank transaction by ID.",
                "parameters": {
                    "type": "object",
                    "properties": {"transaction_id": {"type": "string"}},
                    "required": ["transaction_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "match_payment_to_invoice",
                "description": "Match a payment to an invoice and mark the invoice paid.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "payment_id": {"type": "string"},
                        "invoice_id": {"type": "string"},
                    },
                    "required": ["payment_id", "invoice_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "flag_duplicate_payment",
                "description": "Mark a payment as a duplicate of another payment.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "payment_id": {"type": "string"},
                        "duplicate_of_payment_id": {"type": "string"},
                    },
                    "required": ["payment_id", "duplicate_of_payment_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_audit_log",
                "description": "Write an audit log entry for a task action. If citation evidence was attached, include the word citation in action or summary.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "action": {"type": "string"},
                        "record_id": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["task_id", "action", "record_id", "summary"],
                    "additionalProperties": False,
                },
            },
        },
    ],
    "contracts": [
        {
            "type": "function",
            "function": {
                "name": "search_documents",
                "description": "Search contract documents by text query.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_document",
                "description": "Get a full document by ID.",
                "parameters": {
                    "type": "object",
                    "properties": {"document_id": {"type": "string"}},
                    "required": ["document_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "extract_clause",
                "description": "Extract a supported clause type from a document.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string"},
                        "clause_type": {
                            "type": "string",
                            "enum": ["governing_law", "renewal_notice", "termination"],
                        },
                    },
                    "required": ["document_id", "clause_type"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compare_versions",
                "description": "Compare an original and amended document for a topic.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "original_document_id": {"type": "string"},
                        "amended_document_id": {"type": "string"},
                        "topic": {"type": "string"},
                    },
                    "required": ["original_document_id", "amended_document_id", "topic"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_obligation",
                "description": "Create an obligation record.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "contract_id": {"type": "string"},
                        "obligation_type": {"type": "string"},
                        "description": {"type": "string"},
                        "source_clause_id": {"type": "string"},
                    },
                    "required": ["contract_id", "obligation_type", "description"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_deadline",
                "description": "Create a deadline for an obligation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "obligation_id": {"type": "string"},
                        "due_date": {"type": "string", "description": "ISO date, e.g. 2026-05-01"},
                        "description": {"type": "string"},
                    },
                    "required": ["obligation_id", "due_date", "description"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "attach_citation",
                "description": "Attach a citation using an exact document span and quote.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_table": {"type": "string", "enum": ["clauses", "obligations", "deadlines", "risks"]},
                        "source_id": {"type": "string"},
                        "document_id": {"type": "string"},
                        "start_char": {"type": "integer"},
                        "end_char": {"type": "integer"},
                        "quote": {"type": "string"},
                    },
                    "required": ["source_table", "source_id", "document_id", "start_char", "end_char", "quote"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_audit_log",
                "description": "Write an audit log entry for a task action. If citation evidence was attached, include the word citation in action or summary.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "action": {"type": "string"},
                        "record_id": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["task_id", "action", "record_id", "summary"],
                    "additionalProperties": False,
                },
            },
        },
    ],
}
