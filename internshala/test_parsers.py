"""Offline tests: refs resolvers, marshmallow schemas, value helpers, the
listing path grammar, parsers and the endpoint functions with the transport
monkeypatched to serve fixtures (internshala/fixtures/*.gz, raw listing JSON
and pages captured 2026-10-19 from internshala.com) — no network.

    python -m pytest internshala/test_parsers.py -q
"""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from internshala import companies, details, fetch, listings, lookups, parsers as P, refs, schemas, shared as S  # noqa: E402
from schema_fields import load_query  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
RELIANCE = "marketing-sales-internship-in-multiple-locations-at-reliance-nippon-life-insurance1789563888"
TUTOR = "remote-part-time-part-time-tutor-work-from-home-job-at-planetspark1792389837"


def fx(name):
    path = os.path.join(FX, name)
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json.gz") else f.read()


# ---- refs ------------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (f"https://internshala.com/internship/detail/{RELIANCE}", ("internship", RELIANCE)),
    (f"https://internshala.com/internship/detail/{RELIANCE}?utm_source=cp_link&referral=web_share", ("internship", RELIANCE)),
    (f"internshala.com/job/detail/{TUTOR}", ("job", TUTOR)),
    (f"/job/details/{TUTOR}", ("job", TUTOR)),
    (RELIANCE, ("internship", RELIANCE)),
])
def test_resolve_internship(value, expected):
    assert refs.resolve_internship(value) == {"kind": expected[0], "slug": expected[1]}


def test_resolve_job_defaults_kind():
    assert refs.resolve_job(TUTOR) == {"kind": "job", "slug": TUTOR}
    assert refs.resolve_job(f"https://internshala.com/internship/detail/{RELIANCE}")["kind"] == "internship"


@pytest.mark.parametrize("value", ["", "marketing", "https://example.com/internship/detail/x1", "https://internshala.com/internships/"])
def test_resolve_listing_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_internship(value)


@pytest.mark.parametrize("value,expected", [
    ("planetspark-1580118881", {"slug": "planetspark-1580118881", "name": None}),
    ("https://internshala.com/company/reliance-nippon-life-insurance-1543381830/careers/?utm_source=x",
     {"slug": "reliance-nippon-life-insurance-1543381830", "name": None}),
    ("PlanetSpark", {"slug": None, "name": "PlanetSpark"}),
    ("  Reliance   Nippon ", {"slug": None, "name": "Reliance Nippon"}),
])
def test_resolve_company(value, expected):
    assert refs.resolve_company(value) == expected


@pytest.mark.parametrize("value", ["", "https://example.com/company/x-1", "https://internshala.com/internships/", "a/b"])
def test_resolve_company_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_company(value)


@pytest.mark.parametrize("value,expected", [
    ("Web Development", "web-development"), ("web-development", "web-development"), ("Human Resources (HR)", "hr"),
    ("hr", "hr"), ("Agriculture & Food Engineering", "agriculture-and-food-engineering"), ("marketing", "marketing"),
    ("UI/UX Design", "ui/ux"), ("ui ux design", "ui/ux"),
])
def test_resolve_category(value, expected):
    assert refs.resolve_category(value) == expected


def test_resolve_category_rejects():
    with pytest.raises(ValueError):
        refs.resolve_category("Underwater Basket Weaving")


@pytest.mark.parametrize("value,expected", [("Delhi", "delhi"), ("New Delhi", "new-delhi"), ("new-delhi", "new-delhi"),
                                            ("navi mumbai", "navi-mumbai")])
def test_resolve_location(value, expected):
    assert refs.resolve_location(value) == expected


# ---- shared helpers ------------------------------------------------------------------------------

@pytest.mark.parametrize("label,low,high,period", [
    ("₹ 8,000 - 12,000 /month", 8000, 12000, "monthly"),
    ("₹ 10,000 /month", 10000, 10000, "monthly"),
    ("₹ 3,50,000 - 4,50,000 /year", 350000, 450000, "yearly"),
    ("₹ 800 - 3,000 lump sum", 800, 3000, "lump_sum"),
    ("₹ 4LPA", 400000, 400000, "yearly"),
    ("₹ 8.2LPA", 820000, 820000, "yearly"),
    ("₹ 4 - 6 LPA", 400000, 600000, "yearly"),
])
def test_money(label, low, high, period):
    out = S.money(label)
    assert (out["min"], out["max"], out["period"], out["currency"]) == (low, high, period, "INR")
    assert out["is_unpaid"] is False


