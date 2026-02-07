from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from openai import OpenAI

from app.services.transformer import SUPPORTED_OPERATIONS


logger = logging.getLogger(__name__)

GENERIC_CLARIFY_QUESTION = "La richiesta non e ancora chiara. Vuoi procedere con impostazioni consigliate?"
GENERIC_CLARIFY_CHOICES = [
    "Si, usa impostazioni consigliate",
    "No, preferisco specificare meglio",
]

SYSTEM_PROMPT = """You are an expert data transformation planner.
Return ONLY valid JSON and ONLY one of these two shapes:

1) Plan:
{
  "type": "plan",
  "plan": {
    "operations": [
      {
        "type": "operation_name",
        "...": "operation specific fields"
      }
    ]
  }
}

2) Clarify:
{
  "type": "clarify",
  "question": "single concise question",
  "choices": ["option A", "option B"],
  "clarify_id": "optional-id"
}

Rules:
- Return JSON only. No markdown. No prose.
- Use only supported operation types.
- If request is ambiguous or non-deterministic, return type="clarify".
- For type="plan", operations must be non-empty and deterministic.
- For type="clarify", include 2-4 concrete choices when possible.

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
        debug_llm: bool = False,
    ) -> None:
        normalized_provider = provider.strip().lower() if provider else "openai"
        self._provider = normalized_provider if normalized_provider in {"openai", "kimi"} else "openai"
        self._debug_llm = debug_llm

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

    def create_plan(self, prompt: str, analysis: dict[str, Any]) -> dict[str, Any]:
        return self._create_plan_internal(prompt=prompt, analysis=analysis, clarify_id=None, answer=None)

    def create_plan_from_clarification(
        self,
        *,
        prompt: str,
        analysis: dict[str, Any],
        clarify_id: str,
        answer: str,
    ) -> dict[str, Any]:
        return self._create_plan_internal(
            prompt=prompt,
            analysis=analysis,
            clarify_id=clarify_id,
            answer=answer,
        )

    def _create_plan_internal(
        self,
        *,
        prompt: str,
        analysis: dict[str, Any],
        clarify_id: str | None,
        answer: str | None,
    ) -> dict[str, Any]:
        logger.info(
            "LLM plan request start: provider=%s model=%s base_url=%s",
            self._provider,
            self._model,
            self._base_url or "(default)",
        )

        fallback_triggered = False
        if self._client is None:
            fallback_triggered = True
            logger.info(
                "LLM fallback triggered: provider=%s model=%s has_fallback=%s",
                self._provider,
                self._model,
                fallback_triggered,
            )
            return self._clarify_response(
                question=GENERIC_CLARIFY_QUESTION,
                choices=GENERIC_CLARIFY_CHOICES,
                clarify_id=clarify_id,
            )

        llm_raw = ""
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "prompt": prompt,
                                "dataset_analysis": analysis,
                                "clarification": (
                                    {"clarify_id": clarify_id, "answer": answer}
                                    if clarify_id and answer
                                    else None
                                ),
                            }
                        ),
                    },
                ],
                temperature=1 if self._provider == "kimi" else 0.1,
            )
            llm_raw = response.choices[0].message.content or ""
            if self._debug_llm:
                logger.debug("LLM raw output: %s", llm_raw)

            parsed = self._parse_json_payload(llm_raw)
            if not isinstance(parsed, dict):
                fallback_triggered = True
                logger.info(
                    "LLM fallback triggered: provider=%s model=%s has_fallback=%s",
                    self._provider,
                    self._model,
                    fallback_triggered,
                )
                return self._clarify_response(
                    question=GENERIC_CLARIFY_QUESTION,
                    choices=GENERIC_CLARIFY_CHOICES,
                    clarify_id=clarify_id,
                )

            normalized = self._normalize_llm_payload(parsed, llm_raw=llm_raw, clarify_id=clarify_id)
            logger.info(
                "LLM fallback triggered: provider=%s model=%s has_fallback=%s",
                self._provider,
                self._model,
                fallback_triggered,
            )
            return normalized
        except Exception as error:  # pragma: no cover - external API variability
            upstream_status = self._extract_status_code(error)
            logger.warning(
                "LLM planner failure: provider=%s model=%s upstream_status=%s error=%s",
                self._provider,
                self._model,
                upstream_status,
                str(error),
            )
            if upstream_status in {401, 403}:
                fallback_triggered = True
                logger.info(
                    "LLM fallback triggered: provider=%s model=%s has_fallback=%s",
                    self._provider,
                    self._model,
                    fallback_triggered,
                )
                return self._clarify_response(
                    question="Non riesco ad autenticarmi al provider LLM. Vuoi riprovare con un prompt piu specifico?",
                    choices=["Riprova ora", "Modifica prompt"],
                    clarify_id=clarify_id,
                )

            fallback_triggered = True
            logger.info(
                "LLM fallback triggered: provider=%s model=%s has_fallback=%s",
                self._provider,
                self._model,
                fallback_triggered,
            )
            return self._clarify_response(
                question=GENERIC_CLARIFY_QUESTION,
                choices=GENERIC_CLARIFY_CHOICES,
                clarify_id=clarify_id,
            )

    def _normalize_llm_payload(
        self,
        payload: dict[str, Any],
        *,
        llm_raw: str,
        clarify_id: str | None,
    ) -> dict[str, Any]:
        response_type = payload.get("type")
        if response_type == "clarify":
            question = payload.get("question")
            choices = payload.get("choices")
            raw_clarify_id = payload.get("clarify_id")
            normalized_choices = self._normalize_choices(choices)
            return self._clarify_response(
                question=question if isinstance(question, str) and question.strip() else GENERIC_CLARIFY_QUESTION,
                choices=normalized_choices or GENERIC_CLARIFY_CHOICES,
                clarify_id=raw_clarify_id if isinstance(raw_clarify_id, str) else clarify_id,
            )

        if response_type == "plan":
            raw_plan = payload.get("plan")
            sanitized_plan = self._sanitize_plan_payload(raw_plan)
            operations = sanitized_plan.get("operations")
            if isinstance(operations, list) and len(operations) > 0:
                return {
                    "type": "plan",
                    "plan": sanitized_plan,
                    "warnings": [],
                }

            if self._debug_llm:
                logger.debug("LLM returned empty plan payload: %s", self._truncate(llm_raw, limit=500))
            return self._clarify_response(
                question=GENERIC_CLARIFY_QUESTION,
                choices=GENERIC_CLARIFY_CHOICES,
                clarify_id=clarify_id,
            )

        if self._debug_llm:
            logger.debug("LLM payload without valid type: %s", self._truncate(llm_raw, limit=500))
        return self._clarify_response(
            question=GENERIC_CLARIFY_QUESTION,
            choices=GENERIC_CLARIFY_CHOICES,
            clarify_id=clarify_id,
        )

    def _clarify_response(
        self,
        *,
        question: str,
        choices: list[str],
        clarify_id: str | None,
    ) -> dict[str, Any]:
        return {
            "type": "clarify",
            "question": question.strip(),
            "choices": choices[:4],
            "clarify_id": clarify_id.strip() if isinstance(clarify_id, str) and clarify_id.strip() else uuid4().hex,
        }

    @staticmethod
    def _normalize_choices(raw_choices: Any) -> list[str]:
        if not isinstance(raw_choices, list):
            return []
        choices: list[str] = []
        for choice in raw_choices:
            if isinstance(choice, str) and choice.strip():
                choices.append(choice.strip())
        return choices

    @staticmethod
    def _extract_status_code(error: Exception) -> int | None:
        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        response = getattr(error, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status
        return None

    @staticmethod
    def _parse_json_payload(raw_content: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(raw_content)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass

        if not raw_content:
            return None

        start = raw_content.find("{")
        end = raw_content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        candidate = raw_content[start : end + 1]
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    @staticmethod
    def _truncate(value: str, *, limit: int) -> str:
        if len(value) <= limit:
            return value
        return f"{value[:limit]}...(truncated)"

    @staticmethod
    def _sanitize_plan_payload(raw_plan: Any) -> dict[str, Any]:
        if not isinstance(raw_plan, dict):
            return {"operations": []}

        operations = raw_plan.get("operations")
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

        return {"operations": safe_operations}
