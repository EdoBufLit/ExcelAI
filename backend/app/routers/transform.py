from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.models import (
    ApplyRequest,
    ApplyResponse,
    PlanRequest,
    PlanResponse,
    PreviewRequest,
    PreviewResponse,
    UploadResponse,
    UsageResponse,
)
from app.services.analyzer import analysis_for_llm, build_analysis
from app.services.container import ServiceContainer
from app.services.plan_explainer import explain_plan
from app.services.transformer import TransformationError, apply_plan

router = APIRouter(prefix="/api", tags=["transform"])

EMPTY_PLAN_OPERATIONS_ERROR = (
    "Il piano non contiene operazioni. Genera o modifica il piano prima di applicarlo."
)


def _services(request: Request) -> ServiceContainer:
    return request.app.state.services


def _extract_file_size_bytes(services: ServiceContainer, file_id: str) -> int | None:
    try:
        metadata = services.file_store.get_upload_meta(file_id)
        raw_size = metadata.get("file_size_bytes")
        if isinstance(raw_size, int):
            return max(0, raw_size)
        if isinstance(raw_size, str) and raw_size.isdigit():
            return int(raw_size)
        stored_path = metadata.get("stored_path")
        if isinstance(stored_path, str):
            path = Path(stored_path)
            if path.exists():
                return int(path.stat().st_size)
    except Exception:
        return None
    return None


def _clarification_guard(plan: dict[str, Any]) -> str | None:
    needs_clarification = bool(plan.get("needs_clarification", False))
    operations = plan.get("operations")
    has_operations = isinstance(operations, list) and len(operations) > 0
    question = plan.get("clarification_question")

    if needs_clarification or not has_operations:
        if isinstance(question, str) and question.strip():
            return question.strip()
        return "La richiesta e ambigua o incompleta. Specifica meglio il prompt prima di continuare."
    return None


@router.get("/usage/{user_id}", response_model=UsageResponse)
def get_usage(user_id: str, request: Request) -> UsageResponse:
    services = _services(request)
    usage_count = services.usage_limiter.get_usage(user_id)
    remaining = services.usage_limiter.get_remaining(user_id)
    return UsageResponse(
        user_id=user_id,
        usage_count=usage_count,
        remaining_uses=remaining,
        limit=services.usage_limiter.max_uses,
    )


@router.post("/files/upload", response_model=UploadResponse)
def upload_file(request: Request, file: UploadFile = File(...)) -> UploadResponse:
    services = _services(request)
    settings = request.app.state.settings
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    try:
        metadata = services.file_store.save_upload(file)
        df = services.file_store.load_upload_df(metadata["file_id"])
        analysis = build_analysis(df, settings.preview_rows)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Upload failed: {error}") from error
    finally:
        file.file.close()

    return UploadResponse(
        file_id=metadata["file_id"],
        filename=metadata["filename"],
        analysis=analysis,
    )


@router.post("/plan", response_model=PlanResponse)
def generate_plan(payload: PlanRequest, request: Request) -> PlanResponse:
    services = _services(request)
    settings = request.app.state.settings
    try:
        df = services.file_store.load_upload_df(payload.file_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="File not found.") from error
    except Exception as error:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Unable to read source file: {error}") from error

    analysis = build_analysis(df, settings.preview_rows)
    plan_payload, warnings = services.llm_planner.create_plan(payload.prompt, analysis_for_llm(analysis))
    return PlanResponse(
        plan={
            "needs_clarification": bool(plan_payload.get("needs_clarification", False)),
            "clarification_question": plan_payload.get("clarification_question"),
            "operations": plan_payload.get("operations", []),
        },
        warnings=warnings,
        needs_clarification=bool(plan_payload.get("needs_clarification", False)),
        clarification_question=plan_payload.get("clarification_question"),
    )


