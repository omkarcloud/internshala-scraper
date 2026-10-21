"""Raw Internshala HTML / JSON -> clean API objects. Pure functions, no
network; every parser tolerates missing / null / wrong-typed markup and
never raises on a partial page.

Listing cards come from the listing JSON's card HTML (listing_result /
card); internship and job pages from the detail HTML plus the JobPosting
JSON-LD the page embeds (details); company profiles / openings / salaries
from the three company pages; the category and city vocabularies from the
criteria JSON.

Intentionally dropped everywhere: the login / sign-up / share / apply-now
chrome (Google sign-in buttons, WhatsApp / LinkedIn share links, csrf
tokens, registration forms), the "Earn certifications in these skills"
training-course adverts and native ad slots on the listing, the
`sequential_apply_referral` / `data-source_page` / `visibilityTrackerItem`
tracking attributes, utm / referral query params on every link (links are
rebuilt clean), the SEO FAQ / breadcrumb / footer HTML blobs of the listing
JSON (`faqs_html`, `breadcrumbs_html`, `programmatic_footer_content_html`,
`location_content_html`, `recommended_categories_view`, `third_container_data`
— sign-up nudges), the page's mobile/desktop duplicate spans (one value is
kept), the JSON-LD `@context` / `@type` / `directApply` / `identifier`
(its value is the listing id with a year prefix — the card id is kept
instead), and the "Similar internships" sign-up card. Nothing with
information content is left out.
"""
import json
import re
from math import ceil

from lxml import html as lxml_html

from internshala import refdata
from internshala import shared as S
from internshala.shared import as_dict, as_list, text

# ---- small helpers ----------------------------------------------------------------------------------

def doc(markup):
    """HTML text -> lxml root (never raises; junk -> an empty <div>)."""
    try:
        return lxml_html.fromstring(markup if markup and markup.strip() else "<div></div>")
    except Exception:
        return lxml_html.fromstring("<div></div>")


def _one(el, xpath):
    try:
        found = el.xpath(xpath)
    except Exception:
        return None
    return found[0] if found else None


def _all(el, xpath):
    try:
        return el.xpath(xpath)
    except Exception:
        return []


def _text(el):
    if el is None:
        return None
    if isinstance(el, str):
        return text(el)
    try:
        return text(el.text_content())
    except Exception:
        return None


def _own_text(el):
    """An element's text without its descendants' text (the '(Hybrid)' next to the city link)."""
    if el is None:
        return None
    parts = [el.text or ""]
    for child in el:
        parts.append(child.tail or "")
    return text(" ".join(parts))


def _attr(el, name):
    if el is None:
        return None
    return text(el.get(name)) if el.get(name) is not None else None


def _inner_html(el):
    if el is None:
        return None
    try:
        parts = [el.text or ""]
        for child in el:
            parts.append(lxml_html.tostring(child, encoding="unicode"))
        return "".join(parts).strip() or None
    except Exception:
        return None


_PLACEHOLDER_LOGOS = ("placeholder_logo", "/images/company/logo.svg")


def logo(src):
    """An employer logo -> absolute link; the site's placeholder / default
    images (shown when the employer uploaded none) -> None."""
    out = S.link(src) if isinstance(src, str) else None
    if not out or any(p in out for p in _PLACEHOLDER_LOGOS):
        return None
    return out


def _has_class(el, name):
    return name in (el.get("class") or "").split()


def _cls(name):
    """An XPath predicate matching one exact class token (contains() would
    also match 'individual_internship_details' for 'internship_details')."""
    return f"[contains(concat(' ', normalize-space(@class), ' '), ' {name} ')]"


def _int(value):
    return S.to_int(value)


# ---- listing cards ------------------------------------------------------------------------------------

def _work_mode(location_el):
    """The card's location row -> (cities, work_mode, office_days_per_week)."""
    if location_el is None:
        return [], None, None
    cities = S.split_list(_text(_one(location_el, ".//a")))
    rest = (_own_text(_one(location_el, ".//span")) or "") + " " + (_own_text(location_el) or "")
    low = rest.lower()
    remote = _one(location_el, ".//i[contains(@class,'ic-16-home')]") is not None \
        or any(c.lower() == "work from home" for c in cities)
    if remote:
        cities = [c for c in cities if c.lower() != "work from home"]
        mode = "work_from_home"
    elif "hybrid" in low:
        mode = "hybrid"
    elif cities:
        mode = "in_office"
    else:
        mode = None
    days = None
    popover = _one(location_el, ".//*[contains(@class,'office_days_popover')]")
    if popover is not None:
        days = S.count_in(popover.get("data-popover_content"))
    return cities, mode, days


