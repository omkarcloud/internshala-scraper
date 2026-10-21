"""/internshala/internships/search and /internshala/jobs/search — the two
listing boards (plus the fresher-jobs and for-women boards they branch to)
from the site's own listing JSON (fetch.listing).

The site takes its filters as PATH segments, in a fixed grammar (a wrong
order 301s to the canonical one, which the JSON endpoint does not follow):

  internships  [keywords-<kw>/] [work-from-home-]<category>-internship[s][-in-<city>]
               [/international-internship] [/part-time-true] [/duration-N] [/start-date-YYYYMMDD]
               [/ppo-true] [/stipend-N] [/fast-response-true] [/early-applicant-25] [/big-brand] /page-N/
               (plural "internships" with work-from-home; "internship" otherwise; ONE category
               and ONE city — the site's comma-joined multi-select narrows instead of widening)
  jobs         [keywords-<kw>/] [part-time-][work-from-home-]<category>-jobs[-in-<city>]
               [/salary-N] [/experience-N|5plus] /page-N/      (fresher -> the fresher-jobs board)
  company      internship-at-<company>  |  job-at-<company>     (the company's name slug)
"""
from internshala import fetch, refdata, refs
from internshala import parsers as P
from internshala import shared as S


def _base(prefixes, cat, noun, city):
    cat = cat or ""
    city = city or ""
    base = "".join(prefixes) + (f"{cat}-" if cat else "") + noun + (f"-in-{city}" if city else "")
    return None if base == noun else base


def internship_segments(query=None, category=None, location=None, work_from_home=None, part_time=None,
                        min_stipend=None, duration=None, start_date=None, with_job_offer=None,
                        fast_response=None, early_applicant=None, international=None, big_brand=None):
    segments = []
    if query:
        segments.append("keywords-" + S.path_segment(query))
    noun = "internships" if work_from_home else "internship"
    base = _base(["work-from-home-"] if work_from_home else [], category, noun, location)
    if base:
        segments.append(S.path_segment(base))
    elif work_from_home:
        segments.append("work-from-home-internships")
    if international:
        segments.append("international-internship")
    if part_time:
        segments.append("part-time-true")
    if duration:
        segments.append(f"duration-{int(duration)}")
    if start_date:
        segments.append("start-date-" + str(start_date).replace("-", ""))
    if with_job_offer:
        segments.append("ppo-true")
    if min_stipend:
        segments.append(f"stipend-{int(min_stipend)}")
    if fast_response:
        segments.append("fast-response-true")
    if early_applicant:
        segments.append("early-applicant-25")
    if big_brand:
        segments.append("big-brand")
    return segments


def job_segments(query=None, category=None, location=None, work_from_home=None, part_time=None,
                 min_salary=None, experience=None):
    segments = []
    if query:
        segments.append("keywords-" + S.path_segment(query))
    prefixes = (["part-time-"] if part_time else []) + (["work-from-home-"] if work_from_home else [])
    base = _base(prefixes, category, "jobs", location)
    if base:
        segments.append(S.path_segment(base))
    if min_salary:
        segments.append(f"salary-{int(min_salary)}")
    if experience and experience != "fresher":
        segments.append(f"experience-{experience}")
    return segments


def _filters(**kwargs):
    """Echo of the filters that were applied (None / False / empty dropped)."""
    return {k: v for k, v in kwargs.items() if v not in (None, False, "", [])}


def internships(query=None, category=None, location=None, work_from_home=None, part_time=None, min_stipend=None,
                duration=None, start_date=None, with_job_offer=None, fast_response=None, early_applicant=None,
                international=None, big_brand=None, for_women=None, page=1):
    """One page of internship cards for the given filters."""
    segments = internship_segments(query, category, location, work_from_home, part_time, min_stipend, duration,
                                   start_date, with_job_offer, fast_response, early_applicant, international,
                                   big_brand)
    board = "internships_for_women" if for_women else "internships"
    raw = fetch.listing(board, segments, page, label=f"internships {'/'.join(segments) or 'all'} p{page}")
    result = P.listing_result(raw, page, "internship")
    result["internships"] = result.pop("listings")
    result["filters"] = _filters(query=query, category=refs.category_label(category) or category,
                                 location=refs.city_label(location) or location,
                                 work_from_home=work_from_home, part_time=part_time, min_stipend=min_stipend,
                                 duration_months=duration, start_date=start_date, with_job_offer=with_job_offer,
                                 fast_response=fast_response, early_applicant=early_applicant,
                                 international=international, big_brand=big_brand, for_women=for_women)
    return result


def jobs(query=None, category=None, location=None, work_from_home=None, part_time=None, min_salary=None,
         experience=None, for_women=None, page=1):
    """One page of job cards for the given filters (`experience` = fresher
    switches to the fresher-jobs board)."""
    segments = job_segments(query, category, location, work_from_home, part_time, min_salary, experience)
    if for_women:
        board = "jobs_for_women"
        if experience == "fresher":
            segments.append("job_type-fresher_job")
    elif experience == "fresher":
        board = "fresher_jobs"
    else:
        board = "jobs"
    raw = fetch.listing(board, segments, page, label=f"jobs {'/'.join(segments) or 'all'} p{page}")
    result = P.listing_result(raw, page, "job")
    result["jobs"] = result.pop("listings")
    result["filters"] = _filters(query=query, category=refs.category_label(category) or category,
                                 location=refs.city_label(location) or location,
                                 work_from_home=work_from_home, part_time=part_time, min_salary=min_salary,
                                 experience=experience, for_women=for_women)
    return result


def company_name_slug(company):
    """A resolved company ref -> the name slug the listing filter takes
    ('planetspark-1580118881' -> 'planetspark'; a name -> its arg slug)."""
    import re
    slug = company.get("slug") if isinstance(company, dict) else None
    if slug:
        return re.sub(r"-\d+$", "", slug)
    return S.arg_slug(company.get("name") if isinstance(company, dict) else company)


def company_listings(name_slug, kind="internships", page=1):
    """The company's open internships or jobs (the site's company-scoped
    listing). Raises InternshalaNotFound when the site knows no such
    company (it then answers the unfiltered board, flagged by an empty
    seo.company_name)."""
    board = "jobs" if kind == "jobs" else "internships"
    segment = f"job-at-{name_slug}" if kind == "jobs" else f"internship-at-{name_slug}"
    raw = fetch.listing(board, [S.path_segment(segment)], page, label=f"{kind} at {name_slug} p{page}")
    result = P.listing_result(raw, page, "job" if kind == "jobs" else "internship")
    company = result.get("company")
    if not company:
        raise fetch.InternshalaNotFound(f"Internshala lists no {kind} for the company '{name_slug}'")
    # a company with nothing open on this board gets the site's "similar" fill
    # (other employers' cards under the company's heading): keep its own only
    own = [c for c in result["listings"] if ((c.get("company") or {}).get("name") or "").strip().lower() == company.strip().lower()]
    if len(own) != len(result["listings"]):
        result["listings"] = own
        result["pagination"].update(total_count=len(own) if page == 1 else result["pagination"]["total_count"],
                                    total_pages=page, is_last_page=True, items_per_page=len(own) or refdata.ITEMS_PER_PAGE)
    return result
