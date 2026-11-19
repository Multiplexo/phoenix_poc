from django import template

register = template.Library()


@register.filter
def pct(v, sign=""):
    if v is None or v == "":
        return "–"
    s = f"{float(v) * 100:+.0f} %" if sign else f"{float(v) * 100:.0f} %"
    return s.replace("-", "−")


@register.filter
def stk(v):
    if v is None or v == "":
        return "–"
    return f"{float(v):,.0f}".replace(",", ".")


@register.filter
def ml(d):
    """Monat kurz: 11/26"""
    try:
        return f"{d.month:02d}/{str(d.year)[2:]}"
    except AttributeError:
        return str(d)[:7]


@register.filter
def get(d, k):
    return d.get(k) if hasattr(d, "get") else None


@register.filter
def pp(v):
    if v is None or v == "":
        return "–"
    return (f"{float(v) * 100:+.1f}".replace(".", ",") + " Pp.").replace("-", "−")
