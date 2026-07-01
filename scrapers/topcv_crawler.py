from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib import robotparser
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup

from scrapers.fetching import DEFAULT_USER_AGENT, FetchResult, fetch_url as safe_fetch_url
from scrapers.storage import append_jsonl, existing_urls

BASE_URL = "https://www.topcv.vn"
DEFAULT_KEYWORDS = [
    "it",
    "cong-nghe-thong-tin",
]
KEYWORD_LISTING_URLS = {
    "it": f"{BASE_URL}/tim-viec-lam-it",
    "cong-nghe-thong-tin": f"{BASE_URL}/tim-viec-lam-cong-nghe-thong-tin-cr257",
}
USER_AGENT = DEFAULT_USER_AGENT
_ROBOTS: robotparser.RobotFileParser | None = None


class BlockDetected(RuntimeError):
    pass


@dataclass(frozen=True)
class Discovery:
    url: str
    discovered_from_url: str
    discovered_keyword: str
    discovered_page: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_url(url: str, timeout: int = 30) -> FetchResult:
    return safe_fetch_url(url, timeout=timeout, user_agent=USER_AGENT)


def can_fetch(url: str) -> bool:
    global _ROBOTS
    if _ROBOTS is not None:
        return _ROBOTS.can_fetch(USER_AGENT, url)

    parser = robotparser.RobotFileParser(urljoin(BASE_URL, "/robots.txt"))
    try:
        result = fetch_url(urljoin(BASE_URL, "/robots.txt"))
        if result.status and result.status >= 400:
            return False
        parser.parse(result.html.splitlines())
    except Exception:
        return False
    _ROBOTS = parser
    return parser.can_fetch(USER_AGENT, url)


def strip_accents(value: str) -> str:
    value = value.replace("Đ", "D").replace("đ", "d")
    return "".join(
        character for character in unicodedata.normalize("NFD", value) if unicodedata.category(character) != "Mn"
    )


def keyword_slug(keyword: str) -> str:
    normalized = strip_accents(keyword).casefold().strip()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return quote(normalized or "it")


def build_search_url(keyword: str, page: int) -> str:
    normalized_keyword = keyword_slug(keyword)
    base_url = KEYWORD_LISTING_URLS.get(normalized_keyword, f"{BASE_URL}/tim-viec-lam-{normalized_keyword}")
    if page <= 1:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}page={page}"


def normalize_job_url(href: str) -> str | None:
    href = unescape(href.strip())
    if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
        return None

    absolute_url = urljoin(BASE_URL, href)
    parsed = urlparse(absolute_url)
    if parsed.netloc and parsed.netloc not in {"topcv.vn", "www.topcv.vn"}:
        return None
    if not parsed.path.startswith("/viec-lam/"):
        return None
    if not re.search(r"/viec-lam/.+/\d+\.html$", parsed.path):
        return None
    return f"https://www.topcv.vn{parsed.path}"


def iter_json_ld_candidates(block: Any) -> list[dict[str, Any]]:
    stack = block if isinstance(block, list) else [block]
    candidates: list[dict[str, Any]] = []
    while stack:
        candidate = stack.pop(0)
        if not isinstance(candidate, dict):
            continue
        candidates.append(candidate)
        graph = candidate.get("@graph")
        if isinstance(graph, list):
            stack.extend(graph)
    return candidates


def extract_job_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()

    for block in extract_json_ld(html):
        for candidate in iter_json_ld_candidates(block):
            items = candidate.get("itemListElement") or []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                url_value = item.get("url")
                if not isinstance(url_value, str):
                    nested_item = item.get("item")
                    if isinstance(nested_item, dict):
                        url_value = nested_item.get("url")
                if not isinstance(url_value, str):
                    continue
                url = normalize_job_url(url_value)
                if url and url not in seen:
                    seen.add(url)
                    urls.append(url)

    for anchor in soup.find_all("a", href=True):
        url = normalize_job_url(str(anchor["href"]))
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def discover_job_urls(
    keywords: list[str],
    limit: int,
    pages_per_keyword: int,
    delay_min: float,
    delay_max: float,
    timeout: int,
) -> list[Discovery]:
    discovered: list[Discovery] = []
    seen: set[str] = set()

    for keyword in keywords:
        for page in range(1, pages_per_keyword + 1):
            if len(discovered) >= limit:
                return discovered
            search_url = build_search_url(keyword, page)
            if not can_fetch(search_url):
                print(f"Skip disallowed by robots.txt: {search_url}")
                continue

            try:
                result = fetch_url(search_url, timeout=timeout)
            except RuntimeError as error:
                print(error)
                continue
            if is_block_page(result.html):
                raise BlockDetected(f"Stop: possible block/captcha page detected for listing {search_url}")

            for job_url in extract_job_urls(result.html):
                if job_url in seen:
                    continue
                seen.add(job_url)
                discovered.append(
                    Discovery(
                        url=job_url,
                        discovered_from_url=search_url,
                        discovered_keyword=keyword,
                        discovered_page=page,
                    )
                )
                if len(discovered) >= limit:
                    return discovered

            time.sleep(random.uniform(delay_min, delay_max))

    return discovered


