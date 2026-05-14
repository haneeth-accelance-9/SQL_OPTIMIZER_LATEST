"""
Unit tests for pure functions in optimizer.services.excel_processor.
No DB required.
"""
import pytest
import pandas as pd

from optimizer.services.excel_processor import normalize_columns


class TestNormalizeColumns:
    def test_lowercases_column_names(self):
        df = pd.DataFrame(columns=["Server_Name", "Product_Family"])
        result = normalize_columns(df)
        assert list(result.columns) == ["server_name", "product_family"]

    def test_strips_whitespace_from_columns(self):
        df = pd.DataFrame(columns=["  Server  ", "  Product  "])
        result = normalize_columns(df)
        assert list(result.columns) == ["server", "product"]

    def test_replaces_spaces_with_underscores(self):
        df = pd.DataFrame(columns=["Server Name", "Product Family"])
        result = normalize_columns(df)
        assert list(result.columns) == ["server_name", "product_family"]

    def test_removes_parentheses(self):
        df = pd.DataFrame(columns=["Cost (EUR)", "Usage (%)"])
        result = normalize_columns(df)
        assert list(result.columns) == ["cost_eur", "usage_%"]

    def test_does_not_modify_original_dataframe(self):
        df = pd.DataFrame(columns=["Server Name"])
        original_columns = list(df.columns)
        normalize_columns(df)
        assert list(df.columns) == original_columns

    def test_empty_dataframe_columns(self):
        df = pd.DataFrame()
        result = normalize_columns(df)
        assert len(result.columns) == 0

    def test_data_rows_preserved(self):
        df = pd.DataFrame({"Server Name": ["srv1", "srv2"], "Cost (EUR)": [100, 200]})
        result = normalize_columns(df)
        assert list(result["server_name"]) == ["srv1", "srv2"]
        assert list(result["cost_eur"]) == [100, 200]

    def test_multiple_spaces_replaced_with_multiple_underscores(self):
        df = pd.DataFrame(columns=["A  B"])
        result = normalize_columns(df)
        assert list(result.columns) == ["a__b"]
