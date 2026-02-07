from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from app.services.transformer import SUPPORTED_OPERATIONS


SYSTEM_PROMPT = """You are an expert data transformation planner.
Return ONLY valid JSON in this exact structure:
{
  "needs_clarification": false,
  "clarification_question": null,
  "operations": [
    {
      "type": "operation_name",
      "...": "operation specific fields"
    }
  ]
}

Rules:
- Use only supported operation types.
- Never include code, Python expressions, SQL, or freeform text.
- Keep plans minimal and deterministic.
- If the request is ambiguous or missing critical details, set:
  - "needs_clarification": true
  - "clarification_question": a single direct question with concrete options
  - "operations": []
- Example clarification question:
  "Intendi raggruppare per cliente o per data?"

Supported operations:
- rename_column: {"type":"rename_column","from":"old","to":"new"}
- drop_columns: {"type":"drop_columns","columns":["col_a","col_b"]}
- fill_null: {"type":"fill_null","column":"col","value":"fallback"}
- cast_type: {"type":"cast_type","column":"col","dtype":"string|int64|float64|datetime|bool"}
- trim_whitespace: {"type":"trim_whitespace","columns":["col"]}
- change_case: {"type":"change_case","columns":["col"],"case":"upper|lower|title"}
- derive_numeric: {"type":"derive_numeric","left_column":"a","right_column":"b","new_column":"c","operator":"add|sub|mul|div","round":2}
- filter_rows: {"type":"filter_rows","column":"col","comparator":"eq|neq|gt|gte|lt|lte","value":100}
- sort_rows: {"type":"sort_rows","by":["col"],"ascending":true}
"""


class LLMConfigurationError(RuntimeError):
    pass


class LLMProviderRequestError(RuntimeError):
    pass


class LLMPlanner:
    def __init__(
        self,
        provider: str,
        *,
        openai_api_key: str | None,
        openai_model: str,
        openai_base_url: str | None,
        kimi_api_key: str | None,
        kimi_model: str,
        kimi_base_url: str,
    ) -> None:
        normalized_provider = provider.strip().lower() if provider else "openai"
        self._provider = normalized_provider if normalized_provider in {"openai", "kimi"} else "openai"

        if self._provider == "kimi":
            self._api_key = kimi_api_key
            self._model = kimi_model
            self._base_url = kimi_base_url
            self._client = OpenAI(api_key=kimi_api_key, base_url=kimi_base_url) if kimi_api_key else None
        else:
            self._api_key = openai_api_key
            self._model = openai_model
            self._base_url = openai_base_url
            self._client = OpenAI(api_key=openai_api_key, base_url=openai_base_url) if openai_api_key else None

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str | None:
        return self._base_url

    def create_plan(self, prompt: str, analysis: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        if self._client is None:
            if self._provider == "kimi":
                raise LLMConfigurationError("Missing KIMI_API_KEY")
            return self._fallback_plan(prompt, analysis), [
                "OPENAI_API_KEY non configurata: uso planner euristico locale.",
            ]

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0.1,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "prompt": prompt,
                                "dataset_analysis": analysis,
                            }
                        ),
                    },
                ],
            )
            content = response.choices[0].message.content or '{"operations":[]}'
            plan = self._sanitize_plan_payload(json.loads(content))
            return plan, []
        except Exception as error:  # pragma: no cover - external API variability
            if self._provider == "kimi":
                raise LLMProviderRequestError(f"Kimi planner request failed: {error}") from error
            fallback = self._fallback_plan(prompt, analysis)
            return fallback, [f"Errore LLM, fallback locale: {error}"]

    def _fallback_plan(self, prompt: str, analysis: dict[str, Any]) -> dict[str, Any]:
        prompt_low = prompt.lower()
        string_columns = [
            column["name"]
            for column in analysis.get("columns", [])
            if "object" in column.get("dtype", "") or "string" in column.get("dtype", "")
        ]
        numeric_columns = [
            column["name"]
            for column in analysis.get("columns", [])
            if any(tag in column.get("dtype", "") for tag in ("int", "float"))
        ]

        operations: list[dict[str, Any]] = []
        if any(keyword in prompt_low for keyword in ("trim", "spazi", "whitespace")) and string_columns:
            operations.append({"type": "trim_whitespace", "columns": string_columns[:3]})

        if any(keyword in prompt_low for keyword in ("uppercase", "maiusc", "upper")) and string_columns:
            operations.append({"type": "change_case", "columns": string_columns[:2], "case": "upper"})

        sort_match = re.search(r"sort(?: by)? ([a-zA-Z0-9_ ]+)", prompt_low)
        if sort_match:
            raw_column = sort_match.group(1).strip()
            for column in analysis.get("columns", []):
                if column["name"].lower() == raw_column:
                    operations.append({"type": "sort_rows", "by": [column["name"]], "ascending": True})
                    break

        if "somma" in prompt_low or "sum" in prompt_low:
            if len(numeric_columns) >= 2:
                operations.append(
                    {
                        "type": "derive_numeric",
                        "left_column": numeric_columns[0],
                        "right_column": numeric_columns[1],
                        "new_column": "sum_result",
                        "operator": "add",
                        "round": 2,
                    }
                )

        return self._sanitize_plan_payload(
            {
                "needs_clarification": False,
                "clarification_question": None,
                "operations": operations,
            }
        )

    @staticmethod
    def _sanitize_plan_payload(raw_plan: Any) -> dict[str, Any]:
        if not isinstance(raw_plan, dict):
            return {
                "needs_clarification": False,
                "clarification_question": None,
                "operations": [],
            }

        operations = raw_plan.get("operations")
        needs_clarification = bool(raw_plan.get("needs_clarification", False))
        raw_question = raw_plan.get("clarification_question")
        question = raw_question.strip() if isinstance(raw_question, str) else None
        if not isinstance(operations, list):
            operations = []

        safe_operations: list[dict[str, Any]] = []
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            op_type = operation.get("type")
            if op_type not in SUPPORTED_OPERATIONS:
                continue
            safe_operations.append(operation)

        if needs_clarification:
            return {
                "needs_clarification": True,
                "clarification_question": question
                or "Richiesta ambigua. Puoi chiarire meglio il criterio desiderato?",
                "operations": [],
            }

        return {
            "needs_clarification": False,
            "clarification_question": None,
            "operations": safe_operations,
        }
