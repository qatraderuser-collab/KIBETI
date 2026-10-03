from django import template

register = template.Library()


@register.filter
def money(value):
    try:
        return "KSh {:,.2f}".format(float(value))
    except (TypeError, ValueError):
        return value


@register.filter
def money_short(value):
    try:
        return "KSh {:,.0f}".format(float(value))
    except (TypeError, ValueError):
        return value


@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except (TypeError, ValueError):
        return value


SWATCH_HEX = {
    "black": "#1b1b1b", "charcoal": "#3a3a3a", "grey": "#9a9a9a", "gray": "#9a9a9a",
    "silver": "#c7c9cc", "white": "#ffffff", "cream": "#f2e7d2", "beige": "#e3d3b8",
    "tan": "#c49a6c", "gold": "#c98a2b", "mustard yellow": "#c9a227", "yellow": "#d9b23a",
    "orange": "#d9702a", "spice brown": "#a2602c", "spice": "#b06a2e", "caramel": "#c07f3e",
    "dark brown": "#4a2f1c", "chocolate brown": "#4b2e1e", "chocolate": "#4b2e1e",
    "brown": "#7a4a25", "cracked": "#6b5744", "red": "#b3272d", "maroon": "#6e2231",
    "burgundy": "#5f2330", "pink": "#e3a3b0", "rose": "#c98a7a", "lilac": "#b9a3d0",
    "purple": "#6b4a86", "emerald green": "#1f6b4a", "green": "#3f7a4e", "olive": "#6e7042",
    "teal": "#2e7a78", "turquoise": "#2e9a97", "blue": "#2f5d86", "navy": "#20293f",
    "denim": "#4a6b8a", "leopard": "#a37a45", "ankara": "#7a3f5d",
}
SWATCH_KEYWORDS = [
    ("mustard", "#c9a227"), ("dark brown", "#4a2f1c"), ("chocolate", "#4b2e1e"),
    ("spice", "#a2602c"), ("emerald", "#1f6b4a"), ("navy", "#20293f"),
    ("off white", "#f4f1ea"), ("brown", "#7a4a25"), ("green", "#3f7a4e"),
    ("blue", "#2f5d86"), ("yellow", "#d9b23a"), ("pink", "#e3a3b0"),
    ("red", "#b3272d"), ("grey", "#9a9a9a"), ("gray", "#9a9a9a"),
    ("white", "#ffffff"), ("black", "#1b1b1b"), ("gold", "#c98a2b"),
    ("beige", "#e3d3b8"), ("cream", "#f2e7d2"), ("tan", "#c49a6c"),
]


@register.filter
def color_swatches(value, limit=6):
    names = [n.strip() for n in str(value or "").replace(";", ",").split(",") if n.strip()]
    seen, unique = set(), []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            unique.append(n)
    shown = unique[:limit]
    out = [
        {
            "name": n,
            "hex": SWATCH_HEX.get(n.lower())
            or next((h for k, h in SWATCH_KEYWORDS if k in n.lower()), "#d8d2c8"),
        }
        for n in shown
    ]
    if len(unique) > limit:
        out.append({"more": len(unique) - limit})
    return out


@register.inclusion_tag("store/partials/pagination.html")
def pagination(page_obj, **extra):
    return {"page_obj": page_obj, "params": extra}
