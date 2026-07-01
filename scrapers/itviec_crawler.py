from __future__ import annotations

import argparse
import json
import random
import re
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib import robotparser
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup

from scrapers.fetching import DEFAULT_USER_AGENT, FetchResult, fetch_url as safe_fetch_url
from scrapers.storage import append_jsonl, existing_urls

BASE_URL = "https://itviec.com"
DEFAULT_KEYWORDS = [
    "python",
    "java",
    "frontend",
    "backend",
    "react",
    "nodejs",
    "devops",
    "data",
    "tester",
]
USER_AGENT = DEFAULT_USER_AGENT
_ROBOTS: robotparser.RobotFileParser | None = None


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


def build_search_urls(keyword: str, pages_per_keyword: int) -> list[str]:
    encoded = quote_plus(keyword)
    urls: list[str] = []
    for page in range(1, pages_per_keyword + 1):
        urls.append(f"{BASE_URL}/it-jobs/{encoded}?page={page}")
    return urls


def normalize_job_url(href: str) -> str | None:
    href = unescape(href.strip())
    if not href or href.startswith("#") or href.startswith("mailto:"):
        return None

    absolute_url = urljoin(BASE_URL, href)
    parsed = urlparse(absolute_url)
    if parsed.netloc and parsed.netloc != "itviec.com":
        return None
    if "/it-jobs/" not in parsed.path:
        return None
    if parsed.path in {"/it-jobs", "/it-jobs/"}:
        return None
    slug = parsed.path.rstrip("/").split("/")[-1]
    if not re.search(r"-\d{4}$", slug):
        return None

    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def extract_job_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()

    for block in extract_json_ld(html):
        candidates = block if isinstance(block, list) else [block]
        for candidate in candidates:
            if not isinstance(candidate, dict) or candidate.get("@type") != "ItemList":
                continue
            items = candidate.get("itemListElement") or []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                url_value = item.get("url")
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
) -> list[str]:
    discovered: list[str] = []
    seen: set[str] = set()

    for keyword in keywords:
        for search_url in build_search_urls(keyword, pages_per_keyword):
            if len(discovered) >= limit:
                return discovered
            if not can_fetch(search_url):
                print(f"Skip disallowed by robots.txt: {search_url}")
                continue

            try:
                result = fetch_url(search_url)
            except RuntimeError as error:
                print(error)
                continue

            for job_url in extract_job_urls(result.html):
                if job_url in seen:
                    continue
                seen.add(job_url)
                discovered.append(job_url)
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
    ]
    return any(marker in lowered or marker in title for marker in block_markers)


def is_job_detail_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if re.search(r"Jobs in Viet Nam(?: Page \d+)? \| ITviec", title, re.IGNORECASE):
        return False
    json_ld = extract_json_ld(html)
    for block in json_ld:
        candidates = block if isinstance(block, list) else [block]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            item_type = candidate.get("@type")
            if item_type == "JobPosting" or (isinstance(item_type, list) and "JobPosting" in item_type):
                return True
    return bool(soup.select_one("h1") and "itviec" in title.lower())


def job_id_from_url(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", slug).strip("-")
    return f"itviec_{slug}"


def crawl_job_detail(url: str, timeout: int, retries: int) -> dict[str, Any] | None:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            result = fetch_url(url, timeout=timeout)
            if is_block_page(result.html):
                print(f"Stop: possible block/captcha page detected for {url}")
                return None
            if not is_job_detail_page(result.html):
                print(f"Skip non-detail page: {url}")
                return None
            return {
                "source": "itviec",
                "url": url,
                "job_id": job_id_from_url(url),
                "html": result.html,
                "json_ld": extract_json_ld(result.html),
                "visible_text": extract_visible_text(result.html),
                "http_status": result.status,
                "fetcher": result.fetcher,
                "scraped_at": utc_now(),
            }
        except Exception as error:
            last_error = error
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    print(f"Failed after retries: {url} ({last_error})")
    return None


def crawl_itviec(
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
    urls = discover_job_urls(
        keywords=keywords,
        limit=limit + len(already_saved),
        pages_per_keyword=pages_per_keyword,
        delay_min=delay_min,
        delay_max=delay_max,
    )
    urls = [url for url in urls if url not in already_saved]
    urls = urls[: max(0, limit - len(already_saved))]

    print(f"Discovered {len(urls)} new job URLs. Existing records: {len(already_saved)}")
    for index, url in enumerate(urls, start=1):
        if not can_fetch(url):
            print(f"Skip disallowed by robots.txt: {url}")
            continue

        record = crawl_job_detail(url, timeout=timeout, retries=retries)
        if record is not None:
            append_jsonl(output, record)
            print(f"[{index}/{len(urls)}] saved {url}")
        time.sleep(random.uniform(delay_min, delay_max))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl ITviec job details into raw JSONL.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", type=Path, default=Path("data/raw/itviec_sample_50.jsonl"))
    parser.add_argument("--keywords", nargs="*", default=DEFAULT_KEYWORDS)
    parser.add_argument("--pages-per-keyword", type=int, default=3)
    parser.add_argument("--delay-min", type=float, default=2.0)
    parser.add_argument("--delay-max", type=float, default=4.0)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=2)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    crawl_itviec(
        output=args.output,
        limit=args.limit,
        keywords=args.keywords,
        pages_per_keyword=args.pages_per_keyword,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        timeout=args.timeout,
        retries=args.retries,
    )


if __name__ == "__main__":
    main()
