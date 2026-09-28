"""
The core pipeline: plain-English question -> schema context -> LLM ->
guarded SQL -> DuckDB execution -> structured answer.

Nothing about the sample dataset is hardcoded here -- the only inputs
are the dataset's own profile (built in db.py from whatever CSV was
uploaded) and the user's question.
"""
from __future__ import annotations
import concurrent.futures
import json

from app.config import settings
from app.db import DatasetProfile, TABLE_NAME, get_readonly_connection
from app.llm_client import LLMClient, LLMError
from app.models import QueryResult
from app.sql_guard import validate_sql

SYSTEM_PROMPT = """You are a careful data analyst that writes DuckDB SQL.

You will be given:
- the name of a single table
- its columns, inferred types, null counts, distinct counts, sample values,
  and (where applicable) min/max values
- a question in plain English

Rules:
1. You may ONLY query the table you are given. Never invent columns or tables.
2. Output STRICT JSON matching this schema, nothing else, no markdown fences:
   {
     "answerable": boolean,
     "sql": string or null,       // a single DuckDB SELECT/WITH statement, or null
     "reasoning": string,          // one short sentence on your approach
     "refusal_reason": string or null  // required and non-null if answerable is false
   }
3. If the question cannot be answered from the given schema (e.g. it asks
   about a column/concept that isn't present, like profit when there is no
   cost column, or a time grouping finer than the available date
   resolution), set "answerable" to false, "sql" to null, and explain why
   in "refusal_reason". Do NOT guess or invent data.
4. Prefer explicit column names over SELECT *. Alias computed columns with
   clear names (e.g. total_revenue, order_count).
5. When the question implies revenue/sales and the schema has separate
   quantity and unit-price-like numeric columns, compute revenue as their
   product; use your judgement based on the actual column names/samples
   given, never assume a specific retailer's schema.
6. For "top N" questions, always include an explicit LIMIT.
7. Return ONLY the JSON object.
"""


def _describe_column(col) -> str:
    parts = [f'- "{col.name}" ({col.duckdb_type})']
    parts.append(f"nulls={col.null_count}")
    parts.append(f"distinct={col.distinct_count}")
    if col.min_value is not None or col.max_value is not None:
        parts.append(f"range=[{col.min_value} .. {col.max_value}]")
    if col.sample_values:
        parts.append(f"samples={col.sample_values}")
    return " ".join(parts)


def build_schema_context(profile: DatasetProfile) -> str:
    lines = [
        f"Table name: {TABLE_NAME}",
        f"Row count: {profile.row_count}",
        "Columns:",
    ]
    lines += [_describe_column(c) for c in profile.columns]
    return "\n".join(lines)


def _run_sql_with_timeout(dataset_id: str, sql: str, timeout_s: int):
    con = get_readonly_connection(dataset_id)

    def _run():
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(settings.max_result_rows)
        return cols, rows

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_run)
        try:
            return fut.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            try:
                con.interrupt()
            except Exception:
                pass
            raise TimeoutError(f"Query exceeded {timeout_s}s timeout and was cancelled.")
        finally:
            con.close()


def _format_answer(question: str, columns: list[str], rows: list[tuple]) -> str:
    """Deterministic, non-LLM phrasing of the result -- keeps the reported
    numbers exactly what the SQL engine computed, with zero room for the
    model to hallucinate over real figures."""
    if not rows:
        return "The query ran successfully but returned no rows."
    if len(rows) == 1 and len(columns) == 1:
        return f"{columns[0]}: {rows[0][0]}"
    if len(rows) == 1:
        pairs = ", ".join(f"{c}={v}" for c, v in zip(columns, rows[0]))
        return pairs
    preview = rows[: min(5, len(rows))]
    lines = [", ".join(str(v) for v in r) for r in preview]
    more = f" (+{len(rows) - len(preview)} more rows)" if len(rows) > len(preview) else ""
    return f"Columns: {', '.join(columns)}\n" + "\n".join(lines) + more


def answer_question(
    llm: LLMClient,
    profile: DatasetProfile,
    dataset_id: str,
    question: str,
) -> QueryResult:
    schema_context = build_schema_context(profile)
    user_prompt = f"{schema_context}\n\nQuestion: {question}"

    warnings: list[str] = []
    try:
        parsed = llm.complete_json(SYSTEM_PROMPT, user_prompt)
    except LLMError as e:
        return QueryResult(
            question=question,
            answerable=False,
            refusal_reason=f"LLM error: {e}",
        )

    answerable = bool(parsed.get("answerable"))
    sql = parsed.get("sql")
    refusal_reason = parsed.get("refusal_reason")

    if not answerable or not sql:
        return QueryResult(
            question=question,
            answerable=False,
            refusal_reason=refusal_reason or "The model judged this unanswerable from the given schema.",
        )

    guard = validate_sql(sql, allowed_table=TABLE_NAME)
    if not guard.ok:
        return QueryResult(
            question=question,
            answerable=False,
            refusal_reason=f"Generated SQL failed safety validation: {guard.reason}",
            sql=sql,
        )

    try:
        columns, rows = _run_sql_with_timeout(
            dataset_id, guard.cleaned_sql, settings.query_timeout_seconds
        )
    except TimeoutError as e:
        return QueryResult(
            question=question, answerable=False, sql=guard.cleaned_sql,
            refusal_reason=str(e),
        )
    except Exception as e:
        return QueryResult(
            question=question, answerable=False, sql=guard.cleaned_sql,
            refusal_reason=f"Query execution failed: {e}",
        )

    if len(rows) >= settings.max_result_rows:
        warnings.append(f"Result truncated to first {settings.max_result_rows} rows.")

    rows_jsonable = [[_jsonable(v) for v in r] for r in rows]

    return QueryResult(
        question=question,
        answerable=True,
        answer=_format_answer(question, columns, rows),
        sql=guard.cleaned_sql,
        columns=columns,
        rows=rows_jsonable,
        row_count=len(rows),
        warnings=warnings,
    )


def _jsonable(v):
    try:
        json.dumps(v)
        return v
    except TypeError:
        return str(v)