def test_money_unpaid_and_empty():
    assert S.money("Unpaid") == {"label": "Unpaid", "min": 0, "max": 0, "currency": "INR", "period": None, "is_unpaid": True}
    assert S.money("") is None
    assert S.money("₹ 3,50,000 - 4,50,000", period="yearly")["period"] == "yearly"


@pytest.mark.parametrize("label,months", [("3 Months", 3), ("1 Month", 1), ("2 Weeks", 0.5), ("6 Months", 6)])
def test_duration(label, months):
    assert S.duration(label) == {"label": label, "months": months}


@pytest.mark.parametrize("label,low,high", [("1 year(s)", 1, 1), ("0-2 years", 0, 2), ("Fresher", 0, 0),
                                            ("No experience required", 0, 0)])
def test_experience(label, low, high):
    out = S.experience(label)
    assert (out["min_years"], out["max_years"]) == (low, high)


@pytest.mark.parametrize("label,days", [("Few hours ago", 0), ("Just now", 0), ("Today", 0), ("1 day ago", 1),
                                        ("2 days ago", 2), ("Posted 3 weeks ago", 21), ("1 week ago", 7)])
def test_posted(label, days):
    from datetime import date
    out = S.posted(label, today=date(2026, 10, 19))
    assert out["days_ago"] == days and out["date"] is not None


@pytest.mark.parametrize("label,iso", [("3 Nov' 26", "2026-11-03"), ("18th Oct'26", "2026-10-18"), ("16th Sep'26", "2026-09-16"),
                                       ("2026-11-18 23:59:59", "2026-11-18"), ("June 2025", "2025-06-01"), ("", None)])
def test_site_date(label, iso):
    assert S.site_date(label) == iso


def test_links_and_slugs():
    assert S.link("/internship/detail/x1?utm_source=company_pages&referral=company_pages") == "https://internshala.com/internship/detail/x1"
    assert S.slug_of_link("/job/detail/abc123?x=1") == ("job", "abc123")
    assert S.company_slug_of_link("/company/planetspark-1580118881\\") == "planetspark-1580118881"
    assert S.arg_slug("  New   Delhi ") == "new-delhi"
    assert S.path_segment("ui/ux-design") == "ui%2Fux-design"
    assert S.count_in("544 applicants") == 544 and S.count_in("1,261 opportunities posted") == 1261


# ---- path grammar ------------------------------------------------------------------------------------

def test_internship_segments():
    assert listings.internship_segments() == []
    assert listings.internship_segments(category="marketing", location="delhi", min_stipend=5000) == \
        ["marketing-internship-in-delhi", "stipend-5000"]
    assert listings.internship_segments(query="machine learning", work_from_home=True, part_time=True) == \
        ["keywords-machine%20learning", "work-from-home-internships", "part-time-true"]
    assert listings.internship_segments(work_from_home=True, category="marketing") == ["work-from-home-marketing-internships"]
    assert listings.internship_segments(location="delhi", duration=2, start_date="2026-11-01", with_job_offer=True,
                                        fast_response=True, early_applicant=True, international=True, big_brand=True) == \
        ["internship-in-delhi", "international-internship", "duration-2", "start-date-20261101", "ppo-true",
         "fast-response-true", "early-applicant-25", "big-brand"]
    assert fetch.listing_path("internships", ["marketing-internship-in-delhi", "stipend-5000"], 2) == \
        "/internships_ajax/marketing-internship-in-delhi/stipend-5000/page-2/"


def test_job_segments():
    assert listings.job_segments() == []
    assert listings.job_segments(category="marketing", location="mumbai", min_salary=300000, experience="1") == \
        ["marketing-jobs-in-mumbai", "salary-300000", "experience-1"]
    assert listings.job_segments(part_time=True, work_from_home=True) == ["part-time-work-from-home-jobs"]
    assert listings.job_segments(location="delhi", experience="fresher") == ["jobs-in-delhi"]
    assert listings.job_segments(query="react", experience="5plus") == ["keywords-react", "experience-5plus"]


