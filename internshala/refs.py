"""Internshala input parsing: ONE param per input that auto-detects its
forms (tripadvisor QueryOrLinkField convention, never a sibling `url`/`id`
pair). Every resolver returns plain JSON values so validated params stay
usable as a response-cache key, and raises ValueError with a user-facing
message.

  internship / job   https://internshala.com/internship/detail/<slug>  (any query / utm dropped)
                     | /job/detail/<slug> | <slug>   -> {"kind": "internship" | "job", "slug": "<slug>"}
                     (a bare slug takes the endpoint's own kind; a link's path decides)
  company            https://internshala.com/company/planetspark-1580118881/careers/
                     | planetspark-1580118881        -> {"slug": "planetspark-1580118881", "name": None}
                     | PlanetSpark (a name)          -> {"slug": None, "name": "PlanetSpark"}
                     (a name is resolved against the site's own company listings at call time)
  category           'Web Development' | 'web-development' | 'hr' -> the listing slug
  location           'New Delhi' | 'new-delhi'                    -> the listing slug
"""
import re
from urllib.parse import unquote, urlparse

from internshala import refdata

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*\d+$")
_BAD = re.compile(r"[/?#\\<>\"]")


def _site_url(value):
    """-> (path) when value is an internshala.com link or host path, None for
    plain text. Raises ValueError for another site's link."""
    raw = (value or "").strip()
    low = raw.lower()
    if low.startswith("//"):
        raw = "https:" + raw
    elif low.startswith("/"):
        return unquote(raw.split("?", 1)[0])          # a site path: /job/detail/<slug>, /company/<slug>/
    elif not low.startswith(("http://", "https://")):
        head = low.split("/", 1)[0]
        if not head.endswith(refdata.HOST):
            return None
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host != refdata.HOST and not host.endswith("." + refdata.HOST):
        raise ValueError("Must be an internshala.com link.")
    return unquote(parsed.path)


LISTING_HINT = ("Must be an Internshala internship or job link (https://internshala.com/internship/detail/<slug> "
                "or /job/detail/<slug>) or the slug from one (the part after /detail/).")


def resolve_listing(value, default_kind="internship"):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(LISTING_HINT)
    try:
        path = _site_url(raw)
    except ValueError:
        raise ValueError(LISTING_HINT)
    if path is not None:
        match = re.search(r"/(internship|job)/details?/([^/?#]+)", path)
        if not match:
            raise ValueError(LISTING_HINT)
        kind, slug = match.group(1), match.group(2)
    else:
        kind, slug = default_kind, raw.split("?")[0].strip("/")
    slug = slug.strip().lower()
    if not _SLUG_RE.match(slug) or _BAD.search(slug) or len(slug) > 300:
        raise ValueError(LISTING_HINT)
    return {"kind": kind, "slug": slug}


def resolve_internship(value):
    return resolve_listing(value, "internship")


def resolve_job(value):
    return resolve_listing(value, "job")


COMPANY_HINT = ("Must be an Internshala company page link (https://internshala.com/company/<name>-<id>), "
                "its slug (planetspark-1580118881) or a company name.")


def resolve_company(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(COMPANY_HINT)
    try:
        path = _site_url(raw)
    except ValueError:
        raise ValueError(COMPANY_HINT)
    if path is not None:
        match = re.search(r"/company/([^/?#\\]+)", path)
        if not match:
            raise ValueError("Links must be company pages (/company/<name>-<id>).")
        raw = match.group(1)
    slug = raw.lower()
    if " " not in slug and re.fullmatch(r"[a-z0-9][a-z0-9._-]*-\d{6,}", slug):
        return {"slug": slug, "name": None}
    name = " ".join(raw.split())
    if _BAD.search(name) or len(name) > 150:
        raise ValueError(COMPANY_HINT)
    return {"slug": None, "name": name}


# ---- categories / cities ------------------------------------------------------------------------------

_CATEGORY_BY_LOWER = {label.lower(): slug for label, slug in refdata.CATEGORIES.items()}
_CATEGORY_SLUGS = set(refdata.CATEGORIES.values())
_CITY_BY_LOWER = {label.lower(): slug for label, slug in refdata.CITIES.items()}
_CITY_SLUGS = set(refdata.CITIES.values())


def _norm(value):
    return re.sub(r"\s+", "-", (value or "").strip().lower())


def resolve_category(value):
    """A category label or slug -> the listing slug; unknown -> ValueError."""
    raw = " ".join((value or "").split())
    if not raw:
        raise ValueError("Category must not be empty.")
    slug = _CATEGORY_BY_LOWER.get(raw.lower()) or (_norm(raw) if _norm(raw) in _CATEGORY_SLUGS else None)
    if slug is None:
        # tolerate "web development" / "web-development" / "Web Development (Backend)" style typing
        key = re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()
        for label, s in refdata.CATEGORIES.items():
            if re.sub(r"[^a-z0-9]+", " ", label.lower()).strip() == key or re.sub(r"[^a-z0-9]+", " ", s).strip() == key:
                slug = s
                break
    if slug is None:
        raise ValueError(f"'{raw}' is not an Internshala category (see /internshala/categories).")
    return slug


def resolve_location(value):
    """A city label or slug -> the listing slug; unknown -> ValueError."""
    raw = " ".join((value or "").split())
    if not raw:
        raise ValueError("Location must not be empty.")
    slug = _CITY_BY_LOWER.get(raw.lower()) or (_norm(raw) if _norm(raw) in _CITY_SLUGS else None)
    if slug is None:
        key = re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()
        for label, s in refdata.CITIES.items():
            if re.sub(r"[^a-z0-9]+", " ", label.lower()).strip() == key:
                slug = s
                break
    if slug is None:
        raise ValueError(f"'{raw}' is not a city Internshala lists (see /internshala/locations).")
    return slug


def category_label(slug):
    for label, s in refdata.CATEGORIES.items():
        if s == slug:
            return label
    return None


def city_label(slug):
    for label, s in refdata.CITIES.items():
        if s == slug:
            return label
    return None