def _job_offer(el):
    """The 'Job offer upto ₹ 4LPA post internship' badge -> {label, max_ctc}."""
    label = _text(el)
    if not label:
        return None
    ctc = S.money(re.sub(r"\bpost internship\b|\bjob offer\b|\bupto\b|\bup to\b", "", label, flags=re.I))
    if ctc and ctc["max"] is None:
        ctc = None
    if ctc:
        ctc["period"] = "yearly"
    return {"label": label, "max_ctc": ctc}


def card(el, kind=None):
    """One listing card (div.individual_internship) -> the public card object."""
    href = _attr(_one(el, ".//a[contains(@class,'job-title-href')]"), "href") or el.get("data-href")
    parsed = S.slug_of_link(href)
    kind = (el.get("employment_type") or (parsed[0] if parsed else kind) or "internship").lower()
    slug = parsed[1] if parsed else None
    location_el = _one(el, ".//*[contains(@class,'locations')]")
    cities, mode, office_days = _work_mode(location_el)

    stipend = None
    salary = None
    money_row = _one(el, ".//div[contains(@class,'row-1-item')][.//i[contains(@class,'ic-16-money')]]")
    if money_row is not None:
        label = _text(_one(money_row, ".//span[contains(@class,'stipend')]"))
        if label:
            stipend = S.money(label)
        else:
            label = _text(_one(money_row, ".//span[contains(@class,'mobile')]")) or _text(money_row)
            salary = S.money(label, period="yearly")
    duration = S.duration(_text(_one(el, ".//div[contains(@class,'row-1-item')][.//i[contains(@class,'ic-16-calendar')]]//span")))
    experience = S.experience(_text(_one(el, ".//div[contains(@class,'row-1-item')][.//i[contains(@class,'ic-16-briefcase')]]//span")))

    posted_el = _one(el, ".//div[contains(@class,'color-labels')]//div[contains(@class,'status-')]//span")
    labels = []
    is_part_time = False
    for item in _all(el, ".//div[contains(@class,'gray-labels')]//div[contains(@class,'status-li')]"):
        label = _text(item)
        if not label:
            continue
        if label.lower() == "part time":
            is_part_time = True
        else:
            labels.append(label)
    skills = [s for s in (_text(x) for x in _all(el, ".//div[@class='job_skill']")) if s]

    out = {
        "id": _int(el.get("internshipid") or el.get("internshipId")),
        "slug": slug,
        "type": kind,
        "title": _text(_one(el, ".//a[contains(@class,'job-title-href')]")) or _text(_one(el, ".//h2")),
        "link": S.listing_link(kind, slug) if slug else S.link(href),
        "company": {
            "name": _text(_one(el, ".//*[contains(@class,'company-name')]")),
            "logo": logo(_attr(_one(el, ".//div[contains(@class,'internship_logo')]//img"), "src")),
        },
        "locations": cities,
        "work_mode": mode,
        "office_days_per_week": office_days,
        "is_part_time": is_part_time,
        "stipend": stipend,
        "salary": salary,
        "duration": duration,
        "experience": experience,
        "skills": skills,
        "summary": _text(_one(el, ".//div[contains(@class,'about_job')]//div[contains(@class,'text')]")),
        "posted": S.posted(_text(posted_el)),
        "is_actively_hiring": _one(el, ".//*[contains(@class,'actively-hiring-badge')]") is not None,
        "is_early_applicant": _one(el, ".//*[contains(@class,'early_applicant_wrapper')]") is not None,
        "job_offer": _job_offer(_one(el, ".//div[contains(@class,'ppo_status')]//span")),
        "labels": labels,
    }
    if kind == "job":
        out.pop("stipend", None)
        out.pop("duration", None)
        out.pop("job_offer", None)
    else:
        out.pop("salary", None)
        out.pop("experience", None)
    return out


def cards(markup, kind=None):
    root = doc(markup)
    out = []
    for el in _all(root, "//div[contains(@class,'individual_internship') and (@internshipid or @internshipId or @data-href)]"):
        # the listing wraps each card once; nested detail blocks carry no data-href
        if _has_class(el, "individual_internship_details"):
            continue
        item = card(el, kind)
        if item.get("title") or item.get("link"):
            out.append(item)
    return out