# ---- schemas --------------------------------------------------------------------------------------------

def test_internship_search_schema():
    data, error = load_query(schemas.InternshipSearchSchema, {"category": "Web Development", "location": "New Delhi",
                                                              "work_from_home": "1", "min_stipend": "5000", "page": "2"})
    assert error is None
    assert data["category"] == "web-development" and data["location"] == "new-delhi" and data["work_from_home"] is True
    assert data["min_stipend"] == 5000 and data["page"] == 2 and data["part_time"] is None
    assert load_query(schemas.InternshipSearchSchema, {"category": "Nope"})[1]["errors"]["category"]
    assert load_query(schemas.InternshipSearchSchema, {"foo": "bar"})[1]["errors"]["foo"]
    assert load_query(schemas.InternshipSearchSchema, {"start_date": "2026/11/01"})[1]["errors"]["start_date"]


def test_job_search_schema():
    data, error = load_query(schemas.JobSearchSchema, {"experience": "fresher", "min_salary": "300000"})
    assert error is None and data["experience"] == "fresher" and data["min_salary"] == 300000
    assert load_query(schemas.JobSearchSchema, {"experience": "10"})[1]["errors"]["experience"]
    assert load_query(schemas.JobSearchSchema, {"min_stipend": "1"})[1]["errors"]["min_stipend"]


def test_ref_schemas():
    assert load_query(schemas.InternshipSchema, {"internship": RELIANCE})[0]["internship"]["slug"] == RELIANCE
    assert load_query(schemas.JobSchema, {})[1]["errors"]["job"]
    assert load_query(schemas.CompanySchema, {"company": "PlanetSpark"})[0]["company"] == {"slug": None, "name": "PlanetSpark"}
    data, _ = load_query(schemas.CompanyOpeningsSchema, {"company": "planetspark-1580118881", "type": "JOBS"})
    assert data["type"] == "jobs" and data["page"] == 1
    assert load_query(schemas.AutocompleteSchema, {"query": "py"})[1]["errors"]["query"]
    assert load_query(schemas.AutocompleteSchema, {"query": "pyth", "type": "location"})[0]["type"] == "location"
    assert load_query(schemas.BoardSchema, {})[0]["type"] == "internships"


# ---- parsers: listings ---------------------------------------------------------------------------------

def test_listing_internships():
    result = P.listing_result(fx("listing_internships.json.gz"), 1, "internship")
    assert result["heading"] == "3675 Internships in Delhi" and result["filters_applied"] == 3
    assert result["pagination"] == {"page": 1, "items_per_page": 56, "total_pages": 36, "total_count": 3675, "is_last_page": False}
    first = result["listings"][0]
    assert first["id"] == 3310208 and first["type"] == "internship" and first["title"] == "Social Work - Female"
    assert first["link"] == "https://internshala.com/internship/detail/social-work-internship-in-delhi-at-milestone1791357333"
    assert first["company"]["name"] == "Milestone" and first["company"]["logo"].startswith("https://")
    assert first["locations"] == ["Delhi"] and first["work_mode"] == "hybrid" and first["office_days_per_week"] == 5
    assert first["stipend"]["min"] == 3000 and first["duration"]["months"] == 1
    assert first["skills"] == ["English Proficiency (Spoken)", "Effective Communication"]
    assert first["posted"]["days_ago"] == 7 and first["is_actively_hiring"] is True
    assert "salary" not in first and "experience" not in first
    modes = {c["work_mode"] for c in result["listings"]}
    assert "hybrid" in modes and "in_office" in modes
    assert all(c["stipend"] for c in result["listings"]) and all(c["slug"] for c in result["listings"])


def test_listing_internships_job_offer_badge():
    result = P.listing_result(fx("listing_internships_p2.json.gz"), 2, "internship")
    assert result["pagination"]["page"] == 2 and result["pagination"]["total_count"] == 7027
    offers = [c["job_offer"] for c in result["listings"] if c["job_offer"]]
    assert offers and offers[0]["max_ctc"]["min"] == 400000 and offers[0]["max_ctc"]["period"] == "yearly"
    assert any(c["is_early_applicant"] for c in result["listings"])


