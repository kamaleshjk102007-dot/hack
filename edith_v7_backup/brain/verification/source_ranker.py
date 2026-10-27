from __future__ import annotations

from urllib.parse import unquote, urlparse

from .models import Source


class SourceRanker:
    PRIMARY_SUFFIXES = (".gov", ".gov.in", ".edu", ".ac.in")
    HIGH_RELIABILITY = {
        "reuters.com", "apnews.com", "bbc.com", "who.int", "un.org", "nasa.gov",
        "imdb.com", "themoviedb.org", "docs.python.org", "developer.mozilla.org",
        "bookmyshow.com", "rottentomatoes.com", "fandango.com", "tfapa.com",
        "marvel.com", "thewaltdisneycompany.com",
    }
    LOW_HINTS = ("blog", "forum", "medium.com", "quora.com", "reddit.com", "pinterest")

    def score(self, url: str) -> tuple[int, float]:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        if host.endswith(self.PRIMARY_SUFFIXES) or host.startswith(("docs.", "developer.")):
            return 1, 0.95
        if any(host == d or host.endswith("." + d) for d in self.HIGH_RELIABILITY):
            return 2, 0.86
        if host.endswith("wikipedia.org"):
            return 3, 0.76
        if any(h in host for h in self.LOW_HINTS):
            return 4, 0.30
        return 3, 0.58

    def rank(self, sources: list[Source]) -> list[Source]:
        deduped = {}
        for source in sources:
            canonical_url = unquote(source.url.split("#", 1)[0]).rstrip("/")
            deduped.setdefault(canonical_url, source)
        return sorted(deduped.values(), key=lambda item: (-item.reliability, item.url))