def _heading_total(heading):
    """'7027 Total Internships' / '218 Web Development Internships in Bangalore' / '6523 Jobs' -> 7027."""
    heading = text(heading)
    if not heading:
        return None
    match = re.match(r"\s*(\d[\d,]*)\s", heading + " ")
    return int(match.group(1).replace(",", "")) if match else None


def _last_page(markup):
    """The largest page number the listing's pagination block links to."""
    pages = [int(p) for p in re.findall(r'class=["\']?pagination_block[^>]*data-page=["\']?(\d+)', markup or "")]
    return max(pages) if pages else None


def listing_result(raw, page=1, kind=None):
    """The listing JSON -> {heading, company, pagination, listings}."""
    raw = as_dict(raw)
    markup = raw.get("internship_list_html") or ""
    seo = as_dict(raw.get("seo"))
    items = cards(markup, kind)
    total = _heading_total(seo.get("heading"))
    is_last = bool(raw.get("is_last_page"))
    last_page = _last_page(markup)
    if is_last:
        total_pages = page if items or page == 1 else page - 1
    elif last_page:
        total_pages = max(last_page, page)
    elif total:
        total_pages = max(ceil(total / refdata.ITEMS_PER_PAGE), page)
    else:
        total_pages = page + 1
    if total is None:
        total = len(items) if is_last and page == 1 else None
    return {
        "heading": text(seo.get("heading")),
        "company": text(seo.get("company_name")) or None,
        "filters_applied": _int(raw.get("filters_count")),
        "pagination": {
            "page": page,
            "items_per_page": len(items) or refdata.ITEMS_PER_PAGE,
            "total_pages": total_pages,
            "total_count": total,
            "is_last_page": is_last,
        },
        "listings": items,
    }


# ---- detail pages ---------------------------------------------------------------------------------------

def _json_ld(root):
    """The page's JobPosting JSON-LD (a dict) or None."""
    for script in _all(root, "//script[@type='application/ld+json']"):
        try:
            data = json.loads(script.text or "")
        except ValueError:
            continue
        for item in (data if isinstance(data, list) else [data]):
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return None


def _numbered_lines(container):
    """<p>1. are available ...</p> ... -> ['are available ...', ...] (the lead-in dropped)."""
    out = []
    for p in _all(container, ".//p|.//li"):
        line = _text(p)
        if not line or line.lower().startswith("only those candidates"):
            continue
        line = re.sub(r"^\d+\.\s*", "", line)
        if line and line not in out:
            out.append(line)
    if not out:
        line = _text(container)
        if line:
            out = [re.sub(r"^\d+\.\s*", "", s.strip()) for s in re.split(r"\s(?=\d+\.\s)", line)
                   if s.strip() and not s.lower().startswith("only those candidates")]
    return out


def _start_window(lines):
    """'can start the internship between 16th Sep'26 and 3rd Nov'26' -> (from, to)."""
    for line in lines or []:
        match = re.search(r"between\s+(.+?)\s+and\s+(.+?)$", line, re.I)
        if match:
            return S.site_date(match.group(1)), S.site_date(match.group(2))
    return None, None


def _section_body(heading):
    """The content element(s) that follow a section heading until the next heading."""
    bodies = []
    sib = heading.getnext()
    while sib is not None and not _has_class(sib, "section_heading"):
        if sib.tag not in ("script", "style"):
            bodies.append(sib)
        sib = sib.getnext()
    return bodies


def _tabs(bodies):
    out = []
    for body in bodies:
        for tab in _all(body, ".//*[contains(@class,'round_tabs')]"):
            value = _text(tab)
            if value and value not in out:
                out.append(value)
    return out


def _stipend_breakup(bodies):
    """'Fixed pay: ₹ 4,000 /month  Incentive pay: ₹ 4,000 - 8,000 /month' -> {fixed, incentive}."""
    joined = " ".join(_text(b) or "" for b in bodies)
    fixed = re.search(r"fixed pay:\s*(.+?)(?=\s+incentive pay:|$)", joined, re.I)
    incentive = re.search(r"incentive pay:\s*(.+?)(?=\s+(?:job offer|fixed pay):|$)", joined, re.I)
    if not fixed and not incentive:
        return None
    return {"fixed": S.money(fixed.group(1)) if fixed else None,
            "incentive": S.money(incentive.group(1)) if incentive else None}


