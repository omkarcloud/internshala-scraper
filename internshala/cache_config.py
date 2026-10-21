"""Cache TTL per /internshala/* endpoint (cache.py, keyed on the validated
params — marshmallow fills the defaults, so an omitted param and its default
share a row).

Listings churn all day (new posts, "Just now" ages, applicant counts); one
listing changes rarely once posted but its applicant count ticks up, so
details are short-lived too; company profiles move daily at most; the
category / city vocabularies and autocomplete are stable."""
from datetime import timedelta

SEARCH_CACHE = timedelta(hours=1)          # internships/search, jobs/search, companies/openings
DETAILS_CACHE = timedelta(hours=6)         # internships/details, jobs/details
COMPANY_CACHE = timedelta(days=1)          # companies/details
CATEGORIES_CACHE = timedelta(days=7)       # categories, locations
AUTOCOMPLETE_CACHE = timedelta(days=7)     # autocomplete
COMPANY_LOOKUP_CACHE = timedelta(days=7)   # company name -> slug (fetch.shared_raw)
