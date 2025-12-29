from typing import Any, Dict, List, Tuple


def extract_schema_columns(schema: Dict[str, Any]) -> Tuple[List[str], bool]:
    columns = [column["name"] for column in schema.get("columns", []) if "name" in column]
    strict_mode = bool(schema.get("strict", False))
    return columns, strict_mode


def validate_bounds(columns: List[Dict[str, Any]], dataframe) -> List[Dict[str, Any]]:
    import pandas as pd

    failures: List[Dict[str, Any]] = []
    for column in columns:
        name = column.get("name")
        if not name or name not in dataframe.columns:
            continue
        min_value = column.get("min")
        max_value = column.get("max")
        if min_value is None and max_value is None:
            continue
        series = pd.to_numeric(dataframe[name], errors="coerce")
        if series.isna().any():
            failures.append({"column": name, "issue": "non_numeric"})
            continue
        if min_value is not None and (series < min_value).any():
            failures.append({"column": name, "issue": "below_min", "min": min_value})
        if max_value is not None and (series > max_value).any():
            failures.append({"column": name, "issue": "above_max", "max": max_value})
    return failures
