"""Live endpoint smoke tests: one call per /internshala/* route against a
running service, with example values proven to return data (2026-10-19).
The listing tooling (derive_facts.py) reads each route's FIRST call from
this file's AST as its working example, so the values stay literals.

Skipped unless INTERNSHALA_BASE points at a running service:

    SCRAPERS_PORT=6090 ONLY_SCRAPER=internshala python run.py
    INTERNSHALA_BASE=http://127.0.0.1:6090 python -m pytest internshala/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("INTERNSHALA_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set INTERNSHALA_BASE to run live endpoint tests")


def call(path, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=300)
    assert resp.status_code == 200, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def status(path, **params):
    from curl_cffi import requests
    return requests.get(BASE + path, params=params, timeout=300).status_code


def test_internship_search():
    body = call("/internshala/internships/search", category="Marketing", location="Delhi", min_stipend=5000)
    assert body["count"] > 100 and body["internships"] and body["next"] and body["total_pages"] > 1
    assert body["filters"] == {"category": "Marketing", "location": "Delhi", "min_stipend": 5000}
    first = body["internships"][0]
    assert first["id"] and first["title"] and first["link"].startswith("https://internshala.com/internship/detail/")
    assert first["stipend"]["min"] is not None and first["company"]["name"] and first["posted"]["label"]
    page2 = call("/internshala/internships/search", category="Marketing", location="Delhi", min_stipend=5000, page=2)
    # the site repeats a few promoted cards across pages; the bulk must be new
    assert len({i["id"] for i in page2["internships"]} - {i["id"] for i in body["internships"]}) > 20
    body = call("/internshala/internships/search", query="python", work_from_home="true", part_time="true")
    assert body["internships"] and all(i["work_mode"] == "work_from_home" for i in body["internships"])
    assert all(i["is_part_time"] for i in body["internships"])
    body = call("/internshala/internships/search", with_job_offer="true", duration=2, for_women="true")
    assert body["internships"]
    assert status("/internshala/internships/search", category="Underwater Basket") == 400
    assert status("/internshala/internships/search", foo="bar") == 400


def test_internship_details():
    body = call("/internshala/internships/details",
                internship="https://internshala.com/internship/detail/part-time-software-development-internship-in-bangalore-at-salesforce1789133363")
    assert body["company"]["name"] == "Salesforce" and body["stipend"]["min"] == 100000 and body["skills"]
    listing = call("/internshala/internships/search", category="Web Development")
    link = listing["internships"][0]["link"]
    body = call("/internshala/internships/details", internship=link)
    assert body["link"] == link and body["description"] and body["skills"] and body["company"]["name"]
    assert body["apply_by"]["date"] and body["openings"] and body["posted"]["label"] and body["is_active"] is True
    assert body["company"]["slug"] and body["company"]["link"].startswith("https://internshala.com/company/")
    slug = link.rsplit("/", 1)[-1]
    assert call("/internshala/internships/details", internship=slug)["id"] == body["id"]
    assert status("/internshala/internships/details", internship="no-such-internship-at-nowhere1234567890") == 404
    assert status("/internshala/internships/details", internship="https://example.com/x") == 400


def test_job_search():
    body = call("/internshala/jobs/search", category="Marketing", location="Mumbai", min_salary=300000, experience=1)
    assert body["count"] > 5 and body["jobs"] and body["jobs"][0]["salary"]["min"] >= 300000
    assert body["jobs"][0]["link"].startswith("https://internshala.com/job/detail/")
    body = call("/internshala/jobs/search", query="react", work_from_home="true", experience="fresher")
    assert body["jobs"] and body["heading"].endswith("Fresher Jobs")
    body = call("/internshala/jobs/search", part_time="true")
    assert body["jobs"] and all(j["is_part_time"] for j in body["jobs"])
    assert status("/internshala/jobs/search", experience="10") == 400


def test_job_details():
    body = call("/internshala/jobs/details", job="https://internshala.com/job/detail/remote-data-scientist-job-at-quickhyre1792131425")
    assert body["title"] == "Data Scientist" and body["salary"]["min"] == 3300000 and body["work_mode"] == "work_from_home"
    listing = call("/internshala/jobs/search", location="Bangalore")
    link = listing["jobs"][0]["link"]
    body = call("/internshala/jobs/details", job=link)
    assert body["type"] == "job" and body["salary"] and body["description"] and body["experience"]
    assert body["company"]["slug"] and body["apply_by"]["date"]


def test_company_details():
    body = call("/internshala/companies/details", company="planetspark-1580118881")
    assert body["name"] == "PlanetSpark" and body["location"] and body["industry"] and body["website"]
    assert body["jobs_count"] > 0 and body["jobs"][0]["company"]["name"] == "PlanetSpark" and body["perks"]
    body = call("/internshala/companies/details", company="https://internshala.com/company/reliance-nippon-life-insurance-1543381830/careers/")
    assert body["slug"] == "reliance-nippon-life-insurance-1543381830" and body["salaries"]
    body = call("/internshala/companies/details", company="PlanetSpark")
    assert body["slug"] == "planetspark-1580118881"
    assert status("/internshala/companies/details", company="Zzzz Nonexistent Corp") == 404
    assert status("/internshala/companies/details", company="https://example.com/company/x-1") == 400


def test_company_openings():
    body = call("/internshala/companies/openings", company="PlanetSpark", type="jobs")
    assert body["count"] > 0 and body["jobs"] and all(j["company"]["name"] == "PlanetSpark" for j in body["jobs"])
    assert body["company"]["name"] == "PlanetSpark"
    body = call("/internshala/companies/openings", company="planetspark-1580118881")
    assert body["count"] == 0 and body["internships"] == []


def test_lookups():
    body = call("/internshala/categories")
    assert body["count"] > 100 and {"name": "Human Resources (HR)", "slug": "hr"} in body["categories"]
    assert call("/internshala/categories", type="jobs")["count"] > 100
    body = call("/internshala/locations", type="internships")
    assert body["count"] > 500 and {"name": "Delhi", "slug": "delhi"} in body["locations"]
    body = call("/internshala/autocomplete", query="pyth")
    assert body["suggestions"] == [{"name": "Python/Django Development", "slug": "python/django"}]
    body = call("/internshala/autocomplete", query="bang", type="location")
    assert body["suggestions"][0]["name"] == "Bangalore" and body["suggestions"][0]["slug"] == "bangalore"
    assert status("/internshala/autocomplete", query="py") == 400
