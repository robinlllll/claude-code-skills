"""JSONL utility module with file locking for the investment system.

Provides safe append-only JSONL operations with:
- portalocker for cross-platform file locking
- Optional Pydantic validation before write
- UTF-8 encoding everywhere (Windows defaults to GBK)
"""

from __future__ import annotations

import json
from pathlib import Path

import portalocker
from pydantic import BaseModel


def safe_jsonl_append(filepath, record, model_class=None) -> None:
    """Append a record to a JSONL file with exclusive file locking.

    Args:
        filepath: str or Path to .jsonl file
        record: dict or Pydantic model instance to append
        model_class: optional Pydantic BaseModel class. If provided:
            - If record is already an instance of model_class, calls .to_jsonl_dict()
            - If record is a raw dict, validates by constructing the model first
            Raises ValueError if validation fails.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    if model_class is not None:
        if isinstance(record, model_class):
            # Already a model instance — serialize via to_jsonl_dict if available
            if hasattr(record, "to_jsonl_dict"):
                data = record.to_jsonl_dict()
            else:
                data = json.loads(record.model_dump_json())
        elif isinstance(record, dict):
            # Raw dict — validate by constructing the model (raises ValidationError on failure)
            try:
                instance = model_class(**record)
            except Exception as exc:
                raise ValueError(
                    f"Validation failed against {model_class.__name__}: {exc}"
                ) from exc
            if hasattr(instance, "to_jsonl_dict"):
                data = instance.to_jsonl_dict()
            else:
                data = json.loads(instance.model_dump_json())
        else:
            raise ValueError(
                f"record must be a dict or {model_class.__name__} instance, "
                f"got {type(record).__name__}"
            )
    elif isinstance(record, BaseModel):
        # No model_class specified but record is a Pydantic model
        if hasattr(record, "to_jsonl_dict"):
            data = record.to_jsonl_dict()
        else:
            data = json.loads(record.model_dump_json())
    else:
        data = record

    line = json.dumps(data, ensure_ascii=False, default=str) + "\n"

    with portalocker.Lock(
        str(filepath), "a", encoding="utf-8", flags=portalocker.LOCK_EX
    ) as fh:
        fh.write(line)


def read_jsonl(filepath, filter_fn=None) -> list[dict]:
    """Read all records from a JSONL file.

    Args:
        filepath: str or Path to .jsonl file
        filter_fn: optional callable. If provided, only records where
                   filter_fn(record) is True are included.

    Returns:
        List of dicts. Returns empty list if file does not exist.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return []

    records = []
    with open(filepath, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if filter_fn is None or filter_fn(record):
                records.append(record)
    return records


def query_jsonl(filepath, **kwargs) -> list[dict]:
    """Query a JSONL file by field equality.

    Convenience wrapper around read_jsonl that builds a filter from kwargs.
    The `ticker` field is compared case-insensitively (both sides .upper()).

    Example:
        query_jsonl(path, ticker="celh", failure_type="追涨")

    Returns:
        List of matching dicts.
    """

    def _filter(record: dict) -> bool:
        for key, value in kwargs.items():
            rec_val = record.get(key)
            if key == "ticker":
                if str(rec_val).upper() != str(value).upper():
                    return False
            else:
                if rec_val != value:
                    return False
        return True

    return read_jsonl(filepath, filter_fn=_filter)


def count_jsonl(filepath) -> int:
    """Count non-empty lines in a JSONL file.

    Returns:
        Integer count of non-empty lines. Returns 0 if file does not exist.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return 0

    count = 0
    with open(filepath, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                count += 1
    return count
