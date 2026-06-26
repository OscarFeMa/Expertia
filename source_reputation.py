"""
Source Reputation Tracker — EEAT / TrustRank by TLD, domain patterns, and blocklist.
"""

import logging
from urllib.parse import urlparse
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

TLD_TRUST: Dict[str, int] = {
    ".gov": 100, ".edu": 100, ".ac.uk": 100, ".ac": 95,
    ".edu.au": 100, ".edu.cn": 95, ".ac.jp": 95,
    ".org": 70, ".int": 90, ".mil": 85,
}

TIER1_DOMAIN_PATTERNS: Set[str] = {
    "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
    "ieee.org", "acm.org", "nature.com", "sciencedirect.com",
    "springer.com", "wiley.com", "elsevier.com", "plos.org",
    "biomedcentral.com", "frontiersin.org", "mdpi.com",
    "cambridge.org", "oxfordjournals.org", "oup.com",
    "tandfonline.com", "sagepub.com", "jstor.org",
    "science.org", "cell.com", "thelancet.com", "bmj.com",
    "nejm.org", "jamanetwork.com", "cochrane.org",
    "who.int", "reuters.com", "bloomberg.com", "ft.com",
    "wsj.com", "economist.com", "britannica.com",
    "docs.python.org", "postgresql.org", "kubernetes.io",
    "developer.mozilla.org", "go.dev", "rust-lang.org",
    "docs.rs", "nginx.org", "apache.org",
    "gov.uk", "europa.eu", "worldbank.org", "imf.org",
    "oecd.org", "un.org", "nasa.gov", "noaa.gov",
    "nih.gov", "cdc.gov", "fda.gov",
}

TIER2_DOMAIN_PATTERNS: Set[str] = {
    "wikipedia.org", "stackoverflow.com", "github.com",
    "gitlab.com", "medium.com", "dev.to", "huggingface.co",
    "readthedocs.io", "towardsdatascience.com",
    "arxiv-vanity.com", "paperswithcode.com",
    "semanticscholar.org", "researchgate.net",
    "academia.edu", "ssrn.com", "zenodo.org",
    "figshare.com", "osf.io", "protocols.io",
    "dblp.org", "mathoverflow.net", "cstheory.stackexchange.com",
}

BLOCKED_DOMAINS: Set[str] = {
    "quora.com", "reddit.com", "pinterest.com", "tiktok.com",
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "twitch.tv", "linkedin.com",
}

BLOCKED_PATTERNS: Set[str] = {
    "clickbait", "content-farm", "spam", "payday-loan",
    "casin", "porn", "adult", "xxx",
}


def _extract_netloc(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


def _get_tld(netloc: str) -> str:
    for tld in sorted(TLD_TRUST.keys(), key=len, reverse=True):
        if netloc.endswith(tld):
            return tld
    return ""


def score_url(url: str) -> int:
    if not url:
        return 40
    netloc = _extract_netloc(url)
    if not netloc:
        return 40

    for blocked in BLOCKED_DOMAINS:
        if blocked in netloc:
            return 0
    for pattern in BLOCKED_PATTERNS:
        if pattern in netloc or pattern in url.lower():
            return 5

    tld = _get_tld(netloc)
    if TLD_TRUST.get(tld, 0) >= 100:
        return 100

    for pattern in TIER1_DOMAIN_PATTERNS:
        if pattern in netloc:
            return 100

    for pattern in TIER2_DOMAIN_PATTERNS:
        if pattern in netloc:
            return 70

    if tld:
        return TLD_TRUST[tld]

    return 40


def classify_url(url: str) -> int:
    score = score_url(url)
    if score >= 85:
        return 1
    if score >= 60:
        return 2
    return 3


def is_blocked(url: str) -> bool:
    netloc = _extract_netloc(url)
    for blocked in BLOCKED_DOMAINS:
        if blocked in netloc:
            return True
    for pattern in BLOCKED_PATTERNS:
        if pattern in netloc or pattern in url.lower():
            return True
    return False


class SourceReputationTracker:
    def __init__(self):
        self._domain_cache: Dict[str, int] = {}

    def get_trust_score(self, url: str) -> int:
        if not url:
            return 40
        netloc = _extract_netloc(url)
        if not netloc:
            return 40
        if netloc in self._domain_cache:
            return self._domain_cache[netloc]
        score = score_url(url)
        self._domain_cache[netloc] = score
        return score

    def get_tier(self, url: str) -> int:
        return classify_url(url)

    def is_acceptable(self, url: str, min_score: int = 40) -> bool:
        if is_blocked(url):
            return False
        return self.get_trust_score(url) >= min_score

    def get_details(self, url: str) -> Dict:
        netloc = _extract_netloc(url)
        score = self.get_trust_score(url)
        tier = classify_url(url)
        tld = _get_tld(netloc)
        return {
            "url": url,
            "netloc": netloc,
            "tld": tld,
            "trust_score": score,
            "tier": tier,
            "blocked": is_blocked(url),
        }

    @property
    def cache_size(self) -> int:
        return len(self._domain_cache)
