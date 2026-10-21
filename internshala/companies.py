"""/internshala/companies/* — the employer pages (/company/<name>-<id>/:
overview, careers, salaries-perks) and the company-scoped listings."""
import config
from internshala import cache_config as ttl
from internshala import fetch, listings
from internshala import parsers as P
from internshala import shared as S


def _own_listings(name_slug, kind, page=1):
    """The company's own cards on a board, or None when the site lists none
    (the board then answers other employers' "similar" cards, which
    listings.company_listings strips)."""
    try:
        return listings.company_listings(name_slug, kind, page)
    except fetch.InternshalaNotFound:
        return None


def _slug_from_listings(name):
    """A company name -> its page slug: the company-scoped listing's first own
    card links a detail page, whose header links the company page. None
    when the site lists nothing under that name."""
    name_slug = S.arg_slug(name)
    for kind in ("internships", "jobs"):
        result = _own_listings(name_slug, kind)
        for item in (result or {}).get("listings") or []:
            parsed = S.slug_of_link(item.get("link"))
            if not parsed:
                continue
            page = fetch.page(f"/{parsed[0]}/detail/{parsed[1]}", label=f"{parsed[0]} {parsed[1]}")
            details = P.details(page, parsed[0], parsed[1]) or {}
            slug = (details.get("company") or {}).get("slug")
            if slug:
                return slug
    return None


def resolve_slug(company):
    """A resolved company ref ({slug} | {name}) -> the /company/ page slug."""
    if company.get("slug"):
        return company["slug"]
    name = company["name"]

    def build():
        # raised inside build so a miss is never cached (a name with no open
        # listing today may have one tomorrow)
        slug = _slug_from_listings(name)
        if not slug:
            raise fetch.InternshalaNotFound(f"Internshala has no company page for '{name}'")
        return slug
    return fetch.shared_raw("company_slug", {"name": name.lower()}, build, ttl.COMPANY_LOOKUP_CACHE)


def details(company):
    """The employer profile (location, industry, size, hiring activity,
    website, about), its open internships and jobs (first page of each
    company-scoped listing, full cards, with the totals), the salaries it has
    paid per role and its perks — the pages fetched in parallel."""
    slug = resolve_slug(company)
    name_slug = listings.company_name_slug({"slug": slug})
    fns = [
        lambda: fetch.page(f"/company/{slug}/", label=f"company {slug}"),
        lambda: fetch.page(f"/company/{slug}/salaries-perks/", label=f"company {slug} salaries"),
        lambda: _own_listings(name_slug, "internships"),
        lambda: _own_listings(name_slug, "jobs"),
        lambda: fetch.page(f"/company/{slug}/careers/", label=f"company {slug} careers"),
    ]
    results = fetch.run_parallel(fns, config.INTERNSHALA_WORKERS)
    (overview_status, overview), (salaries_status, salaries), (int_status, internships), (job_status, jobs), \
        (careers_status, careers) = results
    if overview_status != "ok":
        raise overview
    profile = P.company_profile(overview, slug)
    if profile is None:
        raise fetch.InternshalaNotFound(f"Internshala has no company page for '{slug}'")
    profile.pop("openings_preview", None)
    if salaries_status == "ok":
        extra = P.company_salaries(salaries)
        if extra["salaries"]:
            profile["salaries"] = extra["salaries"]
        if extra["perks"]:
            profile["perks"] = extra["perks"]
    internships = internships if int_status == "ok" else None
    jobs = jobs if job_status == "ok" else None
    profile["internships_count"] = (internships or {}).get("pagination", {}).get("total_count", 0) if internships else 0
    profile["internships"] = (internships or {}).get("listings") or []
    profile["jobs_count"] = (jobs or {}).get("pagination", {}).get("total_count", 0) if jobs else 0
    profile["jobs"] = (jobs or {}).get("listings") or []
    # the careers page is the site's own (partial) openings list: the fallback
    # when the name slug the listing filter takes differs from the page slug
    if not profile["internships"] and not profile["jobs"] and careers_status == "ok":
        openings = P.company_openings(careers)
        profile["internships"] = [o for o in openings if o.get("type") == "internship"]
        profile["jobs"] = [o for o in openings if o.get("type") == "job"]
        profile["internships_count"] = len(profile["internships"])
        profile["jobs_count"] = len(profile["jobs"])
    return profile


def openings(company, type="internships", page=1):
    """One page of the company's open internships or jobs as full listing
    cards (the same card shape as the search endpoints)."""
    name_slug = listings.company_name_slug(company)
    result = listings.company_listings(name_slug, type, page)
    result[type] = result.pop("listings")
    result["company"] = {"name": result.get("company"), "slug": company.get("slug"),
                         "link": S.company_link(company.get("slug"))}
    return result
