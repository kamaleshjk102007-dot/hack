from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests

from .models import Source
from .source_ranker import SourceRanker


class Retriever:
    """Retrieves only URLs and text actually returned by external services."""

    def __init__(self, session=None, timeout=8):
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.timeout = timeout
        self.ranker = SourceRanker()

    def build_queries(self, query: str, fresh: bool = False) -> list[str]:
        base = query.strip().rstrip("?")
        values = [base]
        if fresh:
            values.append(f"{base} official latest")
        values.append(f"{base} official source")
        return list(dict.fromkeys(values))[:3]

    def retrieve(self, queries: list[str]) -> list[Source]:
        found = []
        now = datetime.now(timezone.utc).isoformat()
        for query in queries:
            try:
                response = self.session.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                    headers={"User-Agent": "EDITH-Verification/1.0"}, timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
            except Exception:
                continue
            url = data.get("AbstractURL", "")
            text = data.get("AbstractText", "") or data.get("Answer", "")
            if url and text:
                level, score = self.ranker.score(url)
                found.append(Source(url, data.get("Heading") or data.get("AbstractSource") or url,
                                    text, score, level, now, query))
            for topic in data.get("RelatedTopics", [])[:6]:
                if "Topics" in topic:
                    candidates = topic.get("Topics", [])[:3]
                else:
                    candidates = [topic]
                for item in candidates:
                    url, text = item.get("FirstURL", ""), item.get("Text", "")
                    if url and text:
                        level, score = self.ranker.score(url)
                        found.append(Source(url, text.split(" - ", 1)[0][:100], text,
                                            score, level, now, query))
            # Instant Answers are sparse for entertainment/entity relations.
            # DuckDuckGo HTML supplies real result URLs plus snippets without
            # granting any snippet automatic verification status.
            try:
                html = self.session.get(
                    "https://html.duckduckgo.com/html/", params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 EDITH-Verification/1.0"}, timeout=self.timeout,
                )
                html.raise_for_status()
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html.text, "html.parser")
                for row in soup.select(".result")[:8]:
                    anchor = row.select_one(".result__a")
                    snippet = row.select_one(".result__snippet")
                    if not anchor or not snippet:
                        continue
                    url = anchor.get("href", "")
                    text = snippet.get_text(" ", strip=True)
                    if not url.startswith("http") or not text:
                        continue
                    level, score = self.ranker.score(url)
                    found.append(Source(url, anchor.get_text(" ", strip=True)[:120], text,
                                        score, level, now, query))
            except Exception:
                pass
            # Entity-resolution fallback. MediaWiki returns the actual page
            # extract and canonical URL, not an invented or model-generated
            # citation. It is deliberately ranked below primary/industry data.
            try:
                wiki = self.session.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={"action": "query", "generator": "search", "gsrsearch": query,
                            "gsrlimit": 3, "prop": "extracts|info", "exintro": 1,
                            "explaintext": 1, "inprop": "url", "format": "json"},
                    headers={"User-Agent": "EDITH-Verification/1.0"}, timeout=self.timeout,
                )
                wiki.raise_for_status()
                pages = wiki.json().get("query", {}).get("pages", {})
                for page in pages.values():
                    url, text = page.get("fullurl", ""), page.get("extract", "")
                    if not url or not text:
                        continue
                    level, score = self.ranker.score(url)
                    found.append(Source(url, page.get("title", url), text, score, level, now, query))
            except Exception:
                pass
        return self.ranker.rank(found)
