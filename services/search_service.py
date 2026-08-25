"""
Search service: resolves a student's query to real, verified source
material and returns it categorized (web pages, PDFs, videos).

Default provider ("auto", no API key needed) tries several strategies in
order to resolve ANY query — a topic, a question, a gaming term, slang —
to a real Wikipedia article:
  1. Wikipedia full-text search on the query as typed (matches content,
     not just titles — so "Python inheritance" finds the article on
     inheritance even though no article is titled exactly that).
  2. The same search after stripping question phrasing ("what is",
     "how does", "why is", trailing "?", etc.).
  3. A search on the core keyword phrase extracted from the query (e.g.
     "K in Free Fire" -> "Free Fire"), for terms too specific/slangy to
     have their own article but that belong to something that does.
If nothing resolves, search() still succeeds — it returns real, always-
reachable "search launcher" links (Google, YouTube) instead of an error,
so a genuinely unfamiliar query is never simply rejected. AIService
decides what to say about the result; this module's only job is to never
hand back a fake or unverified URL.

Configure a real SEARCH_API_KEY (Brave/Serper/Tavily/Bing) for broader
open-web coverage; those paths go through the same URL verification.
"""
import re
import requests
from urllib.parse import quote, quote_plus, urlparse

from config.config import Config

BLOCKED_DOMAIN_FRAGMENTS = [
    "example.com", "example.org", "example.edu", "example.net",
    "example-university.edu", "example-edu.org", "example-video.org",
    "test.com", "placeholder.com", "yoursite.com",
]

# Large, stable platforms that reliably reject bot-style HEAD/GET checks
# (403s, CAPTCHAs) even though the URL works fine for a real person in a
# browser. Skip live verification for these specific launcher URLs only —
# every other resource still gets verified.
_TRUSTED_LAUNCHER_DOMAINS = ("google.com", "youtube.com")

USER_AGENT = "StudentHub/1.0 (educational study-notes project; contact: none)"

_QUESTION_PREFIXES = [
    r"^what\s+is\s+", r"^what\s+are\s+", r"^what's\s+", r"^whats\s+",
    r"^who\s+is\s+", r"^who\s+was\s+", r"^who\s+are\s+",
    r"^how\s+does\s+", r"^how\s+do\s+", r"^how\s+to\s+", r"^how\s+is\s+",
    r"^why\s+is\s+", r"^why\s+does\s+", r"^why\s+do\s+", r"^why\s+are\s+",
    r"^best\s+way\s+to\s+", r"^define\s+", r"^explain\s+", r"^tell\s+me\s+about\s+",
]


