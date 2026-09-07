from django import template

register = template.Library()

FUNDING_COLORS = {
    "Fully Funded": "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    "Partial": "bg-amber-500/15 text-amber-400 border-amber-500/30",
    "Cash Prize": "bg-fuchsia-500/15 text-fuchsia-400 border-fuchsia-500/30",
    "Paid Role": "bg-sky-500/15 text-sky-400 border-sky-500/30",
    "Unfunded": "bg-slate-500/15 text-slate-400 border-slate-500/30",
}

STATUS_COLORS = {
    "New": "bg-slate-500/15 text-slate-300 border-slate-500/30",
    "Interested": "bg-sky-500/15 text-sky-400 border-sky-500/30",
    "Applied": "bg-amber-500/15 text-amber-400 border-amber-500/30",
    "Rejected": "bg-rose-500/15 text-rose-400 border-rose-500/30",
    "Accepted": "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
}

CATEGORY_COLORS = {
    "MSc": "bg-indigo-500/15 text-indigo-400 border-indigo-500/30",
    "PhD": "bg-purple-500/15 text-purple-400 border-purple-500/30",
    "Quant Role": "bg-cyan-500/15 text-cyan-400 border-cyan-500/30",
    "SWE Role": "bg-blue-500/15 text-blue-400 border-blue-500/30",
    "Hackathon": "bg-pink-500/15 text-pink-400 border-pink-500/30",
    "Fellowship": "bg-teal-500/15 text-teal-400 border-teal-500/30",
    "Scholarship": "bg-lime-500/15 text-lime-400 border-lime-500/30",
    "Other": "bg-slate-500/15 text-slate-400 border-slate-500/30",
}


@register.filter
def funding_color(value):
    return FUNDING_COLORS.get(value, FUNDING_COLORS["Unfunded"])


@register.filter
def status_color(value):
    return STATUS_COLORS.get(value, STATUS_COLORS["New"])


@register.filter
def category_color(value):
    return CATEGORY_COLORS.get(value, CATEGORY_COLORS["Other"])


@register.filter
def get_item(dictionary, key):
    """Usage: {{ some_dict|get_item:key }} -- Django templates can't do dynamic dict lookups otherwise."""
    if not dictionary:
        return None
    return dictionary.get(key)