def _job_offer_note(bodies):
    joined = " ".join(_text(b) or "" for b in bodies)
    match = re.search(r"job offer:\s*(.+?)(?=\s+(?:fixed pay|incentive pay|stipend structure):|$)", joined, re.I)
    return text(match.group(1)) if match else None


def _probation(bodies):
    for body in bodies:
        box = _one(body, ".//*[contains(@class,'probation-salary-container')]") if body.tag != "div" or not _has_class(body, "probation-salary-container") else body
        if box is None:
            continue
        if "display: none" in (box.get("style") or "").replace(" ", "").replace(":", ": "):
            return None
        lines = [_text(x) for x in _all(box, ".//*[contains(@class,'probation-text') or contains(@class,'probation-text2')]")]
        lines = [l for l in lines if l]
        if not lines:
            return None
        out = {"duration": None, "salary": None, "after": None}
        for line in lines:
            low = line.lower()
            if low.startswith("duration"):
                out["duration"] = S.duration(line.split(":", 1)[-1])
            elif "during probation" in low:
                out["salary"] = S.money(line.split(":", 1)[-1])
            elif low.startswith("after probation"):
                out["after"] = S.money(line.split(":", 1)[-1])
        return out if any(out.values()) else None
    return None


def _activity(root):
    out = {"hiring_since": None, "opportunities_posted": None, "candidates_hired": None}
    for item in _all(root, "//div[contains(@class,'activity_section')]//div[contains(@class,'activity')]//div[contains(@class,'text')]"):
        line = _text(item)
        if not line:
            continue
        low = line.lower()
        if "hiring since" in low:
            out["hiring_since"] = S.month_label(line)
        elif "opportunit" in low:
            out["opportunities_posted"] = S.count_in(line)
        elif "hired" in low:
            out["candidates_hired"] = S.count_in(line)
    return out


def _ld_locations(ld):
    out = []
    for place in as_list(ld.get("jobLocation")):
        address = as_dict(as_dict(place).get("address"))
        city = text(address.get("addressLocality"))
        region = text(address.get("addressRegion"))
        country = text(address.get("addressCountry"))
        if city or region:
            out.append({"city": city, "region": region, "country": country})
    return out


def _ld_salary(ld):
    base = as_dict(ld.get("baseSalary"))
    value = as_dict(base.get("value"))
    if not value:
        return None
    unit = (text(value.get("unitText")) or "").lower()
    period = {"month": "monthly", "year": "yearly", "week": "weekly", "day": "daily", "hour": "hourly"}.get(unit)
    return {"min": S.to_int(value.get("minValue")), "max": S.to_int(value.get("maxValue")),
            "currency": text(base.get("currency")) or S.CURRENCY, "period": period}



def _header_items(head):
    """A detail header's labelled items -> {'start date': 'Starts immediately',
    'duration': '1 Month', 'stipend': '₹ 8,000 - 12,000 /month', 'apply by': ..., 'ctc (annual)': ..., 'experience': ...}."""
    items = {}
    for item in _all(head, ".//div[contains(@class,'other_detail_item')]"):
        label = (_text(_one(item, ".//div[contains(@class,'item_heading')]")) or "").lower()
        value_el = _one(item, ".//div[contains(@class,'item_body')]")
        if not label or value_el is None:
            continue
        if _one(value_el, ".//span[contains(@class,'mobile')]") is not None and _one(value_el, ".//span[contains(@class,'desktop')]") is not None:
            value = _text(_one(value_el, ".//span[contains(@class,'mobile')]"))
        else:
            value = _text(value_el)
        items[label] = value
    return items


