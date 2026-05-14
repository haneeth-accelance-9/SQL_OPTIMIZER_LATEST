"""
Unit tests for optimizer.templatetags.optimizer_filters.
Pure function tests — no DB required.
"""
import pytest

from optimizer.templatetags.optimizer_filters import eu_currency


class TestEuCurrency:
    def test_integer_value(self):
        result = eu_currency(1000)
        assert result == "1.000,00 €"

    def test_float_value(self):
        result = eu_currency(1234.56)
        assert result == "1.234,56 €"

    def test_string_number(self):
        result = eu_currency("28558944")
        assert result == "28.558.944,00 €"

    def test_string_float_number(self):
        result = eu_currency("1234.56")
        assert result == "1.234,56 €"

    def test_none_returns_none(self):
        result = eu_currency(None)
        assert result is None

    def test_non_numeric_string_returned_unchanged(self):
        result = eu_currency("N/A")
        assert result == "N/A"

    def test_empty_string_returned_unchanged(self):
        result = eu_currency("")
        assert result == ""

    def test_negative_number(self):
        result = eu_currency(-1500.50)
        assert result == "-1.500,50 €"

    def test_zero(self):
        result = eu_currency(0)
        assert result == "0,00 €"

    def test_large_number(self):
        result = eu_currency(1000000000)
        assert result == "1.000.000.000,00 €"

    def test_result_ends_with_euro_symbol(self):
        result = eu_currency(500)
        assert result.endswith(" €")

    def test_decimal_separator_is_comma(self):
        result = eu_currency(1.5)
        # European format: decimal separator should be comma
        assert "," in result
        # Check it's the decimal comma (before the €)
        numeric_part = result.replace(" €", "")
        assert numeric_part.endswith(",50")

    def test_thousands_separator_is_dot(self):
        result = eu_currency(1000)
        # European thousands separator is a dot
        assert "1.000" in result

    def test_float_zero_point_zero(self):
        result = eu_currency(0.0)
        assert result == "0,00 €"

    def test_list_type_returned_unchanged(self):
        # Lists cannot be converted to float → TypeError → returned as-is
        val = [1, 2, 3]
        result = eu_currency(val)
        assert result is val
