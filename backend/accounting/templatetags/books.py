from decimal import Decimal

from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def amount(value, blank_zero=False):
    """1234.5 -> "1,234.50"; negatives in brackets, as accountants write them: (1,234.50)."""
    if value in (None, ""):
        return ""
    value = Decimal(value)
    if blank_zero and value == 0:
        return ""
    if value < 0:
        return format_html('<span class="neg">({})</span>', f"{-value:,.2f}")
    return f"{value:,.2f}"