def similar_card(el):
    """A 'Similar internships you can apply to' card on a detail page (the
    detail header's compact layout, not the listing card) -> a card object."""
    link_el = _one(el, ".//a[contains(@class,'view_detail_button')]")
    href = _attr(link_el, "href") or (el.getparent().get("link") if el.getparent() is not None else None)
    parsed = S.slug_of_link(href)
    kind = parsed[0] if parsed else "internship"
    slug = parsed[1] if parsed else None
    company_a = _one(el, ".//*[contains(@class,'company_name')]//a")
    company_slug = S.company_slug_of_link(_attr(company_a, "href"))
    cities, mode, office_days = _work_mode(_one(el, ".//*[@id='location_names']"))
    items = _header_items(el)
    ctc = next((v for k, v in items.items() if k.startswith("ctc")), None)
    out = {
        "id": _int(el.get("internshipid") or el.get("internshipId")),
        "slug": slug,
        "type": kind,
        "title": _text(_one(el, ".//*[contains(@class,'profile')]")),
        "link": S.listing_link(kind, slug) if slug else S.link(href),
        "company": {"name": _text(company_a) or _text(_one(el, ".//*[contains(@class,'company_name')]")),
                    "slug": company_slug, "link": S.company_link(company_slug),
                    "logo": logo(_attr(_one(el, ".//div[contains(@class,'internship_logo')]//img"), "src"))},
        "locations": cities,
        "work_mode": mode,
        "office_days_per_week": office_days,
        "stipend": S.money(items.get("stipend")) if items.get("stipend") else None,
        "salary": S.money(ctc, period="yearly") if ctc else None,
        "duration": S.duration(items.get("duration")) if items.get("duration") else None,
        "experience": S.experience(items.get("experience")) if items.get("experience") else None,
        "is_actively_hiring": _one(el, ".//*[contains(@class,'actively_hiring_badge')]") is not None,
    }
    if kind == "job":
        out.pop("stipend", None); out.pop("duration", None)
    else:
        out.pop("salary", None); out.pop("experience", None)
    return out