def test_listing_jobs():
    result = P.listing_result(fx("listing_jobs.json.gz"), 2, "job")
    assert result["pagination"]["total_count"] == 6523 and result["pagination"]["total_pages"] == 164
    first = result["listings"][0]
    assert first["type"] == "job" and first["title"] == "Part Time Tutor - Work From Home"
    assert first["work_mode"] == "work_from_home" and first["locations"] == [] and first["is_part_time"] is True
    assert first["salary"] == {"label": "₹ 3,50,000 - 4,50,000 /year", "min": 350000, "max": 450000, "currency": "INR",
                               "period": "yearly", "is_unpaid": False}
    assert first["experience"]["min_years"] == 1 and "stipend" not in first and "duration" not in first
    assert first["skills"][0] == "Teaching" and first["posted"]["days_ago"] == 0


def test_listing_result_tolerates_junk():
    assert P.listing_result({}, 1)["listings"] == []
    assert P.listing_result({"internship_list_html": "<div>nope</div>", "seo": None}, 3)["pagination"]["page"] == 3
    assert P.listing_result(None, 1)["pagination"]["total_count"] is None


# ---- parsers: details ---------------------------------------------------------------------------------

def test_internship_details():
    d = P.details(fx("detail_internship.html.gz"), "internship", RELIANCE)
    assert d["id"] == 3289274 and d["title"] == "Marketing & Sales" and d["status"] == "active" and d["is_active"] is True
    assert d["link"] == f"https://internshala.com/internship/detail/{RELIANCE}"
    assert d["company"]["name"] == "Reliance Nippon Life Insurance"
    assert d["company"]["slug"] == "reliance-nippon-life-insurance-1543381830"
    assert d["company"]["website"] == "https://www.reliancenipponlife.com/"
    assert d["company"]["hiring_since"] == "2025-06" and d["company"]["opportunities_posted"] == 5
    assert d["company"]["about"].startswith("Reliance Capital Limited")
    assert d["locations"] == ["Lucknow", "Pune", "Hyderabad"] and d["work_mode"] == "in_office"
    assert d["start_date"]["starts_immediately"] is True
    assert d["start_date"]["window_from"] == "2026-09-16" and d["start_date"]["window_to"] == "2026-11-03"
    assert d["duration"]["months"] == 1 and d["stipend"]["min"] == 8000 and d["stipend"]["max"] == 12000
    assert d["stipend_breakup"]["fixed"]["min"] == 4000 and d["stipend_breakup"]["incentive"]["max"] == 8000
    assert d["apply_by"]["date"] == "2026-11-03" and d["posted"]["days_ago"] == 21
    assert d["applicants"] == 544 and d["openings"] == 20 and d["is_actively_hiring"] is True
    assert d["skills"] == ["English Proficiency (Spoken)", "Hindi Proficiency (Spoken)", "Lead Generation", "Marketing",
                           "Marketing Strategy", "Networking"]
    assert len(d["who_can_apply"]) == 5 and d["who_can_apply"][0].startswith("are available for full time")
    assert len(d["other_requirements"]) == 6 and d["perks"] == ["Certificate", "Flexible work hours", "Informal dress code"]
    assert d["description"].startswith("Got the hustle") and "<br" in d["description_html"]
    assert d["apply_link"].startswith("https://internshala.com/student/interstitial/application/")
    assert len(d["similar_listings"]) == 3 and d["similar_listings"][0]["company"]["slug"] == "scaleon-consulting-1771662383"
    assert d["similar_listings"][0]["stipend"]["min"] == 4000 and d["similar_listings"][0]["office_days_per_week"] == 2
    assert "salary" not in d and "probation" not in d


def test_internship_details_job_offer_and_json_ld():
    d = P.details(fx("detail_internship_job_offer.html.gz"), "internship", "graphic-design-internship-in-mumbai-at-simit-bhagat-studios1792384358")
    assert d["job_offer"]["max_ctc"]["max"] == 400000
    assert d["job_offer_note"].startswith("On successful conversion")
    assert d["is_early_applicant"] is True and d["applicants"] is None
    assert d["posted_date"] == "2026-10-19" and d["apply_by"]["date"] == "2026-11-18"
    assert d["location_details"] == [{"city": "Mumbai", "region": "Maharashtra", "country": "IN"}]
    assert d["category"] == "Graphic Design" and d["industry"] == "Marketing"
    assert d["employment_types"] == ["intern", "full_time"] and d["openings"] == 2
    assert d["perks"][-1] == "Job offer" and d["company"]["candidates_hired"] == 137