class SearchService:
    def __init__(self):
        self.provider = (Config.SEARCH_API_PROVIDER or "auto").lower()
        self.api_key = Config.SEARCH_API_KEY

    def search(self, query: str, max_results: int = 8) -> dict:
        """
        Returns:
        {
            "query": str, "web": [...], "pdfs": [...], "videos": [...],
            "provider": str, "error": str | None,
            "extract": str,        # real source text, "" if nothing matched
            "page_title": str,     # matched title, None if nothing matched
            "match_quality": "exact" | "related" | "none",
        }
        Every URL returned has been verified reachable (or is a trusted
        search-launcher link — see _TRUSTED_LAUNCHER_DOMAINS above).
        This method essentially always succeeds; "error" is reserved for
        genuine failures (empty query, network outage), not "no match".
        """
        query = (query or "").strip()
        if not query:
            return self._empty_result(query, "Empty query.")

        try:
            if self.provider in ("auto", "mock") or not self.api_key:
                return self._wikipedia_search(query, max_results)
            elif self.provider == "brave":
                return self._brave_search(query, max_results)
            elif self.provider == "serper":
                return self._serper_search(query, max_results)
            elif self.provider == "tavily":
                return self._tavily_search(query, max_results)
            elif self.provider == "bing":
                return self._bing_search(query, max_results)
            else:
                return self._wikipedia_search(query, max_results)
        except requests.RequestException:
            return self._empty_result(
                query, "We couldn't retrieve study resources right now. Please try again."
            )

    def _empty_result(self, query, error, provider=None):
        return {"query": query, "web": [], "pdfs": [], "videos": [],
                "provider": provider or self.provider, "error": error,
                "extract": "", "page_title": None, "match_quality": "none"}

    # ------------------------------------------------------------------
    # Query normalization
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_query(query: str) -> str:
        q = query.strip()
        q = re.sub(r"\?+$", "", q).strip()
        for pattern in _QUESTION_PREFIXES:
            new_q = re.sub(pattern, "", q, flags=re.IGNORECASE)
            if new_q != q and new_q.strip():
                return new_q.strip()
        return q

    @staticmethod
    def _core_keywords(query: str) -> str:
        """Best-effort extraction of the 'thing' a query is really about,
        e.g. 'K in Free Fire' -> 'Free Fire', 'sensitivity in Free Fire'
        -> 'Free Fire'. Falls back to the query unchanged."""
        m = re.search(r"\b(?:in|for|of|on)\s+(.+)$", query, flags=re.IGNORECASE)
        if m and len(m.group(1).strip()) >= 3:
            return m.group(1).strip()
        return query

    # ------------------------------------------------------------------
    # URL verification
    # ------------------------------------------------------------------
    def _is_verified(self, url: str, timeout: float = 6.0) -> bool:
        if not url:
            return False
        domain = urlparse(url).netloc.lower()
        if not domain or any(frag in domain for frag in BLOCKED_DOMAIN_FRAGMENTS):
            return False
        if any(trusted in domain for trusted in _TRUSTED_LAUNCHER_DOMAINS):
            return True
        headers = {"User-Agent": USER_AGENT}
        try:
            resp = requests.head(url, timeout=timeout, allow_redirects=True, headers=headers)
            if resp.status_code < 400:
                return True
            if resp.status_code in (403, 405, 501):
                resp = requests.get(url, timeout=timeout, stream=True, headers=headers)
                return resp.status_code < 400
            return False
        except requests.RequestException:
            return False

    # ------------------------------------------------------------------
    # DEFAULT PROVIDER — Wikipedia, resolved via multiple strategies
    # ------------------------------------------------------------------
    def _wikipedia_fulltext_search(self, text: str):
        """Content-based search (not just title prefix matching) — this is
        what lets 'Python inheritance' or a full question resolve to the
        right article even when no title matches literally."""
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": text,
                    "srlimit": 1, "format": "json"},
            headers={"User-Agent": USER_AGENT},
            timeout=8,
        )
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        return results[0]["title"] if results else None

    def _wikipedia_summary(self, title: str):
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"
        resp = requests.get(url, timeout=8, headers={"User-Agent": USER_AGENT})
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("type") == "disambiguation":
            return None
        return data

    def _resolve_wikipedia_title(self, query: str):
        """Try, in order: full-text search on the query as typed (exact),
        full-text search on the cleaned/de-questioned query (exact), then
        a search on the core keyword phrase (related, not exact)."""
        title = self._wikipedia_fulltext_search(query)
        if title:
            return title, "exact"

        cleaned = self._clean_query(query)
        if cleaned.lower() != query.lower():
            title = self._wikipedia_fulltext_search(cleaned)
            if title:
                return title, "exact"

        core = self._core_keywords(cleaned)
        if core.lower() not in (query.lower(), cleaned.lower()):
            title = self._wikipedia_fulltext_search(core)
            if title:
                return title, "related"

        return None, "none"

    def _launcher_links(self, query: str) -> dict:
        """Real, always-reachable entry points for further reading — used
        both as a supplement to a Wikipedia match and as the fallback when
        nothing resolves, so a query is never met with a dead end."""
        web, videos = [], []
        google_url = f"https://www.google.com/search?q={quote_plus(query)}"
        if self._is_verified(google_url):
            web.append({
                "title": f'Search the web for "{query}"',
                "url": google_url,
                "snippet": "Browse current web results for this exact query.",
                "source": "Google search",
            })
        yt_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        if self._is_verified(yt_url):
            videos.append({
                "title": f'Videos about "{query}" on YouTube',
                "url": yt_url,
                "snippet": f"Browse videos covering {query}.",
                "source": "YouTube search",
            })
        return {"web": web, "videos": videos}

    def _wikipedia_search(self, query: str, max_results: int) -> dict:
        title, match_quality = self._resolve_wikipedia_title(query)
        launchers = self._launcher_links(query)

        if not title:
            return {
                "query": query, "web": launchers["web"], "pdfs": [],
                "videos": launchers["videos"], "provider": "wikipedia", "error": None,
                "extract": "", "page_title": None, "match_quality": "none",
            }

        summary = self._wikipedia_summary(title)
        if not summary:
            return {
                "query": query, "web": launchers["web"], "pdfs": [],
                "videos": launchers["videos"], "provider": "wikipedia", "error": None,
                "extract": "", "page_title": None, "match_quality": "none",
            }

        page_url = summary.get("content_urls", {}).get("desktop", {}).get("page", "")
        extract = summary.get("extract", "") or ""
        display_title = summary.get("title", query)

        if not self._is_verified(page_url):
            return {
                "query": query, "web": launchers["web"], "pdfs": [],
                "videos": launchers["videos"], "provider": "wikipedia", "error": None,
                "extract": "", "page_title": None, "match_quality": "none",
            }

        web = [{
            "title": display_title,
            "url": page_url,
            "snippet": extract[:320],
            "source": "Wikipedia",
        }] + launchers["web"]

        pdfs = []
        pdf_url = f"https://en.wikipedia.org/api/rest_v1/page/pdf/{quote(title.replace(' ', '_'))}"
        if self._is_verified(pdf_url):
            pdfs.append({
                "title": f"{display_title} — Full Article (PDF export)",
                "url": pdf_url,
                "snippet": f"The complete Wikipedia article on {display_title}, exported as a PDF for offline reading.",
                "source": "Wikipedia PDF export",
            })

        videos = launchers["videos"]

        return {
            "query": query, "web": web, "pdfs": pdfs, "videos": videos,
            "provider": "wikipedia", "error": None,
            "extract": extract, "page_title": display_title, "match_quality": match_quality,
        }

    # ------------------------------------------------------------------
    # REAL PROVIDERS — each needs SEARCH_API_KEY + matching
    # SEARCH_API_PROVIDER. Every result is verified before being returned.
    # ------------------------------------------------------------------
    def _brave_search(self, query: str, max_results: int) -> dict:
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": self.api_key},
            params={"q": query, "count": max_results},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        candidates = [
            {"title": r.get("title", ""), "url": r.get("url", ""),
             "snippet": r.get("description", ""), "source": r.get("meta_url", {}).get("hostname", "")}
            for r in data.get("web", {}).get("results", [])[:max_results]
        ]
        web = [c for c in candidates if self._is_verified(c["url"])]
        launchers = self._launcher_links(query)
        web = web or launchers["web"]
        return {"query": query, "web": web, "pdfs": [], "videos": launchers["videos"],
                "provider": "brave", "error": None, "extract": "", "page_title": None,
                "match_quality": "exact" if web else "none"}

    def _serper_search(self, query: str, max_results: int) -> dict:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        candidates = [
            {"title": r.get("title", ""), "url": r.get("link", ""),
             "snippet": r.get("snippet", ""), "source": r.get("link", "").split("/")[2] if r.get("link") else ""}
            for r in data.get("organic", [])[:max_results]
        ]
        web = [c for c in candidates if self._is_verified(c["url"])]
        launchers = self._launcher_links(query)
        web = web or launchers["web"]
        return {"query": query, "web": web, "pdfs": [], "videos": launchers["videos"],
                "provider": "serper", "error": None, "extract": "", "page_title": None,
                "match_quality": "exact" if web else "none"}

    def _tavily_search(self, query: str, max_results: int) -> dict:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": self.api_key, "query": query, "max_results": max_results},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        candidates = [
            {"title": r.get("title", ""), "url": r.get("url", ""),
             "snippet": r.get("content", "")[:280], "source": r.get("url", "").split("/")[2] if r.get("url") else ""}
            for r in data.get("results", [])[:max_results]
        ]
        web = [c for c in candidates if self._is_verified(c["url"])]
        launchers = self._launcher_links(query)
        web = web or launchers["web"]
        return {"query": query, "web": web, "pdfs": [], "videos": launchers["videos"],
                "provider": "tavily", "error": None, "extract": "", "page_title": None,
                "match_quality": "exact" if web else "none"}

    def _bing_search(self, query: str, max_results: int) -> dict:
        resp = requests.get(
            "https://api.bing.microsoft.com/v7.0/search",
            headers={"Ocp-Apim-Subscription-Key": self.api_key},
            params={"q": query, "count": max_results},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        candidates = [
            {"title": r.get("name", ""), "url": r.get("url", ""),
             "snippet": r.get("snippet", ""), "source": r.get("displayUrl", "")}
            for r in data.get("webPages", {}).get("value", [])[:max_results]
        ]
        web = [c for c in candidates if self._is_verified(c["url"])]
        launchers = self._launcher_links(query)
        web = web or launchers["web"]
        return {"query": query, "web": web, "pdfs": [], "videos": launchers["videos"],
                "provider": "bing", "error": None, "extract": "", "page_title": None,
                "match_quality": "exact" if web else "none"}