def extract_json_ld(html: str) -> list[Any]:
    soup = BeautifulSoup(html, "html.parser")
    blocks: list[Any] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text(" ", strip=True)
        if not text:
            continue
        try:
            blocks.append(json.loads(text))
        except json.JSONDecodeError:
            blocks.append({"raw": text})
    return blocks


def extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))


def is_block_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    lowered = html.lower()
    block_markers = [
        "access denied",
        "verify you are human",
        "unusual traffic",
        "checking if the site connection is secure",
        "attention required! | cloudflare",
        "please complete the security check",
        "please solve the captcha",
        "complete the captcha",
        "cf-chl",
        "turnstile",
    ]
    return any(marker in lowered or marker in title for marker in block_markers)


def is_job_detail_page(url: str, html: str) -> bool:
    if normalize_job_url(url) is None:
        return False
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    if "tim viec" in strip_accents(title).casefold():
        return False
    for block in extract_json_ld(html):
        for candidate in iter_json_ld_candidates(block):
            item_type = candidate.get("@type")
            if item_type == "JobPosting" or (isinstance(item_type, list) and "JobPosting" in item_type):
                return True
    return bool(soup.select_one("h1") and soup.select_one("main"))


def content_hash(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest()


def job_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    match = re.search(r"/(\d+)\.html$", parsed.path)
    if match:
        return f"topcv_{match.group(1)}"
    slug = parsed.path.rstrip("/").split("/")[-1]
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", slug).strip("-")
    return f"topcv_{slug}"


def crawl_job_detail(discovery: Discovery, timeout: int, retries: int) -> dict[str, Any] | None:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            result = fetch_url(discovery.url, timeout=timeout)
            if result.status and result.status >= 400:
                print(f"Skip HTTP {result.status}: {discovery.url}")
                return None
            if is_block_page(result.html):
                raise BlockDetected(f"Stop: possible block/captcha page detected for detail {discovery.url}")
            if not is_job_detail_page(discovery.url, result.html):
                print(f"Skip non-detail page: {discovery.url}")
                return None
            return {
                "source": "topcv",
                "url": discovery.url,
                "job_id": job_id_from_url(discovery.url),
                "html": result.html,
                "json_ld": extract_json_ld(result.html),
                "visible_text": extract_visible_text(result.html),
                "http_status": result.status,
                "fetcher": result.fetcher,
                "scraped_at": utc_now(),
                "discovered_from_url": discovery.discovered_from_url,
                "discovered_keyword": discovery.discovered_keyword,
                "discovered_page": discovery.discovered_page,
                "content_hash": content_hash(result.html),
            }
        except BlockDetected:
            raise
        except Exception as error:
            last_error = error
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    print(f"Failed after retries: {discovery.url} ({last_error})")
    return None


def crawl_topcv(
    output: Path,
    limit: int,
    keywords: list[str],
    pages_per_keyword: int,
    delay_min: float,
    delay_max: float,
    timeout: int,
    retries: int,
) -> None:
    already_saved = existing_urls(output)
    if len(already_saved) >= limit:
        print(f"Existing records: {len(already_saved)}. Target already satisfied for {output}")
        return

    discoveries = discover_job_urls(
        keywords=keywords,
        limit=limit + len(already_saved),
        pages_per_keyword=pages_per_keyword,
        delay_min=delay_min,
        delay_max=delay_max,
        timeout=timeout,
    )
    discoveries = [discovery for discovery in discoveries if discovery.url not in already_saved]
    discoveries = discoveries[: max(0, limit - len(already_saved))]

    print(f"Discovered {len(discoveries)} new job URLs. Existing records: {len(already_saved)}")
    for index, discovery in enumerate(discoveries, start=1):
        if not can_fetch(discovery.url):
            print(f"Skip disallowed by robots.txt: {discovery.url}")
            continue

        record = crawl_job_detail(discovery, timeout=timeout, retries=retries)
        if record is not None:
            append_jsonl(output, record)
            print(f"[{index}/{len(discoveries)}] saved {discovery.url}")
        time.sleep(random.uniform(delay_min, delay_max))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl TopCV job details into raw JSONL.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", type=Path, default=Path("data/raw/topcv_sample_50.jsonl"))
    parser.add_argument("--keywords", nargs="*", default=DEFAULT_KEYWORDS)
    parser.add_argument("--pages-per-keyword", type=int, default=3)
    parser.add_argument("--delay-min", type=float, default=2.0)
    parser.add_argument("--delay-max", type=float, default=4.0)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=2)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        crawl_topcv(
            output=args.output,
            limit=args.limit,
            keywords=args.keywords,
            pages_per_keyword=args.pages_per_keyword,
            delay_min=args.delay_min,
            delay_max=args.delay_max,
            timeout=args.timeout,
            retries=args.retries,
        )
    except BlockDetected as error:
        print(error)


if __name__ == "__main__":
    main()
