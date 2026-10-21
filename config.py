"""Configuration for the Internshala Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT               port the API listens on (default 8000)
    INTERNSHALA_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                       (default: none — direct). internshala.com's pages and
                       listing endpoints answer plain HTTP with no cookies, so
                       you very likely don't need this. Set it only if you
                       start seeing failures at high volume.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

INTERNSHALA_PROXY = os.environ.get("INTERNSHALA_PROXY") or None

# Names the internshala package reads.
INTERNSHALA_ALLOW_DIRECT = True             # no INTERNSHALA_PROXY set -> connect directly from this machine
INTERNSHALA_PROXY_COUNTRY = None            # unused here: INTERNSHALA_PROXY above is the whole proxy policy
INTERNSHALA_MAX_ATTEMPTS = MAX_RETRIES      # attempts per upstream call
INTERNSHALA_WORKERS = 3                     # parallel page fetches in /companies/details


def internshala_proxy(fallback=False):
    """The proxy for one Internshala request: INTERNSHALA_PROXY, or None for direct."""
    return os.environ.get("INTERNSHALA_PROXY") or None
