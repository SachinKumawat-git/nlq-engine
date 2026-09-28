from app.db import ingest_csv, load_profile, sample_rows, get_readonly_connection


def test_ingest_infers_schema_generically(sample_csv_path):
    profile = ingest_csv(sample_csv_path, "sample.csv")
    assert profile.row_count == 5
    col_names = {c.name for c in profile.columns}
    assert col_names == {"order_id", "item", "qty", "price", "order_date", "country"}

    qty_col = next(c for c in profile.columns if c.name == "qty")
    assert "INT" in qty_col.duckdb_type.upper() or "BIGINT" in qty_col.duckdb_type.upper()

    price_col = next(c for c in profile.columns if c.name == "price")
    assert price_col.min_value is not None and price_col.max_value is not None


def test_profile_round_trips_from_disk(sample_csv_path):
    profile = ingest_csv(sample_csv_path, "sample.csv")
    reloaded = load_profile(profile.dataset_id)
    assert reloaded.row_count == profile.row_count
    assert len(reloaded.columns) == len(profile.columns)


def test_sample_rows_returns_data(sample_csv_path):
    profile = ingest_csv(sample_csv_path, "sample.csv")
    rows = sample_rows(profile.dataset_id, limit=3)
    assert len(rows) == 3
    assert "item" in rows[0]


def test_readonly_connection_rejects_writes(sample_csv_path):
    profile = ingest_csv(sample_csv_path, "sample.csv")
    con = get_readonly_connection(profile.dataset_id)
    try:
        raised = False
        try:
            con.execute("INSERT INTO dataset VALUES (99,'x',1,1.0,'2024-01-01','US')")
        except Exception:
            raised = True
        assert raised, "read-only connection should refuse writes"
    finally:
        con.close()


def test_unknown_dataset_raises():
    import pytest
    with pytest.raises(FileNotFoundError):
        load_profile("does-not-exist")
