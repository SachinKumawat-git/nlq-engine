"""
DuckDB layer: ingests an arbitrary transactional CSV into a DuckDB file
and builds a generic schema context purely from what's in the file.

Nothing here references retailer-specific column names. Everything is
derived at ingest time: column names, inferred types, null rates,
cardinality, sample values, and (for numeric/date columns) min/max.
"""
from __future__ import annotations
import os
import json
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any

import duckdb

from app.config import settings

TABLE_NAME = "dataset"


@dataclass
class ColumnProfile:
    name: str
    duckdb_type: str
    null_count: int
    distinct_count: int
    sample_values: list[Any]
    min_value: Any = None
    max_value: Any = None


@dataclass
class DatasetProfile:
    dataset_id: str
    source_filename: str
    row_count: int
    columns: list[ColumnProfile]
    created_at: float

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _db_path(dataset_id: str) -> str:
    os.makedirs(settings.db_dir, exist_ok=True)
    return os.path.join(settings.db_dir, f"{dataset_id}.duckdb")


def _profile_path(dataset_id: str) -> str:
    os.makedirs(settings.db_dir, exist_ok=True)
    return os.path.join(settings.db_dir, f"{dataset_id}.profile.json")


def ingest_csv(csv_path: str, source_filename: str) -> DatasetProfile:
    """
    Load an arbitrary CSV into a fresh DuckDB file, letting DuckDB's
    read_csv_auto sniff delimiters, header, and column types. Then
    build a profile (schema + samples) purely from the resulting table
    -- this is what makes the app work on a CSV it has never seen.
    """
    dataset_id = uuid.uuid4().hex[:12]
    db_path = _db_path(dataset_id)

    con = duckdb.connect(db_path)
    try:
        # sample_size=-1 scans the whole file for robust type inference;
        # all_varchar fallback isn't used so numeric/date columns stay typed.
        # The path is escaped and inlined rather than passed as a bound
        # parameter: DuckDB table functions (read_csv_auto) don't reliably
        # accept prepared-statement placeholders for their arguments across
        # versions, so we do our own single-quote escaping instead.
        escaped_path = csv_path.replace("'", "''")
        con.execute(
            f"""
            CREATE TABLE {TABLE_NAME} AS
            SELECT * FROM read_csv_auto('{escaped_path}', header=True, sample_size=-1, ignore_errors=False)
            """
        )

        row_count = con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
        if row_count == 0:
            raise ValueError("CSV parsed to zero rows -- check the file has a header and data.")

        schema_rows = con.execute(f"DESCRIBE {TABLE_NAME}").fetchall()
        # DESCRIBE returns: column_name, column_type, null, key, default, extra

        columns: list[ColumnProfile] = []
        for col_name, col_type, *_ in schema_rows:
            safe_col = f'"{col_name}"'
            null_count = con.execute(
                f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE {safe_col} IS NULL"
            ).fetchone()[0]
            distinct_count = con.execute(
                f"SELECT COUNT(DISTINCT {safe_col}) FROM {TABLE_NAME}"
            ).fetchone()[0]
            samples = con.execute(
                f"SELECT DISTINCT {safe_col} FROM {TABLE_NAME} "
                f"WHERE {safe_col} IS NOT NULL LIMIT 5"
            ).fetchall()
            sample_values = [s[0] for s in samples]

            min_v = max_v = None
            if _is_orderable(col_type):
                try:
                    min_v, max_v = con.execute(
                        f"SELECT MIN({safe_col}), MAX({safe_col}) FROM {TABLE_NAME}"
                    ).fetchone()
                except Exception:
                    pass

            columns.append(
                ColumnProfile(
                    name=col_name,
                    duckdb_type=col_type,
                    null_count=null_count,
                    distinct_count=distinct_count,
                    sample_values=_jsonable(sample_values),
                    min_value=_jsonable_scalar(min_v),
                    max_value=_jsonable_scalar(max_v),
                )
            )

        profile = DatasetProfile(
            dataset_id=dataset_id,
            source_filename=source_filename,
            row_count=row_count,
            columns=columns,
            created_at=time.time(),
        )
        with open(_profile_path(dataset_id), "w") as f:
            json.dump(profile.to_dict(), f, default=str)
        return profile
    finally:
        con.close()


def load_profile(dataset_id: str) -> DatasetProfile:
    path = _profile_path(dataset_id)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Unknown dataset_id: {dataset_id}")
    with open(path) as f:
        raw = json.load(f)
    raw["columns"] = [ColumnProfile(**c) for c in raw["columns"]]
    return DatasetProfile(**raw)


def get_readonly_connection(dataset_id: str) -> duckdb.DuckDBPyConnection:
    db_path = _db_path(dataset_id)
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Unknown dataset_id: {dataset_id}")
    # read_only=True is a hard guardrail: even if a mutating statement slipped
    # past sql_guard, DuckDB itself refuses to execute writes on this handle.
    return duckdb.connect(db_path, read_only=True)


def sample_rows(dataset_id: str, limit: int = 5) -> list[dict[str, Any]]:
    con = get_readonly_connection(dataset_id)
    try:
        cur = con.execute(f"SELECT * FROM {TABLE_NAME} LIMIT {int(limit)}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return [dict(zip(cols, _jsonable(r))) for r in rows]
    finally:
        con.close()


def _is_orderable(duckdb_type: str) -> bool:
    t = duckdb_type.upper()
    return any(
        k in t
        for k in (
            "INT", "DECIMAL", "DOUBLE", "FLOAT", "DATE", "TIME",
            "TIMESTAMP", "NUMERIC", "HUGEINT",
        )
    )


def _jsonable_scalar(v: Any) -> Any:
    if v is None:
        return None
    try:
        json.dumps(v, default=str)
        return v
    except TypeError:
        return str(v)


def _jsonable(values: list[Any]) -> list[Any]:
    return [_jsonable_scalar(v) for v in values]
