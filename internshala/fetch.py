"""Internshala transport: plain curl_cffi, no browser, validated 2026-10-19
from a direct India egress with no cookies.

Surfaces (all on https://internshala.com, server-rendered, no anti-bot —
robots.txt disallows crawlers, nothing enforces it; the only gate seen is a
reCAPTCHA on the login/apply flows, which this scraper never touches):

  listing(board, segments, page)   GET /<board>_ajax/<filters>/page-N/ with
                                   X-Requested-With: XMLHttpRequest — the JSON
                                   the site's own result pages load: card HTML
                                   (40-60 per page), the total in seo.heading,
                                   next_page_number / is_last_page, the SEO
                                   company name for company-scoped listings.
                                   Boards: internships_ajax, jobs_ajax,
                                   fresher-jobs_ajax, internships-for-women_ajax,
                                   jobs-for-women_ajax. Filters are PATH
                                   segments (internshala/listings.py builds
                                   them); the page is the last one.
  page(path)                       GET an HTML page: /internship/detail/<slug>,
                                   /job/detail/<slug>, /company/<slug>[/careers/
                                   | /salaries-perks/]. A missing slug is a
                                   plain 404.
  criteria(kind)                   GET /internship/get_search_criterias_newui/ or
                                   /job/get_search_criterias/ — the category and
                                   city vocabularies (JSON).
  autocomplete(kind, query)        POST /autocomplete/category_filters or
                                   /autocomplete/location_filters (s=<3+ chars>).

Egress: every call rides a proxy exit (config.internshala_proxy(): a sticky
residential exit in INTERNSHALA_PROXY_COUNTRY); a failed call is retried on a
fresh exit. Internshala is never contacted from the server's own
IP: with no proxy configured the call fails, unless the config opts in with
INTERNSHALA_ALLOW_DIRECT = True (the open-source kit does, for a user's own
machine; the scrapers service never does). If exits start getting blocked, a
headful patchright click-through (indeed/fetch.py _browser_page) is the
escalation — not built while plain HTTP works.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  InternshalaUpstreamError  transport failure / 5xx / unexpected body — retryable
  InternshalaBlocked        403 / 429 / challenge page / non-JSON listing — retryable on a new exit
  InternshalaBadRequest     the site rejected the params                — never retried
  InternshalaNotFound       no such listing / company                   — never retried
"""
import json
import os
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from internshala import refdata

BASE = refdata.BASE_LINK
IMPERSONATE = "chrome"
TIMEOUT = (10, 40)            # (connect, read)

HTML_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
}
AJAX_HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "en-US,en;q=0.9",
    "x-requested-with": "XMLHttpRequest",
    "referer": BASE + "/internships/",
}
BLOCK_MARKERS = ("just a moment", "cf-chl", "challenge-platform", "attention required", "access denied",
                 "ddos protection", "captcha-delivery")


class InternshalaUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected body — retryable."""


class InternshalaBlocked(InternshalaUpstreamError, Blocked):
    """403 / 429 / a challenge page — retryable on a fresh exit."""


class InternshalaBadRequest(BadRequest):
    """The site rejected the params — never retried."""


class InternshalaNotFound(NotFound):
    """No such listing / company page — never retried."""


def dump_debug(name, text):
    """Write a raw response to $INTERNSHALA_DEBUG_DIR/<name>.txt for post-mortems."""
    dbg = os.environ.get("INTERNSHALA_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".txt"), "w") as f:
                f.write(text)
        except OSError:
            pass


# ---- curl sessions (per thread, keyed by exit) ---------------------------------------------------

_local = threading.local()


def _sessions():
    store = getattr(_local, "sessions", None)
    if store is None:
        store = _local.sessions = OrderedDict()
    return store


def _session(key, proxy):
    from curl_cffi import requests as curl_requests
    store = _sessions()
    sess = store.get(key)
    if sess is None:
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        store[key] = sess
        while len(store) > 4:
            _, old = store.popitem(last=False)
            try:
                old.close()
            except Exception:
                pass
    else:
        store.move_to_end(key)
    return sess


def _drop_session(key):
    sess = _sessions().pop(key, None)
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _proxy(fallback=False):
    """The exit for a session; refuses to go on without one (Internshala never
    sees the server's own IP) unless the config opts in to direct egress."""
    proxy = config.internshala_proxy(fallback=fallback)
    if not proxy and not getattr(config, "INTERNSHALA_ALLOW_DIRECT", False):
        raise InternshalaUpstreamError("no Internshala proxy configured (Internshala is never contacted "
                                       "from the server's IP)")
    return proxy


def _attempts(label, send):
    """Run send(session) under the retry policy: InternshalaUpstreamError
    (incl. Blocked) retries on a fresh exit up to config.INTERNSHALA_MAX_ATTEMPTS
    times; BadRequest / NotFound surface at once."""
    attempts = max(1, int(config.INTERNSHALA_MAX_ATTEMPTS))
    last = None
    for attempt in range(1, attempts + 1):
        proxy = _proxy(attempt > 1)
        key = f"{attempt if proxy else 0}:{proxy or 'direct'}"
        sess = _session(key, proxy)
        try:
            return send(sess)
        except (InternshalaBadRequest, InternshalaNotFound):
            raise
        except InternshalaUpstreamError as e:
            last = e
        except Exception as e:
            last = InternshalaUpstreamError(f"request failed on {label}: {type(e).__name__}: {e}")
        _drop_session(key)
        print(f"internshala: attempt {attempt}/{attempts} on {label} failed: {last}")
        if attempt < attempts:
            time.sleep(0.5 * attempt)
    raise last


def is_blocked(status, text):
    head = (text or "")[:4000].lower()
    return status in (403, 429, 503) or any(m in head for m in BLOCK_MARKERS)


def _classify(resp, label, json_body):
    """Raise the failure a response represents, else return its JSON (or text)."""
    status = resp.status_code
    text = resp.text or ""
    if is_blocked(status, text):
        dump_debug("blocked", text)
        raise InternshalaBlocked(f"HTTP {status} on {label}")
    if status in (404, 410):
        raise InternshalaNotFound(f"Internshala has no page for {label}")
    if status == 400:
        raise InternshalaBadRequest(f"Internshala rejected the request on {label}: {text[:200]}")
    if status >= 500:
        raise InternshalaUpstreamError(f"HTTP {status} on {label}")
    if status != 200:
        raise InternshalaUpstreamError(f"HTTP {status} on {label}")
    if not json_body:
        return text
    try:
        return json.loads(text)
    except ValueError:
        dump_debug("non_json", text)
        raise InternshalaBlocked(f"non-JSON answer on {label} (a login or challenge page?)")


# ---- listings -------------------------------------------------------------------------------------------

def listing_path(board, segments, page=1):
    """('internships', ['marketing-internship-in-delhi', 'stipend-5000'], 2)
    -> '/internships_ajax/marketing-internship-in-delhi/stipend-5000/page-2/'."""
    prefix = refdata.BOARDS[board]
    parts = [s.strip("/") for s in (segments or []) if s]
    parts.append(f"page-{int(page or 1)}")
    return f"/{prefix}/" + "/".join(parts) + "/"


def listing(board, segments, page=1, label=None):
    """GET one listing page -> the site's JSON ({internship_list_html, seo,
    next_page_number, is_last_page, currentPageCount, ...})."""
    path = listing_path(board, segments, page)
    label = label or f"{board} listing {path}"
    url = BASE + path

    def send(sess):
        resp = sess.get(url, headers=AJAX_HEADERS, timeout=TIMEOUT, allow_redirects=True)
        body = _classify(resp, label, json_body=True)
        if not isinstance(body, dict) or "internship_list_html" not in body:
            dump_debug("listing_unexpected", resp.text)
            raise InternshalaUpstreamError(f"unexpected listing payload on {label}")
        return body
    return _attempts(label, send)


# ---- HTML pages -----------------------------------------------------------------------------------------

def page(path, label=None):
    """GET an HTML page (detail / company) -> its text. 404 -> InternshalaNotFound."""
    url = path if path.startswith("http") else BASE + "/" + path.lstrip("/")
    label = label or path

    def send(sess):
        resp = sess.get(url, headers=HTML_HEADERS, timeout=TIMEOUT, allow_redirects=True)
        text = _classify(resp, label, json_body=False)
        if "<html" not in text[:2000].lower():
            dump_debug("page_unexpected", text)
            raise InternshalaUpstreamError(f"unexpected (non-HTML) answer on {label}")
        return text
    return _attempts(label, send)


# ---- vocabularies ---------------------------------------------------------------------------------------

CRITERIA_PATHS = {"internships": "/internship/get_search_criterias_newui/", "jobs": "/job/get_search_criterias/"}
AUTOCOMPLETE_PATHS = {"category": "/autocomplete/category_filters", "location": "/autocomplete/location_filters"}


def criteria(kind="internships"):
    """GET the board's filter vocabulary -> {category_count, location_count,
    categoryArray: [{name, label}], cityArray: [...], categoryView, cityView}."""
    path = CRITERIA_PATHS[kind]
    label = f"{kind} criteria"

    def send(sess):
        resp = sess.get(BASE + path, headers=AJAX_HEADERS, timeout=TIMEOUT)
        body = _classify(resp, label, json_body=True)
        if not isinstance(body, dict) or "categoryArray" not in body:
            raise InternshalaUpstreamError(f"unexpected criteria payload on {label}")
        return body
    return _attempts(label, send)


def autocomplete(kind, query, args=None):
    """POST the search box's suggestion call -> ['Python/Django', ...]."""
    path = AUTOCOMPLETE_PATHS[kind]
    label = f"{kind} autocomplete {query!r}"
    # an (empty) args[] is mandatory: without it the city box answers fuzzy
    # junk ("bang" -> Bani, Pang) or nothing, and the category box answers
    # short labels outside its own vocabulary ("Python/Django" instead of
    # "Python/Django Development")
    pairs = [("s", query)] + [("args[]", arg) for arg in (args or [""])]
    form = urlencode(pairs)
    headers = dict(AJAX_HEADERS, **{"content-type": "application/x-www-form-urlencoded; charset=UTF-8"})

    def send(sess):
        resp = sess.post(BASE + path, data=form, headers=headers, timeout=TIMEOUT)
        body = _classify(resp, label, json_body=True)
        if not isinstance(body, dict):
            raise InternshalaUpstreamError(f"unexpected autocomplete payload on {label}")
        return body
    return _attempts(label, send)


# ---- memo / cache / parallel ---------------------------------------------------------------------------

_memo = OrderedDict()
_memo_lock = threading.Lock()
MEMO_TTL = 600
MEMO_MAX = 256


def memoized(key, fn, ttl=MEMO_TTL):
    now = time.monotonic()
    with _memo_lock:
        hit = _memo.get(key)
        if hit and now - hit[0] < ttl:
            _memo.move_to_end(key)
            return hit[1]
    value = fn()
    with _memo_lock:
        _memo[key] = (now, value)
        _memo.move_to_end(key)
        while len(_memo) > MEMO_MAX:
            _memo.popitem(last=False)
    return value


def shared_raw(name, params, build, ttl):
    """An upstream value shared by several routes: in-process memo, then the
    service's response cache (pods share it) when one is installed, then
    build()."""
    try:
        from cache import cached_call
    except ImportError:
        cached_call = None
    seconds = ttl.total_seconds() if hasattr(ttl, "total_seconds") else ttl
    key = (name, json.dumps(params, sort_keys=True))
    if cached_call is None:
        return memoized(key, build, ttl=min(seconds, MEMO_TTL))
    return memoized(key, lambda: cached_call(f"internshala.raw.{name}", params, lambda **_: build(), ttl),
                    ttl=min(seconds, MEMO_TTL))


def run_parallel(fns, workers):
    """Run zero-arg callables in parallel; results align with `fns`. Each
    result is ("ok", value) or ("error", exception)."""
    def guard(fn):
        try:
            return ("ok", fn())
        except Exception as e:
            return ("error", e)
    if not fns:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(fns)))) as ex:
        return list(ex.map(guard, fns))


if __name__ == "__main__":
    # Smoke test: python internshala/fetch.py
    body = listing("internships", ["marketing-internship-in-delhi", "stipend-5000"], 1)
    print("listing:", body["seo"]["heading"], body.get("currentPageCount"), "cards; next", body.get("next_page_number"))
    import re
    slug = re.search(r"/internship/detail/([^'\"]+)", body["internship_list_html"]).group(1)
    html = page(f"/internship/detail/{slug}")
    print("detail:", len(html), "bytes", re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()[:80])
    print("criteria:", criteria("internships")["category_count"], "categories")
    print("autocomplete:", autocomplete("category", "pyth"))
