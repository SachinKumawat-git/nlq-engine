from app.db import ingest_csv
from app.nl_query import answer_question, build_schema_context


class FakeLLM:
    """Deterministic stand-in for a real LLM so pipeline tests don't need
    a running Ollama server."""

    def __init__(self, response: dict):
        self.response = response
        self.last_prompt = None

    def complete_json(self, system, user):
        self.last_prompt = user
        return self.response


def test_answerable_question_executes_and_formats(sample_csv_path):
    profile = ingest_csv(sample_csv_path, "sample.csv")
    fake = FakeLLM({
        "answerable": True,
        "sql": "SELECT item, SUM(qty * price) AS revenue FROM dataset GROUP BY item ORDER BY revenue DESC LIMIT 10",
        "reasoning": "sum qty*price grouped by item",
        "refusal_reason": None,
    })
    result = answer_question(fake, profile, profile.dataset_id, "Top products by revenue")
    assert result.answerable
    assert result.columns == ["item", "revenue"]
    assert result.row_count == 3
    assert "revenue" in result.answer.lower() or result.rows


def test_model_refusal_is_respected(sample_csv_path):
    profile = ingest_csv(sample_csv_path, "sample.csv")
    fake = FakeLLM({
        "answerable": False,
        "sql": None,
        "reasoning": "no profit/cost column exists",
        "refusal_reason": "The dataset has no cost column, so profit cannot be computed.",
    })
    result = answer_question(fake, profile, profile.dataset_id, "What was our profit margin?")
    assert not result.answerable
    assert "cost" in result.refusal_reason.lower()


def test_unsafe_sql_from_model_is_blocked(sample_csv_path):
    profile = ingest_csv(sample_csv_path, "sample.csv")
    fake = FakeLLM({
        "answerable": True,
        "sql": "DROP TABLE dataset",
        "reasoning": "bad",
        "refusal_reason": None,
    })
    result = answer_question(fake, profile, profile.dataset_id, "delete everything")
    assert not result.answerable
    assert "safety validation" in result.refusal_reason.lower()


def test_schema_context_has_no_hardcoded_retail_terms(sample_csv_path):
    profile = ingest_csv(sample_csv_path, "sample.csv")
    ctx = build_schema_context(profile)
    # generic column names from THIS csv should appear...
    assert "qty" in ctx and "price" in ctx
    # ...but nothing retailer-specific should be baked in by the builder itself
    assert "StockCode" not in ctx and "InvoiceNo" not in ctx
