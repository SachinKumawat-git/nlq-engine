from app.sql_guard import validate_sql


def test_allows_plain_select():
    r = validate_sql("SELECT * FROM dataset LIMIT 10", allowed_table="dataset")
    assert r.ok


def test_allows_cte():
    r = validate_sql(
        "WITH t AS (SELECT * FROM dataset) SELECT COUNT(*) FROM t",
        allowed_table="dataset",
    )
    assert r.ok


def test_blocks_drop():
    r = validate_sql("DROP TABLE dataset", allowed_table="dataset")
    assert not r.ok


def test_blocks_insert():
    r = validate_sql("INSERT INTO dataset VALUES (1,2,3)", allowed_table="dataset")
    assert not r.ok


def test_blocks_delete():
    r = validate_sql("DELETE FROM dataset WHERE 1=1", allowed_table="dataset")
    assert not r.ok


def test_blocks_multi_statement():
    r = validate_sql("SELECT 1; DROP TABLE dataset", allowed_table="dataset")
    assert not r.ok


def test_blocks_unknown_table():
    r = validate_sql("SELECT * FROM secrets", allowed_table="dataset")
    assert not r.ok


def test_blocks_pragma_attach():
    r = validate_sql("ATTACH '/etc/passwd' AS x", allowed_table="dataset")
    assert not r.ok


def test_strips_comments_and_still_validates():
    r = validate_sql(
        "-- get top rows\nSELECT * FROM dataset LIMIT 5 -- trailing",
        allowed_table="dataset",
    )
    assert r.ok


def test_rejects_empty():
    r = validate_sql("   ", allowed_table="dataset")
    assert not r.ok
