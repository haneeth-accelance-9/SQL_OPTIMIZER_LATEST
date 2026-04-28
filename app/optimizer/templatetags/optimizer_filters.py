from django import template

register = template.Library()


@register.filter
def eu_currency(value):
    """Format a number in European style: 1.234.567,89 €"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    formatted = f"{number:,.2f}"          # e.g. "28,558,944.00"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"           # e.g. "28.558.944,00 €"