def details(markup, kind="internship", slug=None):
    """An internship / job page -> the full listing object, or None when the
    page carries no listing (a login wall or an unrelated page)."""
    root = doc(markup)
    head = _one(root, "//div[contains(@class,'detail_view')]//div[contains(@class,'individual_internship')][@internshipid or @internshipId]")
    if head is None:
        head = _one(root, "//div[contains(@class,'individual_internship')][@internshipid or @internshipId]")
    body = _one(root, "//div" + _cls("internship_details"))
    ld = _json_ld(root) or {}
    if head is None and body is None and not ld:
        return None
    head = head if head is not None else root
    body = body if body is not None else root

    company_a = _one(head, ".//*[contains(@class,'company_name')]//a")
    company_slug = S.company_slug_of_link(_attr(company_a, "href"))
    location_el = _one(head, ".//*[@id='location_names']")
    cities, mode, office_days = _work_mode(location_el)
    if not cities and not mode and ld.get("jobLocationType") == "TELECOMMUTE":
        mode = "work_from_home"

    items = _header_items(head)
    start_label = items.get("start date")
    starts_immediately = bool(start_label) and "immediately" in start_label.lower()
    stipend = S.money(items.get("stipend")) if items.get("stipend") else None
    ctc_label = next((v for k, v in items.items() if k.startswith("ctc")), None)
    salary = S.money(ctc_label, period="yearly") if ctc_label else None
    apply_by = next((v for k, v in items.items() if k.startswith("apply")), None)

    posted_el = _one(head, ".//div[contains(@class,'posted_by_container')]//div" + _cls("status"))
    status_labels = [_text(x) for x in _all(head, ".//div[contains(@class,'other_label_container')]//div" + _cls("status"))]
    status_labels = [l for l in status_labels if l]
    is_part_time = any(l.lower() == "part time" for l in status_labels)
    labels = [l for l in status_labels if l.lower() not in ("part time", "internship", "job", "fresher job")
              and not l.lower().startswith("job offer")]
    job_offer = _job_offer(_one(head, ".//div[contains(@class,'ppo_status')]//span"))
    applicants_label = _text(_one(head, ".//div[contains(@class,'applications_message')]"))
    applicants = S.count_in(applicants_label) if applicants_label and "applicant" in applicants_label.lower() \
        and not applicants_label.lower().startswith("be an early") else None
    is_early = (_one(head, ".//*[contains(@class,'early_applicant')]") is not None
                or bool(applicants_label and "early applicant" in applicants_label.lower()))
    status = _attr(_one(root, "//input[@id='status']"), "value")
    apply_link = S.link(_attr(_one(root, "//a[contains(@class,'apply_now_button')]"), "href"))

    # the body sections, keyed by their heading
    # the listing's own description sits under the heading with class
    # about_heading ("About the internship" / "About the job" / "About part
    # time job/internship"); the employer block is recognised by its content
    # (company_info / about_company_text_container), whatever its heading says
    sections = {}
    description_bodies = []
    company_bodies = []
    for heading in _all(body, ".//*[contains(@class,'section_heading')]"):
        name = (_text(heading) or "").lower()
        bodies = _section_body(heading)
        if _has_class(heading, "about_heading"):
            description_bodies = bodies
        elif any(_has_class(b, "company_info") or _has_class(b, "about_company_text_container") for b in bodies):
            company_bodies = bodies
        else:
            sections[name] = bodies

    def section(prefix):
        for name, bodies in sections.items():
            if name.startswith(prefix):
                return bodies
        return []

    description_el = description_bodies[0] if description_bodies else None
    skills = _tabs(section("skill"))
    who = _numbered_lines(section("who can apply")[0]) if section("who can apply") else []
    start_from, start_to = _start_window(who)
    requirements = _numbered_lines(section("other requirements")[0]) if section("other requirements") else []
    perks = _tabs(section("perks"))
    additional = section("additional information")
    openings = S.count_in(_text(section("number of openings")[0])) if section("number of openings") else None
    salary_bodies = section("salary")
    if salary_bodies and salary is None:
        annual = _text(_one(salary_bodies[-1], ".//p")) or _text(salary_bodies[-1])
        if annual:
            salary = S.money(re.sub(r"annual ctc:\s*", "", annual, flags=re.I), period="yearly")
    about_company = None
    company_website = None
    company_location = None
    for b in company_bodies:
        if _has_class(b, "company_info"):
            company_website = S.link(_attr(_one(b, ".//div[contains(@class,'website_link')]//a"), "href"))
            company_location = _text(_one(b, ".//div[contains(@class,'employer_location')]//span"))
        elif _has_class(b, "about_company_text_container"):
            about_company = S.multiline(_text(b))
    activity = _activity(root)
    similar = []
    similar_root = _one(root, "//div[contains(@class,'similar_job_container')]")
    if similar_root is not None:
        similar = [c for c in (similar_card(el) for el in _all(similar_root, ".//div" + _cls("individual_internship")))
                   if c.get("title") and c.get("link")]

    ld_pay = _ld_salary(ld)
    if ld_pay and (ld_pay.get("min") is not None or ld_pay.get("max") is not None):
        target = salary if kind == "job" else stipend
        if target is None:
            target = {"label": None, "min": None, "max": None, "currency": ld_pay["currency"],
                      "period": ld_pay["period"] or ("yearly" if kind == "job" else "monthly"), "is_unpaid": False}
            if kind == "job":
                salary = target
            else:
                stipend = target
        if target.get("min") is None and target.get("max") is None and not target.get("is_unpaid"):
            target["min"], target["max"] = ld_pay["min"], ld_pay["max"]
    company_name = _text(company_a) or text(as_dict(ld.get("hiringOrganization")).get("name"))
    ld_org = as_dict(ld.get("hiringOrganization"))
    employment_types = [t.strip().lower() for t in (text(ld.get("employmentType")) or "").split(",") if t.strip()]
    experience_months = S.to_int(as_dict(ld.get("experienceRequirements")).get("monthsOfExperience"))
    experience = S.experience(items.get("experience")) if items.get("experience") else None
    if experience is None and experience_months is not None:
        years = experience_months / 12
        years = int(years) if float(years).is_integer() else round(years, 1)
        experience = {"label": f"{years} year(s)", "min_years": years, "max_years": years}

    out = {
        "id": _int(head.get("internshipid") or head.get("internshipId")),
        "slug": slug,
        "type": kind,
        "title": _text(_one(head, ".//*[contains(@class,'profile')]")) or text(ld.get("title")),
        "link": S.listing_link(kind, slug),
        "status": status,
        "is_active": (status == "active") if status else None,
        "company": {
            "name": company_name,
            "slug": company_slug,
            "link": S.company_link(company_slug),
            "logo": logo(_attr(_one(head, ".//div[contains(@class,'internship_logo')]//img"), "src")) or logo(text(ld_org.get("logo"))),
            "website": company_website or S.link(text(ld_org.get("sameAs"))),
            "location": company_location,
            "about": about_company,
            "hiring_since": activity["hiring_since"],
            "opportunities_posted": activity["opportunities_posted"],
            "candidates_hired": activity["candidates_hired"],
        },
        "locations": cities,
        "location_details": _ld_locations(ld),
        "work_mode": mode,
        "office_days_per_week": office_days,
        "is_part_time": is_part_time,
        "employment_types": employment_types,
        "category": text(ld.get("occupationalCategory")),
        "industry": text(ld.get("industry")),
        "start_date": {
            "label": start_label,
            "starts_immediately": starts_immediately,
            "date": None if starts_immediately else S.site_date(start_label),
            "window_from": start_from,
            "window_to": start_to,
        },
        "duration": S.duration(items.get("duration")) if items.get("duration") else None,
        "stipend": stipend,
        "stipend_breakup": _stipend_breakup(additional) if additional else None,
        "salary": salary,
        "probation": _probation(salary_bodies) if salary_bodies else None,
        "experience": experience,
        "apply_by": {"label": apply_by, "date": S.site_date(apply_by) or S.site_date(text(ld.get("validThrough")))} if apply_by or ld.get("validThrough") else None,
        "posted": S.posted(_text(posted_el)),
        "posted_date": S.site_date(text(ld.get("datePosted"))),
        "applicants": applicants,
        "openings": openings if openings is not None else S.to_int(ld.get("totalJobOpenings")),
        "is_actively_hiring": _one(head, ".//*[contains(@class,'actively_hiring_badge')]") is not None,
        "is_early_applicant": is_early,
        "job_offer": job_offer,
        "job_offer_note": _job_offer_note(additional) if additional else None,
        "labels": labels,
        "description": S.html_to_text(_inner_html(description_el)) if description_el is not None else S.html_to_text(text(ld.get("description"))),
        "description_html": _inner_html(description_el),
        "skills": skills or S.split_list(text(ld.get("skills"))),
        "who_can_apply": who,
        "other_requirements": requirements,
        "perks": perks,
        "additional_information": S.multiline(" \n".join(_text(b) or "" for b in additional)) if additional else None,
        "apply_link": apply_link,
        "similar_listings": similar,
    }
    if kind == "job":
        for key in ("stipend", "stipend_breakup", "duration", "job_offer", "job_offer_note"):
            out.pop(key, None)
    else:
        for key in ("salary", "probation", "experience"):
            out.pop(key, None)
    return out