def test_job_details():
    d = P.details(fx("detail_job.html.gz"), "job", TUTOR)
    assert d["type"] == "job" and d["title"] == "Part Time Tutor - Work From Home" and d["is_part_time"] is True
    assert d["work_mode"] == "work_from_home" and d["locations"] == []
    assert d["salary"]["min"] == 350000 and d["salary"]["max"] == 450000 and d["salary"]["period"] == "yearly"
    assert d["experience"]["min_years"] == 1 and d["probation"] is None
    assert d["employment_types"] == ["part_time", "contractor"] and d["category"] == "Teaching"
    assert d["company"]["location"] == "Gurgaon" and d["company"]["website"] == "https://www.planetspark.in/"
    assert d["company"]["hiring_since"] == "2023-11" and d["company"]["candidates_hired"] == 23
    assert d["applicants"] == 29 and d["openings"] == 20 and d["apply_by"]["date"] == "2026-11-18"
    assert d["who_can_apply"] == ["have minimum 1 years of experience"]
    assert d["description"].startswith("Key Responsibilities") and "stipend" not in d and "duration" not in d


def test_internship_details_part_time_heading():
    # the description heading reads "About part time job/internship" here, not "About the internship"
    d = P.details(fx("detail_internship_part_time.html.gz"), "internship",
                  "part-time-software-development-internship-in-bangalore-at-salesforce1789133363")
    assert d["description"].startswith("As a Software Development intern at Salesforce") and d["description_html"]
    assert d["company"]["name"] == "Salesforce" and d["company"]["about"] and d["company"]["slug"] is None
    assert d["stipend"]["min"] == 100000 and d["is_part_time"] is True and d["applicants"] == 1000
    assert d["perks"] and d["skills"][0] == ".NET" and len(d["who_can_apply"]) == 4


def test_placeholder_logos_are_null():
    assert P.logo("/static/images/search/placeholder_logo.svg") is None
    assert P.logo("https://internshala.com/static/images/company/logo.svg") is None
    assert P.logo("https://internshala-uploads.internshala.com/logo%2Fx.png.webp").startswith("https://internshala-uploads")
    assert P.logo(None) is None


def test_details_tolerates_junk():
    assert P.details("<html><body>login</body></html>", "internship", "x") is None
    assert P.details("", "job", "x") is None


# ---- parsers: companies --------------------------------------------------------------------------------

def test_company_profile():
    c = P.company_profile(fx("company_overview.html.gz"), "reliance-nippon-life-insurance-1543381830")
    assert c["name"] == "Reliance Nippon Life Insurance" and c["location"] == "Mumbai, India"
    assert c["industry"].startswith("Banking") and c["employee_count"] == "5001-10000"
    assert c["hiring_since"] == 2018 and c["opportunities_posted"] == 22 and c["candidates_hired"] == 1
    assert c["website"] == "https://www.reliancenipponlife.com/" and c["logo"].startswith("https://")
    assert c["about"].startswith("Reliance Capital Limited")
    assert len(c["openings_preview"]) == 2 and c["openings_preview"][0]["stipend"]["min"] == 6000
    assert c["salaries"][0] == {"title": "Business Development (Sales)", "pay": S.money("₹ 8,000 /month")}
    assert c["perks"]
    assert P.company_profile("<html></html>") is None


def test_company_openings_and_salaries():
    openings = P.company_openings(fx("company_careers.html.gz"))
    assert len(openings) == 6 and openings[0]["type"] == "job" and openings[0]["listing_type"] == "Fresher Job"
    assert openings[0]["salary"]["min"] == 650000 and openings[0]["locations"] == ["Faridabad", "Delhi", "Ghaziabad"]
    extra = P.company_salaries(fx("company_salaries.html.gz"))
    assert "Certificate" in extra["perks"] and "Health insurance" in extra["perks"]


# ---- parsers: vocabularies -----------------------------------------------------------------------------

