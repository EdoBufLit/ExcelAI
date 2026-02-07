from __future__ import annotations

from typing import Any


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _describe_step(operation: dict[str, Any]) -> tuple[str, str, list[str]]:
    op_type = operation.get("type")

    if op_type == "rename_column":
        source = str(operation.get("from", ""))
        target = str(operation.get("to", ""))
        return (
            "Rinomina colonna",
            f"La colonna '{source}' verra rinominata in '{target}'.",
            [source, target],
        )

    if op_type == "drop_columns":
        columns = _as_list(operation.get("columns"))
        return (
            "Rimozione colonne",
            f"Verranno rimosse {len(columns)} colonne dal dataset.",
            columns,
        )

    if op_type == "fill_null":
        column = str(operation.get("column", ""))
        return (
            "Sostituzione valori null",
            f"I valori null in '{column}' verranno sostituiti con un valore di fallback.",
            [column],
        )

    if op_type == "cast_type":
        column = str(operation.get("column", ""))
        dtype = str(operation.get("dtype", ""))
        return (
            "Conversione tipo colonna",
            f"La colonna '{column}' verra convertita in '{dtype}'.",
            [column],
        )

    if op_type == "trim_whitespace":
        columns = _as_list(operation.get("columns"))
        return (
            "Pulizia spazi",
            "Gli spazi iniziali/finali verranno rimossi nelle colonne indicate.",
            columns,
        )

    if op_type == "change_case":
        columns = _as_list(operation.get("columns"))
        case = str(operation.get("case", ""))
        return (
            "Cambio maiuscole/minuscole",
            f"Il testo verra convertito in formato '{case}' nelle colonne indicate.",
            columns,
        )

    if op_type == "derive_numeric":
        left = str(operation.get("left_column", ""))
        right = str(operation.get("right_column", ""))
        new = str(operation.get("new_column", ""))
        operator = str(operation.get("operator", ""))
        return (
            "Calcolo nuova colonna numerica",
            f"Sara creata '{new}' usando operazione '{operator}' tra '{left}' e '{right}'.",
            [left, right, new],
        )

    if op_type == "filter_rows":
        column = str(operation.get("column", ""))
        comparator = str(operation.get("comparator", ""))
        return (
            "Filtro righe",
            f"Le righe verranno filtrate su '{column}' con comparatore '{comparator}'.",
            [column],
        )

    if op_type == "sort_rows":
        columns = _as_list(operation.get("by"))
        ascending = bool(operation.get("ascending", True))
        direction = "crescente" if ascending else "decrescente"
        return (
            "Ordinamento righe",
            f"Le righe verranno ordinate in modo {direction}.",
            columns,
        )

    return (
        "Operazione",
        "Trasformazione prevista dal piano.",
        [],
    )


def explain_plan(plan: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[str]]:
    operations = plan.get("operations")
    if not isinstance(operations, list) or not operations:
        return "Nessuna modifica prevista: il piano non contiene step.", [], []

    steps: list[dict[str, Any]] = []
    impacted_columns: list[str] = []
    seen = set()

    for operation in operations:
        if not isinstance(operation, dict):
            continue
        title, description, columns = _describe_step(operation)
        valid_columns = [column for column in columns if column]
        steps.append(
            {
                "title": title,
                "description": description,
                "columns": valid_columns,
            }
        )
        for column in valid_columns:
            if column not in seen:
                seen.add(column)
                impacted_columns.append(column)

    summary = (
        f"Il piano applichera {len(steps)} step e coinvolgera {len(impacted_columns)} colonne."
        if steps
        else "Nessuna modifica prevista: il piano non contiene step validi."
    )
    return summary, steps, impacted_columns
