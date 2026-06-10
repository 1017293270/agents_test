import pytest

from app.sql_safety import SqlSafetyError, validate_select_sql


def test_allows_single_readonly_select_and_adds_limit_when_missing():
    safe_sql = validate_select_sql("select id, name from customers where status = 'active'")

    assert safe_sql.lower().startswith("select id, name")
    assert "limit 500" in safe_sql.lower()


def test_rejects_multiple_statements():
    with pytest.raises(SqlSafetyError, match="single SELECT"):
        validate_select_sql("select * from users; drop table users")


def test_rejects_non_select_statements():
    with pytest.raises(SqlSafetyError, match="Only SELECT"):
        validate_select_sql("delete from users where id = 1")


def test_preserves_existing_limit_when_present():
    safe_sql = validate_select_sql("select * from orders limit 10", default_limit=500)

    assert safe_sql.lower().endswith("limit 10")