def test_criteria():
    out = P.criteria(fx("criteria_internships.json.gz"))
    assert len(out["categories"]) == 163 and len(out["locations"]) == 637
    assert {"name": "Human Resources (HR)", "slug": "hr"} in out["categories"]
    assert {"name": "New Delhi", "slug": "new-delhi"} in out["locations"]
    assert P.autocomplete({"success": True, "result": ["Python/Django"]}) == ["Python/Django"]
    assert P.autocomplete(None) == []


# ---- endpoint functions on fixtures -------------------------------------------------------------------

def test_endpoints_on_fixtures(monkeypatch):
    calls = []

    def fake_listing(board, segments, page=1, label=None):
        calls.append(("listing", board, list(segments), page))
        if board == "jobs":
            return fx("listing_jobs.json.gz")
        return fx("listing_internships.json.gz")

    def fake_page(path, label=None):
        calls.append(("page", path))
        if "/job/detail/" in path:
            return fx("detail_job.html.gz")
        if "/internship/detail/" in path:
            return fx("detail_internship.html.gz")
        if path.endswith("/salaries-perks/"):
            return fx("company_salaries.html.gz")
        if path.endswith("/careers/"):
            return fx("company_careers.html.gz")
        return fx("company_overview.html.gz")

    monkeypatch.setattr(fetch, "listing", fake_listing)
    monkeypatch.setattr(fetch, "page", fake_page)
    monkeypatch.setattr(fetch, "criteria", lambda kind="internships": fx("criteria_internships.json.gz"))
    monkeypatch.setattr(fetch, "autocomplete", lambda kind, query, args=None: {"result": ["Python/Django"]})

    out = listings.internships(category="marketing", location="delhi", min_stipend=5000, page=1)
    assert out["filters"] == {"category": "Marketing", "location": "Delhi", "min_stipend": 5000}
    assert len(out["internships"]) == 56 and calls[-1] == ("listing", "internships", ["marketing-internship-in-delhi", "stipend-5000"], 1)
    out = listings.jobs(experience="fresher", work_from_home=True, page=2)
    assert calls[-1] == ("listing", "fresher_jobs", ["work-from-home-jobs"], 2) and out["jobs"]
    out = listings.jobs(for_women=True, experience="fresher")
    assert calls[-1] == ("listing", "jobs_for_women", ["job_type-fresher_job"], 1)

    assert details.internship({"kind": "internship", "slug": RELIANCE})["id"] == 3289274
    assert details.job({"kind": "job", "slug": TUTOR})["id"] == 3319720

    # the company-scoped listing fixture carries no Reliance cards: the
    # "similar" fill is stripped and the careers page serves the openings
    c = companies.details({"slug": "reliance-nippon-life-insurance-1543381830", "name": None})
    assert c["name"] == "Reliance Nippon Life Insurance" and "openings_preview" not in c
    assert c["jobs_count"] == 6 and c["internships"] == [] and c["jobs"][0]["type"] == "job"
    assert "Health insurance" in c["perks"]

    assert lookups.categories()["count"] == 163 and lookups.locations("jobs")["count"] == 637
    assert lookups.autocomplete("pyth")["suggestions"] == [{"name": "Python/Django", "slug": "python/django"}]


def test_never_direct_without_opt_in(monkeypatch):
    import config
    monkeypatch.setattr(config, "internshala_proxy", lambda fallback=False: None)
    monkeypatch.delattr(config, "INTERNSHALA_ALLOW_DIRECT", raising=False)
    with pytest.raises(fetch.InternshalaUpstreamError, match="never contacted"):
        fetch.listing("internships", [], 1)
    monkeypatch.setattr(config, "INTERNSHALA_ALLOW_DIRECT", True, raising=False)
    assert fetch._proxy() is None


def test_company_listings_strip_similar_fill(monkeypatch):
    raw = fx("listing_internships.json.gz")
    raw["seo"]["company_name"] = "Milestone"
    monkeypatch.setattr(fetch, "listing", lambda board, segments, page=1, label=None: raw)
    out = listings.company_listings("milestone", "internships", 1)
    assert out["company"] == "Milestone" and all(c["company"]["name"] == "Milestone" for c in out["listings"])
    assert out["pagination"]["total_count"] == len(out["listings"]) and out["pagination"]["is_last_page"] is True
    raw["seo"]["company_name"] = ""
    with pytest.raises(fetch.InternshalaNotFound):
        listings.company_listings("nobody", "internships", 1)
