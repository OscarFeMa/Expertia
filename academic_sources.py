"""
Academic API connectors for Expertia.

Engines: ArXiv, PubMed, CrossRef, Semantic Scholar, Wikipedia batch.
All use HTTP GET with static responses — no JavaScript required.
"""

import time
import random
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from urllib.parse import quote_plus

import httpx
import requests

from config.settings import (
    SEARCH_DELAY_MIN,
    SEARCH_DELAY_MAX,
    MAX_RESULTS_PER_SEARCH,
    SEARCH_TIMEOUT,
    WIKIPEDIA_API_URL,
    WIKIPEDIA_USER_AGENT,
    PUBMED_API_KEY as SETTINGS_PUBMED_API_KEY,
    SEMANTIC_API_KEY as SETTINGS_SEMANTIC_API_KEY,
)

logger = logging.getLogger(__name__)


def apply_random_delay():
    delay = random.uniform(SEARCH_DELAY_MIN, SEARCH_DELAY_MAX)
    time.sleep(delay)


# ──────────────────────────────────────────────
#  ArXiv API
# ──────────────────────────────────────────────

ARXIV_BASE = "http://export.arxiv.org/api/query"
ARXIV_CATEGORIES = {
    "Medicine": "q-bio.QM",
    "Physics": "physics",
    "Cybersecurity": "cs.CR",
    "SoftwareEngineering": "cs.SE",
    "Mathematics": "math",
    "DataScience": "cs.LG",
    "Electronics": "cs.ET",
    "Chemistry": "chem",
    "Astronomy": "astro-ph",
    "PhilosophyHistory": "cs.GL",
    "ArtHistory": "cs.CV",
    "FinanceEconomics": "q-fin",
    "LegalSystem": "cs.CY",
    "Geopolitics": "cs.SI",
    "Linguistics": "cs.CL",
    "Psychology": "q-bio.NC",
    "Sociology": "cs.SI",
    "EnvironmentalScience": "physics.ao-ph",
}


def search_arxiv(query: str, max_results: Optional[int] = None,
                 domain: Optional[str] = None) -> List[Dict[str, str]]:
    if max_results is None:
        max_results = MAX_RESULTS_PER_SEARCH
    apply_random_delay()
    category = ARXIV_CATEGORIES.get(domain, "")
    cat_filter = f"cat:{category}+AND+" if category else ""
    search_query = f"{cat_filter}all:{quote_plus(query)}"
    url = f"{ARXIV_BASE}?search_query={search_query}&start=0&max_results={max_results}&sortBy=relevance"
    headers = {"User-Agent": "Expertia/1.0 (mailto:expertia@localhost)"}
    logger.info(f"[ARXIV] Searching: '{query}' cat={category}")
    try:
        resp = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        results = []
        for entry in root.findall("a:entry", ns):
            title = entry.find("a:title", ns)
            summary = entry.find("a:summary", ns)
            id_el = entry.find("a:id", ns)
            published = entry.find("a:published", ns)
            title_text = title.text.strip().replace("\n", " ") if title is not None and title.text else ""
            summary_text = summary.text.strip().replace("\n", " ") if summary is not None and summary.text else ""
            url_str = id_el.text.strip() if id_el is not None and id_el.text else ""
            pub_date = published.text[:10] if published is not None and published.text else ""
            results.append({
                "title": title_text,
                "href": url_str,
                "body": summary_text[:500],
                "published": pub_date,
                "source": "arxiv",
            })
        logger.info(f"[ARXIV] Found {len(results)} results for '{query}'")
        return results[:max_results]
    except Exception as e:
        logger.warning(f"[ARXIV] Search failed: {e}")
        return []


# ──────────────────────────────────────────────
#  PubMed E-utilities
# ──────────────────────────────────────────────

PUBMED_BASE_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_BASE_FETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_API_KEY = SETTINGS_PUBMED_API_KEY

# Domains relevant to PubMed: biomedical / life sciences
PUBMED_DOMAINS = {"Medicine", "Psychology", "EnvironmentalScience", "Chemistry", "Neuroscience"}


