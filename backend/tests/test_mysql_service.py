from app.mysql_service import row_get


def test_row_get_accepts_information_schema_uppercase_keys():
    row = {"TABLE_NAME": "orders", "COLUMN_NAME": "amount"}

    assert row_get(row, "table_name") == "orders"
    assert row_get(row, "column_name") == "amount"