# ---- company pages --------------------------------------------------------------------------------------

def _bg_image(el):
    style = el.get("style") if el is not None else None
    match = re.search(r"url\(['\"]?([^'\")]+)", style or "")
    return S.link(match.group(1)) if match else None


def company_card(el):
    """A company page opening card (div.card / div.openings-card) -> a compact listing."""
    a = _one(el, ".//a")
    href = _attr(a, "href")
    parsed = S.slug_of_link(href)
    kind = parsed[0] if parsed else None
    slug = parsed[1] if parsed else None
    label = _text(_one(el, ".//*[contains(@class,'job-label')]"))
    pay_label = _text(_one(el, ".//li[.//i[contains(@class,'ic-16-money')]]"))
    locations = S.split_list(_text(_one(el, ".//li[.//i[contains(@class,'ic-16-map-pin')]]")))
    remote = any(l.lower() == "work from home" for l in locations) or _one(el, ".//li[.//i[contains(@class,'ic-16-home')]]") is not None
    out = {
        "id": S.slug_id(slug),
        "slug": slug,
        "type": kind,
        "listing_type": label,
        "title": _text(_one(el, ".//*[contains(@class,'h6')]")),
        "link": S.listing_link(kind, slug) if slug else S.link(href),
        "locations": [l for l in locations if l.lower() != "work from home"],
        "work_mode": "work_from_home" if remote else ("in_office" if locations else None),
        "is_actively_hiring": _one(el, ".//*[contains(@class,'actively-hiring')]") is not None,
    }
    if kind == "job":
        out["salary"] = S.money(pay_label, period="yearly") if pay_label else None
    else:
        out["stipend"] = S.money(pay_label) if pay_label else None
        out["duration"] = S.duration(_text(_one(el, ".//li[.//i[contains(@class,'ic-16-calendar')]]")))
    return out


def _salary_cards(root):
    out = []
    for el in _all(root, "//div[contains(@class,'salaries-container')]//div[contains(@class,'card')]"):
        title = _text(_one(el, ".//*[contains(@class,'job-title')]"))
        pay = _text(_one(el, ".//*[contains(@class,'salary')]"))
        if title or pay:
            out.append({"title": title, "pay": S.money(pay)})
    return out


