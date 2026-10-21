"""/internshala/internships/details and /internshala/jobs/details — one
listing's page (fetch.page) parsed with its JobPosting JSON-LD."""
from internshala import fetch
from internshala import parsers as P


def _details(ref):
    kind, slug = ref["kind"], ref["slug"]
    markup = fetch.page(f"/{kind}/detail/{slug}", label=f"{kind} {slug}")
    result = P.details(markup, kind, slug)
    if result is None:
        raise fetch.InternshalaNotFound(f"Internshala has no {kind} page for '{slug}'")
    return result


def internship(internship):
    """The full internship: description, skills, who can apply, perks, stipend
    breakup, openings, applicants, employer profile and activity, similar
    listings. A job link given here is served as the job it is."""
    return _details(internship)


def job(job):
    """The full job: description, skills, who can apply, annual CTC and
    probation terms, experience, openings, applicants, employer profile and
    activity, similar listings. An internship link given here is served as
    the internship it is."""
    return _details(job)
