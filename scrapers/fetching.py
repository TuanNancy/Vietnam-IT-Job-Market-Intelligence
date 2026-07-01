from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_USER_AGENT = "VietnamITJobMarketResearchBot/0.1 (+research project; respectful crawl)"


@dataclass(frozen=True)
class FetchResult:
    url: str
    html: str
    status: int | None
    fetcher: str


def fetch_with_scrapling(url: str, timeout: int = 30, user_agent: str = DEFAULT_USER_AGENT) -> FetchResult | None:
    try:
        from scrapling.fetchers import Fetcher  # type: ignore
    except ImportError:
        return None

    try:
        page = Fetcher.get(url, timeout=timeout, headers={"User-Agent": user_agent})
    except Exception:
        return None

    body = getattr(page, "body", None)
    if isinstance(body, bytes):
        encoding = getattr(page, "encoding", None) or "utf-8"
        html = body.decode(encoding, errors="replace")
    else:
        html_content = getattr(page, "html_content", None)
        html = str(html_content if html_content is not None else page)

    status = getattr(page, "status", None) or getattr(page, "status_code", None)
    final_url = str(getattr(page, "url", None) or url)
    return FetchResult(url=final_url, html=html, status=status, fetcher="scrapling")


def fetch_url(url: str, timeout: int = 30, user_agent: str = DEFAULT_USER_AGENT) -> FetchResult:
    scrapling_result = fetch_with_scrapling(url, timeout=timeout, user_agent=user_agent)
    if scrapling_result is not None:
        return scrapling_result

    request = Request(url, headers={"User-Agent": user_agent})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return FetchResult(url=url, html=body, status=response.status, fetcher="urllib")
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return FetchResult(url=url, html=body, status=error.code, fetcher="urllib")
    except URLError as error:
        raise RuntimeError(f"Network error while fetching {url}: {error}") from error