def _perks(root):
    out = []
    for el in _all(root, "//div[contains(@class,'perks-container')]//*[contains(@class,'perk-name')]"):
        value = _text(el)
        if value and value not in out:
            out.append(value)
    return out


def company_profile(markup, slug=None):
    """The company overview page -> profile + preview openings + salaries + perks; None when no profile."""
    root = doc(markup)
    name = _text(_one(root, "//h1[contains(@class,'heading-text')]")) or _text(_one(root, "//*[contains(@class,'heading-text')]"))
    if not name:
        return None
    header = _one(root, "//*[@id='company-page-header']")
    if header is None:
        header = root
    highlights = {}
    for item in _all(root, "//div[contains(@class,'highlights')]//div[contains(@class,'highlight')]"):
        key = (_text(_one(item, ".//div[contains(@class,'name')]")) or "").lower()
        value = _text(_one(item, ".//div[contains(@class,'value')]"))
        if key:
            highlights[key] = value
    about = _one(root, "//div[contains(@class,'about-container')]")
    website = S.link(_attr(_one(about, ".//a[contains(@class,'link-text')]"), "href")) if about is not None else None
    about_text = S.multiline(_text(_one(about, ".//p"))) if about is not None else None
    hiring_since = next((v for k, v in highlights.items() if k.startswith("hiring")), None)
    openings = [company_card(el) for el in _all(root, "//div[contains(@class,'internships-jobs-section')]//div[contains(@class,'card')][.//a]")]
    return {
        "name": name,
        "slug": slug,
        "link": S.company_link(slug),
        "logo": logo(_bg_image(_one(header, ".//div[contains(@class,'logo')]"))),
        "location": _text(_one(header, ".//div[contains(@class,'heading')]/p")) or highlights.get("location"),
        "industry": highlights.get("industry"),
        "employee_count": highlights.get("employee count"),
        "hiring_since": _int(hiring_since) if hiring_since and hiring_since.isdigit() else hiring_since,
        "opportunities_posted": S.count_in(next((v for k, v in highlights.items() if k.startswith("opportunit")), None)),
        "candidates_hired": S.count_in(next((v for k, v in highlights.items() if k.startswith("candidates")), None)),
        "website": website,
        "about": about_text,
        "openings_preview": [o for o in openings if o.get("title")],
        "salaries": _salary_cards(root),
        "perks": _perks(root),
    }


def company_openings(markup):
    """The company careers page -> every opening card (the large layout's list)."""
    root = doc(markup)
    container = _one(root, "//div[contains(@class,'cards-container-lg')]")
    if container is None:
        container = root
    out = []
    seen = set()
    for el in _all(container, ".//div[contains(@class,'openings-card')]"):
        item = company_card(el)
        key = item.get("slug") or item.get("link")
        if key and key not in seen and item.get("title"):
            seen.add(key)
            out.append(item)
    return out


def company_salaries(markup):
    root = doc(markup)
    return {"salaries": _salary_cards(root), "perks": _perks(root)}


# ---- vocabularies -----------------------------------------------------------------------------------------

def _options(view):
    from urllib.parse import unquote
    out = []
    for value, label in re.findall(r"<option value=\"([^\"]+)\">([^<]+)</option>", view or ""):
        slug = S.arg_slug(unquote(value))
        name = text(label)
        if slug and name:
            out.append({"name": name, "slug": slug})
    return out


def criteria(raw):
    raw = as_dict(raw)
    categories = _options(raw.get("categoryView"))
    locations = _options(raw.get("cityView"))
    if not categories:
        categories = [{"name": text(c.get("label") or c.get("name")), "slug": S.arg_slug(c.get("name"))}
                      for c in as_list(raw.get("categoryArray")) if isinstance(c, dict)]
    if not locations:
        locations = [{"name": text(c), "slug": S.arg_slug(c)} for c in as_list(raw.get("cityArray")) if isinstance(c, str)]
    return {"categories": categories, "locations": locations}


def autocomplete(raw):
    raw = as_dict(raw)
    out = []
    for item in as_list(raw.get("result")):
        value = text(item.get("label") or item.get("name")) if isinstance(item, dict) else text(item)
        if value and value not in out:
            out.append(value)
    return out
