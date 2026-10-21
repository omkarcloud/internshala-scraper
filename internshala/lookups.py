"""/internshala/categories, /internshala/locations, /internshala/autocomplete
— the filter vocabularies the search endpoints' `category` / `location`
params take (the site's own live lists) and the search box's suggestions."""
from internshala import fetch, refdata
from internshala import parsers as P


def _vocab(type):
    raw = fetch.criteria("jobs" if type == "jobs" else "internships")
    return P.criteria(raw)


def categories(type="internships"):
    """The categories (profiles) of the board, with the slug each listing path uses."""
    items = _vocab(type)["categories"]
    return {"type": type, "count": len(items), "categories": items}


def locations(type="internships"):
    """The cities of the board, with the slug each listing path uses."""
    items = _vocab(type)["locations"]
    return {"type": type, "count": len(items), "locations": items}


def autocomplete(query, type="category"):
    """The search box's category or city suggestions for `query` (3+ chars)."""
    raw = fetch.autocomplete(type, query)
    names = P.autocomplete(raw)
    table = refdata.CATEGORIES if type == "category" else refdata.CITIES
    lower = {k.lower(): v for k, v in table.items()}
    from internshala.shared import arg_slug
    return {"query": query, "type": type,
            "suggestions": [{"name": n, "slug": lower.get(n.lower()) or arg_slug(n)} for n in names]}
