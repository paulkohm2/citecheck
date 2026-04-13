"""
core.py — CourtListener API logic, shared by all UI versions.

Returns plain Python dicts and lists. No UI code here.

Terminology:
  "forward citations" = later cases that cite the target case
  (measures the case's influence over time)
"""

import os
import re
import requests
from collections import Counter

BASE = "https://www.courtlistener.com/api/rest/v4"
MAX_RESULTS = 300

# Matches common reporter citation formats: "410 U.S. 113", "93 S. Ct. 705", etc.
_CITATION_RE = re.compile(
    r"\d+\s+(U\.?S\.?|S\.?\s?Ct\.?|F\.?\d[a-z]*|F\.?Supp|L\.?Ed|A\.?L\.?R)",
    re.IGNORECASE,
)


def _headers():
    key = os.environ.get("COURTLISTENER_API_KEY", "")
    return {"Authorization": f"Token {key}"} if key else {}


def _normalize_citation(raw):
    """Normalize reporter abbreviations to the dotted canonical form CourtListener stores."""
    raw = re.sub(r'\bU\.?S\.?\b',     'U.S.',     raw, flags=re.IGNORECASE)
    raw = re.sub(r'\bS\.?\s?Ct\.?\b', 'S. Ct.',   raw, flags=re.IGNORECASE)
    raw = re.sub(r'\bF\.?Supp\.?\b',  'F. Supp.', raw, flags=re.IGNORECASE)
    raw = re.sub(r'\bL\.?Ed\.?\b',    'L. Ed.',   raw, flags=re.IGNORECASE)
    raw = re.sub(r'\bA\.?L\.?R\.?\b', 'A.L.R.',   raw, flags=re.IGNORECASE)
    return raw


def _search_query(raw):
    """
    If the input looks like a reporter citation, normalize it and wrap it so
    the search engine treats it as a citation field lookup rather than a text query.
    """
    if _CITATION_RE.search(raw):
        return f'citation:("{_normalize_citation(raw)}")'
    return raw


_PREFERRED_OPINION_TYPES = ("combined-opinion", "010combined", "lead-opinion", "020lead")


def _best_opinion_id(opinions):
    """
    A cluster contains multiple opinions (majority, concurrence, dissent, combined).
    Return the ID of whichever type is most likely to be what other cases cite.
    """
    by_type = {op.get("type"): op["id"] for op in opinions}
    for t in _PREFERRED_OPINION_TYPES:
        if t in by_type:
            return by_type[t]
    return opinions[0]["id"] if opinions else None


def find_case(query):
    """
    Search for a case by name or citation string.
    Returns a dict with cluster_id, opinion_id, and metadata — or None.

    The opinion_id is the ID used by CourtListener's citation network.
    It differs from cluster_id for most cases and is required for cites:()
    queries. It is embedded in the search result's 'opinions' list so no
    extra API call is needed.
    """
    r = requests.get(
        f"{BASE}/search/",
        params={"q": _search_query(query), "type": "o"},
        headers=_headers(),
        timeout=10,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        return None
    hit = results[0]
    cluster_id = hit["cluster_id"]

    # Pick the best opinion ID from the embedded opinions list.
    # Clusters contain multiple opinions (majority, concurrence, dissent, combined).
    # The combined-opinion or lead-opinion is what other cases actually cite.
    opinions = hit.get("opinions", [])
    opinion_id = _best_opinion_id(opinions) or cluster_id

    return {
        "cluster_id": cluster_id,
        "opinion_id": opinion_id,
        "case_name": hit.get("caseName", "Unknown"),
        "court": hit.get("court", ""),
        "date_filed": hit.get("dateFiled", ""),
        "citations": hit.get("citation", []),
    }


def fetch_forward_citations(opinion_id, max_results=MAX_RESULTS, progress_cb=None):
    """
    Fetch cases that cite the given opinion (forward citations).

    Returns (total_count, list_of_case_dicts), where total_count is the
    full count reported by the API and the list is capped at max_results.

    progress_cb(fetched, total) is called after each page if provided.
    """
    results = []

    r = requests.get(
        f"{BASE}/search/",
        params={
            "q": f"cites:({opinion_id})",
            "type": "o",
            "order_by": "dateFiled desc",
        },
        headers=_headers(),
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    total = data.get("count", 0)
    results.extend(data.get("results", []))

    if progress_cb:
        progress_cb(len(results), total)

    next_url = data.get("next")
    while next_url and len(results) < max_results:
        r = requests.get(next_url, headers=_headers(), timeout=15)
        r.raise_for_status()
        data = r.json()
        results.extend(data.get("results", []))
        if progress_cb:
            progress_cb(len(results), total)
        next_url = data.get("next")

    cases = []
    for c in results[:max_results]:
        cases.append({
            "case_name": c.get("caseName", "Unknown"),
            "date_filed": c.get("dateFiled", ""),
            "court": c.get("court", ""),
            "cite_count": c.get("citeCount", 0),
            "url": "https://www.courtlistener.com" + c.get("absolute_url", ""),
            "snippet": c.get("snippet", ""),
        })

    return total, cases


def citations_by_year(cases):
    """
    Given a list of case dicts, return a sorted dict of {year: count}.
    """
    years = []
    for c in cases:
        d = c.get("date_filed", "")
        if d and len(d) >= 4:
            try:
                years.append(int(d[:4]))
            except ValueError:
                pass
    return dict(sorted(Counter(years).items()))
