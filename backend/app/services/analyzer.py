from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from app.models import ColumnProfile, DatasetAnalysis


def to_json_safe(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, (pd.Timedelta,)):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    return value


def build_preview(df: pd.DataFrame, rows: int) -> list[dict[str, Any]]:
    preview_df = df.head(rows).copy()
    records: list[dict[str, Any]] = []
    for _, row in preview_df.iterrows():
        record = {str(column): to_json_safe(row[column]) for column in preview_df.columns}
        records.append(record)
    return records


def build_analysis(df: pd.DataFrame, preview_rows: int) -> DatasetAnalysis:
    columns: list[ColumnProfile] = []
    for column in df.columns:
        series = df[column]
        samples = [to_json_safe(item) for item in series.dropna().head(3).tolist()]
        columns.append(
            ColumnProfile(
                name=str(column),
                dtype=str(series.dtype),
                null_count=int(series.isna().sum()),
                non_null_count=int(series.notna().sum()),
                sample_values=samples,
            )
        )

    return DatasetAnalysis(
        row_count=int(df.shape[0]),
        column_count=int(df.shape[1]),
        columns=columns,
        preview=build_preview(df, preview_rows),
    )


def analysis_for_llm(analysis: DatasetAnalysis) -> dict[str, Any]:
    return {
        "row_count": analysis.row_count,
        "column_count": analysis.column_count,
        "columns": [
            {
                "name": column.name,
                "dtype": column.dtype,
                "null_count": column.null_count,
                "sample_values": column.sample_values,
            }
            for column in analysis.columns
        ],
        "preview": analysis.preview,
    }