@router.post("/transform", response_model=ApplyResponse)
def apply_transform(payload: ApplyRequest, request: Request) -> ApplyResponse:
    services = _services(request)
    settings = request.app.state.settings
    started = perf_counter()
    file_size_bytes = _extract_file_size_bytes(services, payload.file_id)
    plan_tier = "free"  # Placeholder until billing tiers are implemented.

    status = "error"
    error_code: str | None = "unknown"
    result: dict[str, Any] | None = None
    usage_count = 0
    remaining = 0
    analysis = None

    try:
        operations = payload.plan.get("operations")
        if not isinstance(operations, list) or len(operations) == 0:
            detail = EMPTY_PLAN_OPERATIONS_ERROR
            clarification_question = payload.plan.get("clarification_question")
            if isinstance(clarification_question, str) and clarification_question.strip():
                detail = f"{detail} {clarification_question.strip()}"
            error_code = "invalid_plan"
            raise HTTPException(status_code=400, detail=detail)

        clarification_error = _clarification_guard(payload.plan)
        if clarification_error:
            error_code = "clarification_required"
            raise HTTPException(status_code=400, detail=clarification_error)

        if not services.usage_limiter.can_consume(payload.user_id):
            error_code = "limit_reached"
            limit = services.usage_limiter.max_uses
            raise HTTPException(status_code=429, detail=f"Free tier limit reached ({limit}/{limit}).")

        source_df = services.file_store.load_upload_df(payload.file_id)
        transformed_df = apply_plan(source_df, payload.plan)
        result = services.file_store.save_result(
            transformed_df,
            source_file_id=payload.file_id,
            output_format=payload.output_format,
        )
        usage_count, remaining = services.usage_limiter.consume(payload.user_id)
        analysis = build_analysis(transformed_df, settings.preview_rows)
        status = "success"
        error_code = None
    except FileNotFoundError as error:
        error_code = "source_not_found"
        raise HTTPException(status_code=404, detail="Source file not found.") from error
    except TransformationError as error:
        error_code = "invalid_plan"
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        error_code = "invalid_request"
        raise HTTPException(status_code=400, detail=str(error)) from error
    except HTTPException as error:
        if error_code == "unknown":
            error_code = f"http_{error.status_code}"
        raise error
    except Exception as error:  # pragma: no cover
        error_code = "internal_error"
        raise HTTPException(status_code=500, detail=f"Transformation failed: {error}") from error
    finally:
        processing_ms = max(0, int((perf_counter() - started) * 1000))
        services.analytics_logger.log_transform_event(
            user_id=payload.user_id,
            plan=payload.plan,
            file_size_bytes=file_size_bytes,
            processing_ms=processing_ms,
            status=status,
            error_code=error_code,
            plan_tier=plan_tier,
            output_format=payload.output_format,
        )

    if result is None or analysis is None:
        raise HTTPException(status_code=500, detail="Transformation result unavailable.")

    return ApplyResponse(
        result_id=result["result_id"],
        output_format=payload.output_format,
        analysis=analysis,
        usage_count=usage_count,
        remaining_uses=remaining,
    )


@router.post("/transform/preview", response_model=PreviewResponse)
def preview_transform(payload: PreviewRequest, request: Request) -> PreviewResponse:
    services = _services(request)

    try:
        clarification_error = _clarification_guard(payload.plan)
        if clarification_error:
            raise HTTPException(status_code=400, detail=clarification_error)

        source_df = services.file_store.load_upload_df(payload.file_id)
        transformed_df = apply_plan(source_df, payload.plan)
        analysis = build_analysis(transformed_df, preview_rows=10)
    except HTTPException as error:
        raise error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Source file not found.") from error
    except TransformationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Preview failed: {error}") from error

    summary, steps, impacted_columns = explain_plan(payload.plan)
    preview_available = len(analysis.preview) > 0
    return PreviewResponse(
        summary=summary,
        steps=steps,
        impacted_columns=impacted_columns,
        analysis=analysis,
        preview_available=preview_available,
    )


@router.get("/results/{result_id}/download")
def download_result(result_id: str, request: Request) -> FileResponse:
    services = _services(request)
    try:
        metadata = services.file_store.get_result_meta(result_id)
        path = Path(metadata["stored_path"])
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Result file not found.") from error

    if not path.exists():
        raise HTTPException(status_code=404, detail="Result file missing from disk.")

    media_type = (
        "text/csv"
        if metadata["output_format"] == "csv"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return FileResponse(
        path=path,
        media_type=media_type,
        filename=path.name,
    )
