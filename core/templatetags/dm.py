from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icon(name, extra=""):
    """Векторная иконка из спрайта templates/icons.html: {% icon "heart" %} или {% icon "heart" "lg fill" %}."""
    cls = ("ic " + extra).strip()
    return format_html('<svg class="{}" aria-hidden="true" focusable="false"><use href="#{}"></use></svg>', cls, name)


ART_VIEWBOX = {"cupid": "-14 0 254 250", "sun": "-100 -100 200 200", "cloud": "0 0 200 100",
               "rose": "0 0 100 130", "mark": "0 0 48 48", "star": "0 0 24 24",
               "p1": "0 0 300 380", "p2": "0 0 300 380", "p3": "0 0 300 380"}


@register.simple_tag
def art(name, extra=""):
    """Нарисованная иллюстрация из templates/art.html: {% art "cupid" "my-class" %}."""
    return format_html('<svg class="art art-{} {}" viewBox="{}" aria-hidden="true" focusable="false"><use href="#art-{}"></use></svg>',
                       name, extra, ART_VIEWBOX[name], name)
