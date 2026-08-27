"""Registry of per-service DOM scrapers.

Each scraper module exports:
    NAME   -- exact service name as used in social_cluster.services
    SCRIPT -- JS source (a single expression / IIFE) that, when run via
              QWebEnginePage.runJavaScript(), returns a JSON string of the
              shape: {"items": [{"sender": str, "count": str|int, "preview": str}, ...]}
              or {"error": str} if extraction failed inside the page.
    STATUS -- "verified" (selectors confirmed against a live unread message
              during development) or "experimental" (best-effort selectors
              that have not yet been confirmed against live unread state and
              may need refinement).

This module is intentionally a thin, file-per-service registry: an install
script can later ask the user which services they want notification content
for, and only copy/enable the matching module(s) here (or fetch new ones),
without touching social_cluster/main.py.
"""

from . import whatsapp, discord, snapchat

_MODULES = [whatsapp, discord, snapchat]

SCRAPERS = {module.NAME: module.SCRIPT for module in _MODULES}
SCRAPER_STATUS = {module.NAME: getattr(module, "STATUS", "experimental") for module in _MODULES}

# Names of all scrapers bundled with the app. An installer can use this list
# to present choices to the user; services not selected simply won't be
# added to a config's "enabled_scrapers" list.
AVAILABLE_SCRAPERS = list(SCRAPERS.keys())
