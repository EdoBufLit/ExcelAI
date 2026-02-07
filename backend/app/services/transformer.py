from __future__ import annotations

from typing import Any

import pandas as pd


SUPPORTED_OPERATIONS = {
    "rename_column",
    "drop_columns",
    "fill_null",
    "cast_type",
    "trim_whitespace",
    "change_case",
    "derive_numeric",
    "filter_rows",
    "sort_rows",
}


class TransformationError(ValueError):
    pass


def _require_columns(df: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise TransformationError(f"Missing columns: {', '.join(missing)}")


def _validate_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    operations = plan.get("operations")
    if not isinstance(operations, list):
        raise TransformationError("Plan must contain an 'operations' list.")
    for operation in operations:
        if not isinstance(operation, dict):
            raise TransformationError("Each operation must be an object.")
        op_type = operation.get("type")
        if op_type not in SUPPORTED_OPERATIONS:
            raise TransformationError(f"Unsupported operation type: {op_type}")
    return operations


def _cast_series(series: pd.Series, dtype: str) -> pd.Series:
    if dtype == "string":
        return series.astype("string")
    if dtype == "int64":
        return pd.to_numeric(series, errors="coerce").astype("Int64")
    if dtype == "float64":
        return pd.to_numeric(series, errors="coerce").astype("float64")
    if dtype == "datetime":
        return pd.to_datetime(series, errors="coerce")
    if dtype == "bool":
        truthy = {"true", "1", "yes", "y", "t"}
        falsy = {"false", "0", "no", "n", "f"}

        def _to_bool(value: Any) -> Any:
            if pd.isna(value):
                return pd.NA
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            text = str(value).strip().lower()
            if text in truthy:
                return True
            if text in falsy:
                return False
            return pd.NA

        return series.map(_to_bool).astype("boolean")
    raise TransformationError("dtype must be one of: string, int64, float64, datetime, bool")


def apply_plan(df: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    operations = _validate_plan(plan)
    transformed = df.copy()

    for operation in operations:
        op_type = operation["type"]

        if op_type == "rename_column":
            source = operation.get("from")
            target = operation.get("to")
            if not source or not target:
                raise TransformationError("rename_column requires 'from' and 'to'.")
            _require_columns(transformed, [source])
            transformed = transformed.rename(columns={source: target})
            continue

        if op_type == "drop_columns":
            columns = operation.get("columns", [])
            if not isinstance(columns, list) or not columns:
                raise TransformationError("drop_columns requires non-empty 'columns'.")
            _require_columns(transformed, columns)
            transformed = transformed.drop(columns=columns)
            continue

        if op_type == "fill_null":
            column = operation.get("column")
            if not isinstance(column, str):
                raise TransformationError("fill_null requires 'column'.")
            _require_columns(transformed, [column])
            transformed.loc[:, column] = transformed[column].fillna(operation.get("value"))
            continue

        if op_type == "cast_type":
            column = operation.get("column")
            dtype = operation.get("dtype")
            if not isinstance(column, str) or not isinstance(dtype, str):
                raise TransformationError("cast_type requires 'column' and 'dtype'.")
            _require_columns(transformed, [column])
            transformed.loc[:, column] = _cast_series(transformed[column], dtype)
            continue

        if op_type == "trim_whitespace":
            columns = operation.get("columns", [])
            if not isinstance(columns, list) or not columns:
                raise TransformationError("trim_whitespace requires non-empty 'columns'.")
            _require_columns(transformed, columns)
            for column in columns:
                transformed.loc[:, column] = transformed[column].map(
                    lambda value: value.strip() if isinstance(value, str) else value
                )
            continue

        if op_type == "change_case":
            columns = operation.get("columns", [])
            case = operation.get("case")
            if not isinstance(columns, list) or not columns:
                raise TransformationError("change_case requires non-empty 'columns'.")
            if case not in {"upper", "lower", "title"}:
                raise TransformationError("change_case.case must be upper, lower, or title.")
            _require_columns(transformed, columns)
            for column in columns:
                if case == "upper":
                    transformed.loc[:, column] = transformed[column].map(
                        lambda value: value.upper() if isinstance(value, str) else value
                    )
                elif case == "lower":
                    transformed.loc[:, column] = transformed[column].map(
                        lambda value: value.lower() if isinstance(value, str) else value
                    )
                else:
                    transformed.loc[:, column] = transformed[column].map(
                        lambda value: value.title() if isinstance(value, str) else value
                    )
            continue

        if op_type == "derive_numeric":
            left_column = operation.get("left_column")
            right_column = operation.get("right_column")
            new_column = operation.get("new_column")
            operator = operation.get("operator")
            round_digits = operation.get("round")

            if not all(isinstance(value, str) for value in [left_column, right_column, new_column]):
                raise TransformationError(
                    "derive_numeric requires 'left_column', 'right_column', and 'new_column'."
                )
            if operator not in {"add", "sub", "mul", "div"}:
                raise TransformationError("derive_numeric.operator must be add, sub, mul, or div.")
            _require_columns(transformed, [left_column, right_column])

            left_values = pd.to_numeric(transformed[left_column], errors="coerce")
            right_values = pd.to_numeric(transformed[right_column], errors="coerce")
            if operator == "add":
                output = left_values + right_values
            elif operator == "sub":
                output = left_values - right_values
            elif operator == "mul":
                output = left_values * right_values
            else:
                output = left_values / right_values.replace(0, pd.NA)

            if isinstance(round_digits, int):
                output = output.round(round_digits)
            transformed.loc[:, new_column] = output
            continue

        if op_type == "filter_rows":
            column = operation.get("column")
            comparator = operation.get("comparator")
            value = operation.get("value")
            if not isinstance(column, str) or comparator not in {"eq", "neq", "gt", "gte", "lt", "lte"}:
                raise TransformationError(
                    "filter_rows requires 'column' and comparator in eq, neq, gt, gte, lt, lte."
                )
            _require_columns(transformed, [column])

            series = transformed[column]
            if comparator == "eq":
                transformed = transformed[series == value]
            elif comparator == "neq":
                transformed = transformed[series != value]
            elif comparator == "gt":
                transformed = transformed[pd.to_numeric(series, errors="coerce") > value]
            elif comparator == "gte":
                transformed = transformed[pd.to_numeric(series, errors="coerce") >= value]
            elif comparator == "lt":
                transformed = transformed[pd.to_numeric(series, errors="coerce") < value]
            else:
                transformed = transformed[pd.to_numeric(series, errors="coerce") <= value]
            transformed = transformed.reset_index(drop=True)
            continue

        if op_type == "sort_rows":
            by = operation.get("by", [])
            ascending = operation.get("ascending", True)
            if not isinstance(by, list) or not by:
                raise TransformationError("sort_rows requires non-empty 'by' list.")
            if not isinstance(ascending, bool):
                raise TransformationError("sort_rows.ascending must be boolean.")
            _require_columns(transformed, by)
            transformed = transformed.sort_values(by=by, ascending=ascending).reset_index(drop=True)
            continue

    return transformed
