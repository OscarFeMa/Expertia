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
    # Dominios que devuelven 403/404 de forma consistente (bloquean scraping).
    # Determinados empíricamente del log del 06/08: todos fallan y no producen
    # extracciones exitosas válidas. (doi.org, ncbi, jstor, etc. se conservan.)
    "anydesk.com", "businessdisabilityforum.org.uk", "chat.deepseek.com",
    "clipart-library.com", "compass.onlinelibrary.wiley.com", "onlinelibrary.wiley.com",
    "dictionary.cambridge.org", "dle.rae.es", "elpais.com", "forums.digitalspy.com",
    "helpforum.sky.com", "journals.aps.org", "models.com", "openai.com",
    "oro.open.ac.uk", "papers.ssrn.com", "philarchive.org", "philpapers.org",
    "pt.restaurantguru.com", "pubs.acs.org", "pubs.aip.org", "smarthistory.org",
    "ssi.armywarcollege.edu", "uk.trustpilot.com", "weworkremotely.com",
    "www.accountingweb.co.uk", "www.annualreviews.org", "www.asanet.org",
    "www.backyardchickens.com", "www.bls.gov", "www.bmj.com", "www.britannica.com",
    "www.britishmuseum.org", "www.canva.com", "www.circlehealthgroup.co.uk",
    "www.collinsdictionary.com", "www.curseforge.com", "www.digikey.com",
    "www.echr.coe.int", "www.ethnologue.com", "www.filmaffinity.com", "www.ft.com",
    "www.imdb.com", "www.imf.org", "www.iop.org", "www.jstor.org", "www.justia.com",
    "www.leganes.org", "www.magnific.com", "www.mayoclinic.org",
    "www.merriam-webster.com", "www.modelmanagement.com",
    "www.moneysavingexpert.com", "www.nga.gov", "www.nih.gov", "www.noaa.gov",
    "www.oecd.org", "www.oxfordbibliographies.com", "www.pccomponentes.com",
    "www.rand.org", "www.researchgate.net", "www.sciencedirect.com",
    "www.semanticscholar.org", "www.template.net", "www.thefreedictionary.com",
    "www.thelancet.com", "www.tripadvisor.com", "www.tripadvisor.pt", "www.ukbusinessforums.co.uk",
    "www.vecteezy.com", "www.viasion.com", "www.worldlii.org",
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

    @property
    def cache_size(self) -> int:
        return len(self._domain_cache)
