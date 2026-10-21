"""Marshmallow request schemas for every /internshala/* route.

Generic fields live in the shared top-level schema_fields.py; this module
adds the Internshala resolvers (refs.py). Every schema's load() output is
the kwargs dict its endpoint function takes.

ONE param per input (tripadvisor QueryOrLinkField convention, never a
sibling `url`/`id` pair): `internship` / `job` take a listing link or its
slug; `company` a company page link, its slug or a company name; `category`
and `location` one label or slug each (validated against the site's
vocabularies, see /internshala/categories and /internshala/locations; the
site's comma-joined multi-select narrows results instead of widening them,
so one value per call).
"""
from marshmallow import ValidationError, validate

from schema_fields import (BaseSchema, ChoiceField, DateField, Flag, PageField, PositiveInt, QueryField, RefField,
                           StrippedString)
from internshala import refdata, refs


def _max_length(n):
    def check(value):
        if value is not None and len(value) > n:
            raise ValidationError(f"Longer than maximum length {n}.")
    return check


class InternshipField(RefField):
    resolver = staticmethod(refs.resolve_internship)


class JobField(RefField):
    resolver = staticmethod(refs.resolve_job)


class CompanyField(RefField):
    resolver = staticmethod(refs.resolve_company)


class CategoryField(RefField):
    """A category label or slug ('Web Development' / 'web-development' / 'hr') -> the listing slug."""
    resolver = staticmethod(refs.resolve_category)

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class LocationField(RefField):
    """A city label or slug ('New Delhi' / 'new-delhi') -> the listing slug."""
    resolver = staticmethod(refs.resolve_location)

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class _Listing(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=_max_length(100))
    category = CategoryField()
    location = LocationField()
    work_from_home = Flag()
    part_time = Flag()
    for_women = Flag()
    page = PageField(max_page=refdata.MAX_PAGE)


class InternshipSearchSchema(_Listing):
    min_stipend = PositiveInt(max_value=10_000_000)
    duration = PositiveInt(max_value=36)
    start_date = DateField()
    with_job_offer = Flag()
    fast_response = Flag()
    early_applicant = Flag()
    international = Flag()
    big_brand = Flag()


class JobSearchSchema(_Listing):
    min_salary = PositiveInt(max_value=1_000_000_000)
    experience = ChoiceField(list(refdata.EXPERIENCE_VALUES))


class InternshipSchema(BaseSchema):
    internship = InternshipField()


class JobSchema(BaseSchema):
    job = JobField()


class CompanySchema(BaseSchema):
    company = CompanyField()


class CompanyOpeningsSchema(CompanySchema):
    type = ChoiceField(["internships", "jobs"], load_default="internships")
    page = PageField(max_page=refdata.MAX_PAGE)


class BoardSchema(BaseSchema):
    type = ChoiceField(["internships", "jobs"], load_default="internships")


class AutocompleteSchema(BaseSchema):
    query = QueryField(max_length=100, validate=validate.Length(min=3, max=100))
    type = ChoiceField(["category", "location"], load_default="category")
