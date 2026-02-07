from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    null_count: int
    non_null_count: int
    sample_values: list[Any] = Field(default_factory=list)


class DatasetAnalysis(BaseModel):
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    preview: list[dict[str, Any]]


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    analysis: DatasetAnalysis


class PlanRequest(BaseModel):
    file_id: str = Field(min_length=8, max_length=64)
    prompt: str = Field(min_length=3, max_length=3000)
    user_id: str = Field(min_length=2, max_length=128)


class PlanResponse(BaseModel):
    type: Literal["plan"] = "plan"
    plan: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class ClarifyResponse(BaseModel):
    type: Literal["clarify"] = "clarify"
    question: str
    choices: list[str] = Field(default_factory=list)
    clarify_id: str


PlanUnion = PlanResponse | ClarifyResponse


class ClarifyRequest(BaseModel):
    file_id: str = Field(min_length=8, max_length=64)
    prompt: str = Field(min_length=3, max_length=3000)
    clarify_id: str = Field(min_length=8, max_length=128)
    answer: str = Field(min_length=1, max_length=3000)


class ApplyRequest(BaseModel):
    file_id: str = Field(min_length=8, max_length=64)
    user_id: str = Field(min_length=2, max_length=128)
    plan: dict[str, Any]
    output_format: Literal["csv", "xlsx"] = "xlsx"


class PreviewRequest(BaseModel):
    file_id: str = Field(min_length=8, max_length=64)
    plan: dict[str, Any]


class PreviewStep(BaseModel):
    title: str
    description: str
    columns: list[str] = Field(default_factory=list)


class PreviewResponse(BaseModel):
    summary: str
    steps: list[PreviewStep]
    impacted_columns: list[str] = Field(default_factory=list)
    analysis: DatasetAnalysis
    preview_available: bool


class ApplyResponse(BaseModel):
    result_id: str
    output_format: Literal["csv", "xlsx"]
    analysis: DatasetAnalysis
    usage_count: int
    remaining_uses: int


class UsageResponse(BaseModel):
    user_id: str
    usage_count: int
    remaining_uses: int
    limit: int
