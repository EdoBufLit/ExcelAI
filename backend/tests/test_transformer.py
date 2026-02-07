import pandas as pd
import pytest

from app.services.transformer import TransformationError, apply_plan


def test_apply_plan_happy_path() -> None:
    source = pd.DataFrame(
        {
            "name": [" anna ", "mario ", None],
            "amount": [10, 20, 30],
            "tax": [1, 2, 3],
        }
    )
    plan = {
        "operations": [
            {"type": "trim_whitespace", "columns": ["name"]},
            {"type": "change_case", "columns": ["name"], "case": "title"},
            {"type": "derive_numeric", "left_column": "amount", "right_column": "tax", "new_column": "gross", "operator": "add"},
            {"type": "sort_rows", "by": ["gross"], "ascending": False},
        ]
    }

    result = apply_plan(source, plan)
    assert list(result.columns) == ["name", "amount", "tax", "gross"]
    assert result.iloc[0]["gross"] == 33
    assert result.iloc[1]["name"] == "Mario"


def test_apply_plan_rejects_unsupported_operation() -> None:
    source = pd.DataFrame({"a": [1, 2]})
    bad_plan = {"operations": [{"type": "execute_python", "code": "print(1)"}]}
    with pytest.raises(TransformationError):
        apply_plan(source, bad_plan)
