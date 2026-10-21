"""Value helpers for the Internshala parsers: text, Indian-rupee money
labels, durations, experience, relative post ages, the site's date formats,
slugs and links. Pure functions, no network; every helper tolerates None and
junk.

The generic safe-access / number / text / HTML helpers have the same
semantics as jobstreet/shared.py (whitespace-collapsed strings, '' -> None,
block elements -> line breaks); they live here so the internshala package
stands alone (it ships as its own open-source repo, which must not pull in
other sites' modules).
"""
import html as html_lib
import re
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import quote, urlparse, urlunparse

from internshala import refdata

# ---- safe access / numbers / text (generic) -------------------------------------------------------

def g(obj, *path, default=None):
    """Safe nested get: g(d, "a", "b", 0) -> d["a"]["b"][0] or default."""
    for step in path:
        if isinstance(step, int):
            if not isinstance(obj, list) or not -len(obj) <= step < len(obj):
                return default
            obj = obj[step]
        else:
            if not isinstance(obj, dict):
                return default
            obj = obj.get(step)
        if obj is None:
            return default
    return obj


def as_list(value):
    return value if isinstance(value, list) else []


def as_dict(value):
    return value if isinstance(value, dict) else {}


def num(value):
    """int / float / numeric string ('1,234.5') -> float; bool, junk, NaN -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    try:
        out = float(str(value).strip().replace(",", ""))
    except ValueError:
        return None
    return out if out == out else None


def to_int(value):
    out = num(value)
    return int(round(out)) if out is not None else None


def text(value):
    """Whitespace-collapsed, HTML-unescaped string; '' -> None. Accepts
    {"text": ...} wrappers."""
    if isinstance(value, dict):
        value = value.get("text")
    if value is None:
        return None
    out = " ".join(html_lib.unescape(str(value)).replace("\xa0", " ").replace(" ", " ").split())
    return out or None


def multiline(value):
    """Like text() but keeps line breaks (review bodies, descriptions)."""
    if isinstance(value, dict):
        value = value.get("text")
    if value is None:
        return None
    lines = [" ".join(line.split()) for line in html_lib.unescape(str(value)).replace("\xa0", " ").splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out or None


# ---- HTML -> text ------------------------------------------------------------------------------------

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
               "section", "article", "header", "footer", "blockquote", "pre", "hr", "dd", "dt", "dl"}
_SKIP_TAGS = {"script", "style", "noscript", "template", "head"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in ("li", "br"):
            return
        elif tag in ("ul", "ol"):
            self.parts.append("\n\n")      # a list ends its paragraph
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(value):
    """An HTML fragment -> readable plain text: block elements become line
    breaks, list items get a dash, runs of blank lines collapse."""
    value = value if isinstance(value, str) else None
    if not value:
        return None
    if "<" not in value:
        return multiline(value)
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        return multiline(re.sub(r"<[^>]+>", " ", value))
    raw = "".join(parser.parts).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"\n\n(- )", r"\n\1", out).strip()   # list items stay tight
    return out or None


CURRENCY = "INR"

# ---- links ---------------------------------------------------------------------------------------------

_TRACKING_PARAMS = ("utm_", "referral", "ref")


def link(path):
    """A site path or absolute URL -> absolute https link without tracking
    query params (utm_source=company_pages&referral=...); '' / None -> None."""
    path = text(path) if isinstance(path, str) else None
    if not path:
        return None
    if path.startswith("//"):
        path = "https:" + path
    elif not path.startswith(("http://", "https://")):
        path = f"{refdata.BASE_LINK}/{path.lstrip('/')}"
    parsed = urlparse(path)
    query = "&".join(p for p in parsed.query.split("&")
                     if p and not p.split("=", 1)[0].lower().startswith(_TRACKING_PARAMS))
    return urlunparse(parsed._replace(scheme="https", query=query, fragment=""))


def listing_link(kind, slug):
    return f"{refdata.BASE_LINK}/{kind}/detail/{slug}" if slug else None


def company_link(slug):
    return f"{refdata.BASE_LINK}/company/{slug}" if slug else None


def slug_of_link(value):
    """'/internship/detail/<slug>?utm=..' -> ('internship', '<slug>'); None when not a listing link."""
    value = text(value) if isinstance(value, str) else None
    if not value:
        return None
    match = re.search(r"/(internship|job)/details?/([^/?#]+)", value)
    if not match:
        return None
    return match.group(1), match.group(2)


def company_slug_of_link(value):
    value = text(value) if isinstance(value, str) else None
    if not value:
        return None
    match = re.search(r"/company/([^/?#\\]+)", value)
    return match.group(1) if match else None


def slug_id(slug):
    """The trailing digits of a listing / company slug ('...-studios1792384358' -> 1792384358)."""
    match = re.search(r"(\d+)$", slug or "")
    return int(match.group(1)) if match else None


# ---- slugs (the site's normalize_for_arg: lower-case, whitespace -> '-') -----------------------------------

def arg_slug(value):
    value = text(value)
    if not value:
        return None
    return re.sub(r"\s+", "-", value.lower().strip()) or None


def path_segment(value):
    """A listing path segment, percent-encoded like the site does ('ui/ux-design'
    -> 'ui%2Fux-design', 'delhi,mumbai' kept)."""
    return quote(value, safe="-_.,~!$'()*+;=:@")


# ---- money ------------------------------------------------------------------------------------------------

_INR_FIGURE = r"\d[\d,]*(?:\.\d+)?"
_PERIODS = (("/month", "monthly"), ("per month", "monthly"), ("/year", "yearly"), ("per year", "yearly"),
            ("/annum", "yearly"), ("/week", "weekly"), ("per week", "weekly"), ("/day", "daily"),
            ("per day", "daily"), ("/hour", "hourly"), ("per hour", "hourly"), ("lump sum", "lump_sum"),
            ("lumpsum", "lump_sum"), ("lpa", "yearly"))


def _figure(raw):
    """'3,50,000' / '8,000' / '4.5' -> number (Indian grouping tolerated)."""
    raw = raw.replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    return int(value) if value.is_integer() else value


def money(label, period=None):
    """A rupee label -> {label, min, max, currency, period, is_unpaid}:

      '₹ 8,000 - 12,000 /month'  -> 8000 / 12000 / monthly
      '₹ 3,50,000 - 4,50,000'    -> 350000 / 450000 (period as given / None)
      '₹ 4LPA' / '₹ 8.2 LPA'      -> 400000 / 820000 / yearly
      '₹ 800 - 3,000 lump sum'   -> 800 / 3000 / lump_sum
      'Unpaid'                   -> 0 / 0, is_unpaid True
    Labels without a figure keep min / max None; '' -> None."""
    label = text(label)
    if not label:
        return None
    low = label.lower()
    out = {"label": label, "min": None, "max": None, "currency": CURRENCY, "period": period, "is_unpaid": False}
    if "unpaid" in low:
        out.update(min=0, max=0, is_unpaid=True)
        return out
    for marker, name in _PERIODS:
        if marker in low:
            out["period"] = name
            break
    figures = []
    lakhs = re.search(r"\d\s*lpa\b", low) is not None     # '₹ 4 - 6 LPA': the unit covers both figures
    for match in re.finditer(_INR_FIGURE, label):
        value = _figure(match.group(0))
        if value is None:
            continue
        if lakhs and value < 1000:
            value = value * 100000
            value = int(value) if float(value).is_integer() else round(value, 2)
        figures.append(value)
    if figures:
        out["min"], out["max"] = min(figures), max(figures)
    return out


# ---- durations / experience ---------------------------------------------------------------------------

def duration(label):
    """'3 Months' / '2 Weeks' / '1 Month' -> {label, months}; '' -> None."""
    label = text(label)
    if not label:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(month|week|day|year)", label, re.I)
    months = None
    if match:
        value = float(match.group(1))
        unit = match.group(2).lower()
        months = {"month": value, "week": value / 4, "day": value / 30, "year": value * 12}[unit]
        months = int(months) if float(months).is_integer() else round(months, 2)
    return {"label": label, "months": months}


def experience(label):
    """'1 year(s)' / '0-2 years' / 'Fresher' -> {label, min_years, max_years}."""
    label = text(label)
    if not label:
        return None
    figures = [int(x) for x in re.findall(r"\d+", label)]
    low = label.lower()
    if not figures and ("fresher" in low or "no experience" in low):
        return {"label": label, "min_years": 0, "max_years": 0}
    return {"label": label, "min_years": min(figures) if figures else None,
            "max_years": max(figures) if figures else None}


# ---- relative post ages / dates ------------------------------------------------------------------------

_AGO_UNITS = {"second": 0, "minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}


def posted(label, today=None):
    """'Few hours ago' / 'Just now' / 'Today' / '2 days ago' / 'Posted 3 weeks ago'
    -> {label, days_ago, date} with the date estimated from today (UTC)."""
    label = text(label)
    if not label:
        return None
    clean = re.sub(r"^posted\s+", "", label, flags=re.I)
    low = clean.lower()
    days = None
    if any(w in low for w in ("just now", "today", "hour", "minute", "few")):
        days = 0
    else:
        match = re.search(r"(\d+)\s*(second|minute|hour|day|week|month|year)", low)
        if match:
            days = int(match.group(1)) * _AGO_UNITS[match.group(2)]
        elif re.search(r"\b(a|an|one)\s+(day|week|month|year)", low):
            unit = re.search(r"\b(a|an|one)\s+(day|week|month|year)", low).group(2)
            days = _AGO_UNITS[unit]
        elif "yesterday" in low:
            days = 1
    today = today or datetime.now(timezone.utc).date()
    return {"label": clean, "days_ago": days, "date": (today - timedelta(days=days)).isoformat() if days is not None else None}


_MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
_MONTHS.update({"sept": 9})


def site_date(label):
    """The site's short dates -> 'YYYY-MM-DD':
    "3 Nov' 26" / "18th Oct'26" / "16th Sep'26" / "2026-11-18 23:59:59" / "June 2025" (-> first of month)."""
    label = text(label)
    if not label:
        return None
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", label)
    if match:
        return "-".join(match.groups())
    match = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s*([A-Za-z]{3,9})'?\s*(\d{2,4})", label)
    if match:
        day, mon, year = match.groups()
        month = _MONTHS.get(mon.lower()[:4] if mon.lower().startswith("sept") else mon.lower()[:3])
        if month:
            year = int(year) + (2000 if len(year) == 2 else 0)
            try:
                return date(year, month, int(day)).isoformat()
            except ValueError:
                return None
    match = re.search(r"([A-Za-z]{3,9})\s+(\d{4})", label)
    if match:
        month = _MONTHS.get(match.group(1).lower()[:3])
        if month:
            return date(int(match.group(2)), month, 1).isoformat()
    return None


def month_label(label):
    """'Hiring since June 2025' -> '2025-06'."""
    iso = site_date(label)
    return iso[:7] if iso else None


def count_in(label):
    """'544 applicants' / '1261 opportunities posted' / '20' -> 544 / 1261 / 20."""
    label = text(label)
    if not label:
        return None
    match = re.search(r"(\d[\d,]*)", label)
    return int(match.group(1).replace(",", "")) if match else None


def split_list(value):
    """'Lucknow, Pune, Hyderabad' -> ['Lucknow', 'Pune', 'Hyderabad'] (trimmed, deduped)."""
    value = text(value)
    if not value:
        return []
    out = []
    for item in value.split(","):
        item = item.strip()
        if item and item not in out:
            out.append(item)
    return out
