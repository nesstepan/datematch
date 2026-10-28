from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icon(name, extra=""):
    """Векторная иконка из спрайта templates/icons.html: {% icon "heart" %} или {% icon "heart" "lg fill" %}."""
    cls = ("ic " + extra).strip()
    return format_html('<svg class="{}" aria-hidden="true" focusable="false"><use href="#{}"></use></svg>', cls, name)