def search_pubmed(query: str, max_results: Optional[int] = None,
                  domain: Optional[str] = None) -> List[Dict[str, str]]:
    if max_results is None:
        max_results = MAX_RESULTS_PER_SEARCH
    if domain and domain not in PUBMED_DOMAINS:
        logger.debug(f"[PUBMED] Skipping domain '{domain}' — not in PUBMED_DOMAINS")
        return []
    apply_random_delay()
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results * 2,
        "retmode": "json",
        "tool": "expertia",
        "email": "expertia@localhost",
    }
    if PUBMED_API_KEY:
        params["api_key"] = PUBMED_API_KEY
    logger.info(f"[PUBMED] Searching: '{query}'")
    try:
        resp = requests.get(PUBMED_BASE_SEARCH, params=params, timeout=SEARCH_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        id_list = data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []
        ids = ",".join(id_list[:max_results])
        fetch_params = {
            "db": "pubmed",
            "id": ids,
            "retmode": "xml",
            "rettype": "abstract",
            "tool": "expertia",
            "email": "expertia@localhost",
        }
        if PUBMED_API_KEY:
            fetch_params["api_key"] = PUBMED_API_KEY
        fetch_resp = requests.get(PUBMED_BASE_FETCH, params=fetch_params, timeout=SEARCH_TIMEOUT)
        fetch_resp.raise_for_status()
        results = _parse_pubmed_xml(fetch_resp.text)
        logger.info(f"[PUBMED] Found {len(results)} results for '{query}'")
        return results
    except Exception as e:
        logger.warning(f"[PUBMED] Search failed: {e}")
        return []


def _parse_pubmed_xml(xml_text: str) -> List[Dict[str, str]]:
    results = []
    try:
        root = ET.fromstring(xml_text)
        for article in root.findall(".//PubmedArticle"):
            medline = article.find(".//MedlineCitation")
            if medline is None:
                continue
            title_el = medline.find(".//ArticleTitle")
            title = "".join(title_el.itertext()) if title_el is not None else ""
            abstract_el = medline.find(".//AbstractText")
            abstract = "".join(abstract_el.itertext()) if abstract_el is not None else ""
            pmid_el = medline.find(".//PMID")
            pmid = pmid_el.text if pmid_el is not None else ""
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
            results.append({
                "title": title.strip(),
                "href": url,
                "body": abstract.strip()[:500],
                "source": "pubmed",
            })
    except ET.ParseError as e:
        logger.warning(f"PubMed XML parse error: {e}")
    return results


# ──────────────────────────────────────────────
#  CrossRef API
# ──────────────────────────────────────────────

CROSSREF_BASE = "https://api.crossref.org/works"


def search_crossref(query: str, max_results: Optional[int] = None) -> List[Dict[str, str]]:
    if max_results is None:
        max_results = MAX_RESULTS_PER_SEARCH
    apply_random_delay()
    params = {"query": query, "rows": max_results}
    headers = {"User-Agent": "Expertia/1.0 (mailto:expertia@localhost)"}
    logger.info(f"[CROSSREF] Searching: '{query}'")
    try:
        resp = requests.get(CROSSREF_BASE, params=params, headers=headers, timeout=SEARCH_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("message", {}).get("items", [])
        results = []
        for item in items:
            title = (item.get("title") or [""])[0]
            doi = item.get("DOI", "")
            url = f"https://doi.org/{doi}" if doi else ""
            abstract = item.get("abstract", "")
            container = item.get("container-title", [""])[0]
            body = abstract or ""
            results.append({
                "title": title,
                "href": url,
                "body": body[:500],
                "doi": doi,
                "journal": container,
                "source": "crossref",
            })
        logger.info(f"[CROSSREF] Found {len(results)} results for '{query}'")
        return results[:max_results]
    except Exception as e:
        logger.warning(f"[CROSSREF] Search failed: {e}")
        return []


# ──────────────────────────────────────────────
#  Semantic Scholar API
# ──────────────────────────────────────────────

SEMANTIC_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_API_KEY = SETTINGS_SEMANTIC_API_KEY

# Semantic Scholar API works without key: 100 req/5 min shared.
# With key: 1 RPS dedicated. Request at https://www.semanticscholar.org/product/api


def search_semantic(query: str, max_results: Optional[int] = None) -> List[Dict[str, str]]:
    if max_results is None:
        max_results = MAX_RESULTS_PER_SEARCH
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,year,doi,url,citationCount",
    }
    headers = {"User-Agent": "Expertia/1.0"}
    if SEMANTIC_API_KEY:
        headers["x-api-key"] = SEMANTIC_API_KEY
    max_retries = 3
    for attempt in range(max_retries):
        if attempt == 0:
            time.sleep(random.uniform(1, 5))
        else:
            apply_random_delay()
        logger.info(f"[SEMANTIC] Searching: '{query}' (attempt {attempt+1}/{max_retries})")
        try:
            resp = requests.get(SEMANTIC_BASE, params=params, headers=headers, timeout=SEARCH_TIMEOUT)
            if resp.status_code == 429 and attempt < max_retries - 1:
                    wait = 15 * (attempt + 1) + random.uniform(0, 10)
                    logger.warning(f"[SEMANTIC] Rate limited (429), retrying in {wait:.0f}s (attempt {attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue
            resp.raise_for_status()
            data = resp.json()
            papers = data.get("data", [])
            results = []
            for paper in papers:
                results.append({
                    "title": paper.get("title", ""),
                    "href": paper.get("url", "") or f"https://api.semanticscholar.org/{paper.get('paperId', '')}",
                    "body": (paper.get("abstract") or "")[:500],
                    "year": paper.get("year", ""),
                    "citations": paper.get("citationCount", 0),
                    "source": "semantic_scholar",
                })
            logger.info(f"[SEMANTIC] Found {len(results)} results for '{query}'")
            return results[:max_results]
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 10 * (attempt + 1)
                logger.warning(f"[SEMANTIC] Attempt {attempt+1} failed: {e}, retrying in {wait}s")
                time.sleep(wait)
                continue
            logger.warning(f"[SEMANTIC] Search failed after {max_retries} attempts: {e}")
    return []


# ──────────────────────────────────────────────
#  Wikipedia batch search (multi-title)
# ──────────────────────────────────────────────

WIKIPEDIA_HEADERS = {"User-Agent": WIKIPEDIA_USER_AGENT}


def search_wikipedia_batch(query: str, max_results: Optional[int] = None,
                           lang: str = "en") -> List[Dict[str, str]]:
    if max_results is None:
        max_results = MAX_RESULTS_PER_SEARCH
    apply_random_delay()
    base_url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": min(max_results * 2, 50),
        "srprop": "snippet|titlesnippet",
    }
    logger.info(f"[WIKI-BATCH] Searching: '{query}' lang={lang}")
    try:
        resp = requests.get(base_url, params=params, headers=WIKIPEDIA_HEADERS, timeout=SEARCH_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        search_results = data.get("query", {}).get("search", [])
        results = []
        for s in search_results[:max_results]:
            title = s.get("title", "")
            page_url = f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
            results.append({
                "title": title,
                "href": page_url,
                "body": s.get("snippet", "").replace("<span class=\"searchmatch\">", "").replace("</span>", ""),
                "source": "wikipedia",
            })
        logger.info(f"[WIKI-BATCH] Found {len(results)} results for '{query}'")
        return results
    except Exception as e:
        logger.warning(f"[WIKI-BATCH] Search failed: {e}")
        return []


# ──────────────────────────────────────────────
#  Multi-engine: try academic sources in priority order
# ──────────────────────────────────────────────

ACADEMIC_ENGINES = [
    ("arxiv", search_arxiv),
    ("pubmed", search_pubmed),
    ("crossref", search_crossref),
    ("semantic", search_semantic),
    ("wikipedia", search_wikipedia_batch),
]


def search_all_academic(query: str, max_results: Optional[int] = None,
                        domain: Optional[str] = None) -> List[Dict[str, str]]:
    if max_results is None:
        max_results = MAX_RESULTS_PER_SEARCH
    all_results = []
    seen_hrefs = set()

    for name, engine_fn in ACADEMIC_ENGINES:
        try:
            if name in ("arxiv", "pubmed"):
                results = engine_fn(query, max_results, domain=domain)
            elif name == "wikipedia":
                results = engine_fn(query, max_results)
            else:
                results = engine_fn(query, max_results)
            for r in results:
                href = r.get("href", "")
                if href and href not in seen_hrefs:
                    seen_hrefs.add(href)
                    all_results.append(r)
        except Exception as e:
            logger.warning(f"[ACADEMIC] Engine {name} failed: {e}")

    logger.info(f"[ACADEMIC] Total {len(all_results)} unique results across all engines")
    return all_results[:max_results * 3]
