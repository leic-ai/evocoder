"""
Web Search Tool for EvoCoder

Provides web search via DuckDuckGo (primary) with Bing fallback,
plus page fetching with BeautifulSoup parsing.

Rate-limited to 1 request per second across all backends.
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """A single search result."""
    title: str
    url: str
    snippet: str = ""
    source: str = ""  # which engine produced it


@dataclass
class PageContent:
    """Parsed content of a fetched web page."""
    url: str
    title: str
    text: str
    links: List[Dict[str, str]] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Simple global rate limiter: at most one call per *interval* seconds."""

    def __init__(self, interval: float = 1.0):
        self._interval = interval
        self._last_call: float = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)
        self._last_call = time.monotonic()


# Shared instance so every WebSearcher instance respects the same budget.
_global_limiter = _RateLimiter(1.0)

# ---------------------------------------------------------------------------
# WebSearcher
# ---------------------------------------------------------------------------

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class WebSearcher:
    """
    Web search with DuckDuckGo (primary) and Bing (fallback).

    Usage::

        searcher = WebSearcher()
        results = searcher.search("python async", max_results=5)
        page = searcher.fetch_page(results[0].url)
    """

    def __init__(
        self,
        timeout: int = 10,
        rate_limit: float = 1.0,
    ):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(_DEFAULT_HEADERS)
        # If caller wants a custom interval, create a local limiter.
        self._limiter = _global_limiter if rate_limit == 1.0 else _RateLimiter(rate_limit)

    # -- public API ---------------------------------------------------------

    def search(
        self,
        query: str,
        max_results: int = 10,
        engine: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search the web.

        Parameters
        ----------
        query : str
            Search query string.
        max_results : int
            Maximum number of results to return (default 10).
        engine : str or None
            Force a specific engine: ``"ddg"`` or ``"bing"``.
            ``None`` (default) tries DuckDuckGo first, falls back to Bing.

        Returns
        -------
        list[SearchResult]
        """
        if not query or not query.strip():
            return []

        if engine == "ddg":
            return self._search_ddg(query, max_results)
        if engine == "bing":
            return self._search_bing(query, max_results)

        # Default: DDG primary, Bing fallback
        results = self._search_ddg(query, max_results)
        if not results:
            logger.info("DuckDuckGo returned no results, falling back to Bing")
            results = self._search_bing(query, max_results)
        return results

    def fetch_page(self, url: str) -> PageContent:
        """
        Fetch a URL and parse it with BeautifulSoup.

        Returns a ``PageContent`` with title, plain text, links, and meta.
        """
        self._limiter.wait()
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")

        title = _get_title(soup)
        text = _get_text(soup)
        links = _get_links(soup, url)
        meta = _get_meta(soup)

        return PageContent(
            url=url,
            title=title,
            text=text,
            links=links,
            meta=meta,
        )

    # -- DuckDuckGo ---------------------------------------------------------

    def _search_ddg(self, query: str, max_results: int) -> List[SearchResult]:
        """Scrape DuckDuckGo HTML results."""
        self._limiter.wait()
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("DuckDuckGo request failed: %s", exc)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        results: List[SearchResult] = []

        for item in soup.select(".result"):
            title_tag = item.select_one(".result__title a")
            snippet_tag = item.select_one(".result__snippet")
            if not title_tag:
                continue

            href = title_tag.get("href", "")
            # DDG sometimes wraps URLs in a redirect; try to extract direct URL
            direct = _extract_ddg_url(href)

            results.append(SearchResult(
                title=title_tag.get_text(strip=True),
                url=direct or href,
                snippet=snippet_tag.get_text(strip=True) if snippet_tag else "",
                source="duckduckgo",
            ))

            if len(results) >= max_results:
                break

        return results

    # -- Bing ---------------------------------------------------------------

    def _search_bing(self, query: str, max_results: int) -> List[SearchResult]:
        """Scrape Bing HTML results."""
        self._limiter.wait()
        url = f"https://www.bing.com/search?q={quote_plus(query)}&count={max_results}"

        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Bing request failed: %s", exc)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        results: List[SearchResult] = []

        for item in soup.select("li.b_algo"):
            title_tag = item.select_one("h2 a")
            snippet_tag = item.select_one(".b_caption p")
            if not title_tag:
                continue

            results.append(SearchResult(
                title=title_tag.get_text(strip=True),
                url=title_tag.get("href", ""),
                snippet=snippet_tag.get_text(strip=True) if snippet_tag else "",
                source="bing",
            ))

            if len(results) >= max_results:
                break

        return results

    # -- teardown -----------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()

    def __enter__(self) -> "WebSearcher":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Module-level helpers (HTML parsing)
# ---------------------------------------------------------------------------

def _extract_ddg_url(href: str) -> str:
    """
    DuckDuckGo wraps result URLs in a redirect proxy.
    Try to pull out the real ``uddg`` parameter if present.
    """
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    if "uddg" in qs:
        return qs["uddg"][0]
    return href


def _get_title(soup: BeautifulSoup) -> str:
    tag = soup.find("title")
    return tag.get_text(strip=True) if tag else ""


def _get_text(soup: BeautifulSoup) -> str:
    """Extract visible page text, stripping scripts and styles."""
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _get_links(soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
    """Return a list of ``{text, href}`` for all anchor tags."""
    links: List[Dict[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("javascript:", "mailto:", "#")):
            continue
        links.append({
            "text": a.get_text(strip=True),
            "href": urljoin(base_url, href),
        })
    return links


def _get_meta(soup: BeautifulSoup) -> Dict[str, str]:
    """Return a dict of interesting ``<meta>`` tags."""
    meta: Dict[str, str] = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property", "")
        content = tag.get("content", "")
        if name and content:
            meta[name] = content
    return meta


# ---------------------------------------------------------------------------
# Registration helper (plug into EvoCoder's ToolRegistry)
# ---------------------------------------------------------------------------

def register_web_search(registry: Any) -> WebSearcher:
    """
    Register ``web_search`` and ``fetch_page`` tools on the given
    ``ToolRegistry`` and return the shared ``WebSearcher`` instance.
    """
    searcher = WebSearcher()

    @registry.register(
        name="web_search",
        description="Search the web using DuckDuckGo (primary) or Bing (fallback). Returns a list of results with title, URL, and snippet.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default 10).",
                },
                "engine": {
                    "type": "string",
                    "enum": ["ddg", "bing"],
                    "description": "Force a specific search engine (optional).",
                },
            },
            "required": ["query"],
        },
        category="web",
    )
    def web_search(query: str, max_results: int = 10, engine: Optional[str] = None) -> List[Dict[str, str]]:
        results = searcher.search(query, max_results=max_results, engine=engine)
        return [
            {"title": r.title, "url": r.url, "snippet": r.snippet, "source": r.source}
            for r in results
        ]

    @registry.register(
        name="fetch_page",
        description="Fetch a web page and extract its title, text content, links, and meta tags using BeautifulSoup.",
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch.",
                },
            },
            "required": ["url"],
        },
        category="web",
    )
    def fetch_page(url: str) -> Dict[str, Any]:
        page = searcher.fetch_page(url)
        return {
            "url": page.url,
            "title": page.title,
            "text": page.text[:8000],  # truncate to keep LLM context manageable
            "links": page.links[:50],
            "meta": page.meta,
        }

    return searcher
