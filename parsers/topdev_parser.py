from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from parsers.common import CLEAN_FIELDNAMES, trend_fields
from parsers.itviec_parser import (
    append_unique,
    canonical_casefold,
    clean_text,
    extract_skills,
    parse_salary_values,
)
from scrapers.storage import append_jsonl, ensure_parent, read_jsonl

DESCRIPTION_HEADING_MARKERS = [
    "why you should apply",
    "why you'll love",
    "why you will love",
    "your role",
    "roles and responsibilities",
    "responsibilities",
    "your skills",
    "skills and qualifications",
    "qualifications",
    "requirements",
    "benefits",
    "mô tả công việc",
    "trách nhiệm",
    "yêu cầu công việc",
    "yêu cầu ứng viên",
    "phúc lợi",
]

REQUIREMENTS_START_MARKERS = [
    "Your skills & qualifications",
    "Your skills and qualifications",
    "Skills & qualifications",
    "Skills and qualifications",
    "Requirements",
    "Yêu cầu công việc",
    "Yêu cầu ứng viên",
]

REQUIREMENTS_END_MARKERS = [
    "Benefits",
    "Phúc lợi",
    "Why you should apply",
    "Your role",
    "Responsibilities",
    "Other jobs",
]

NOISE_MARKERS = [
    "Other jobs at this company",
    "Other jobs",
    "Candidates supporters",
    "Candidate supporters",
    "Interview questions",
    "TopDev Blog",
    "Latest blog",
    "Featured companies",
    "Highlight companies",
    "Company card",
    "Similar jobs",
    "Jobs you may like",
    "TopDev.vn",
]


def soup_from_record(record: dict[str, Any]) -> BeautifulSoup:
    return BeautifulSoup(record.get("html") or "", "html.parser")


def first_meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return clean_text(str(tag["content"]))
    return None


def first_selector_text(soup: BeautifulSoup | Tag, selectors: list[str]) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = clean_text(node.get_text(" ", strip=True))
            if text:
                return text
    return None


def parse_json_ld(record: dict[str, Any]) -> dict[str, Any]:
    blocks = record.get("json_ld") or []
    if isinstance(blocks, dict):
        blocks = [blocks]

    for block in blocks:
        candidates = block if isinstance(block, list) else [block]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            graph = candidate.get("@graph")
            if isinstance(graph, list):
                candidates.extend(item for item in graph if isinstance(item, dict))
            item_type = candidate.get("@type")
            if item_type == "JobPosting" or (isinstance(item_type, list) and "JobPosting" in item_type):
                return candidate
    return {}


def strip_accents(value: str) -> str:
    value = value.replace("Đ", "D").replace("đ", "d")
    return "".join(
        character for character in unicodedata.normalize("NFD", value) if unicodedata.category(character) != "Mn"
    )


def fold_for_matching(value: str) -> str:
    return strip_accents(value).casefold()


def normalize_location(value: str | None) -> str | None:
    parsed = clean_text(value)
    if not parsed:
        return None

    folded = fold_for_matching(parsed)
    if folded in {"not available", "n/a", "na"}:
        return None
    if re.search(r"\b(?:tp\.?\s*)?(?:hcm|ho chi minh|thanh pho ho chi minh|sai gon)\b", folded):
        return "Hồ Chí Minh"
    if re.search(r"\b(?:ha noi|hanoi)\b", folded):
        return "Hà Nội"
    if re.search(r"\b(?:da nang|danang)\b", folded):
        return "Đà Nẵng"
    return parsed


def job_scope(soup: BeautifulSoup) -> BeautifulSoup | Tag:
    for selector in [
        "main",
        "article",
        "[data-testid*='job-detail']",
        "[class*='job-detail']",
        "[class*='jobDetail']",
    ]:
        node = soup.select_one(selector)
        if node:
            return node
    return soup.body or soup


def node_text(node: BeautifulSoup | Tag) -> str | None:
    return clean_text(node.get_text(" ", strip=True))


def is_noise_text(value: str | None) -> bool:
    parsed = clean_text(value)
    if not parsed:
        return False
    folded = canonical_casefold(parsed[:160])
    return any(canonical_casefold(marker) in folded for marker in NOISE_MARKERS)


def remove_heading_block(heading: Tag, scope: BeautifulSoup) -> None:
    container = heading.find_parent(["section", "article", "aside"])
    if container and container is not scope:
        container.decompose()
        return

    for sibling in list(heading.next_siblings):
        if isinstance(sibling, Tag) and sibling.name in {"h1", "h2", "h3", "h4", "h5"}:
            break
        if isinstance(sibling, (Tag, NavigableString)):
            sibling.extract()
    heading.extract()


def pruned_scope(soup: BeautifulSoup) -> BeautifulSoup:
    scoped = BeautifulSoup(str(job_scope(soup)), "html.parser")
    for tag in scoped(["script", "style", "noscript", "svg", "footer", "nav", "aside", "form", "iframe"]):
        tag.decompose()

    for heading in list(scoped.find_all(["h2", "h3", "h4", "h5"])):
        if is_noise_text(heading.get_text(" ", strip=True)):
            remove_heading_block(heading, scoped)

    for container in list(scoped.find_all(["section", "article", "aside", "div", "ul"])):
        heading = container.find(["h2", "h3", "h4", "h5"], recursive=False)
        heading_text = heading.get_text(" ", strip=True) if heading else container.get_text(" ", strip=True)[:120]
        if is_noise_text(heading_text):
            container.decompose()
    return scoped


def trim_noise_text(text: str | None) -> str | None:
    parsed = clean_text(text)
    if not parsed:
        return None

    folded = canonical_casefold(parsed)
    end = len(parsed)
    for marker in NOISE_MARKERS:
        marker_index = folded.find(canonical_casefold(marker))
        if marker_index >= 0:
            end = min(end, marker_index)
    return clean_text(parsed[:end])


def heading_matches(text: str | None, markers: list[str]) -> bool:
    parsed = clean_text(text)
    if not parsed:
        return False
    folded = canonical_casefold(parsed)
    return any(canonical_casefold(marker) in folded for marker in markers)


def collect_heading_content(heading: Tag) -> str | None:
    parts: list[str] = []
    for sibling in heading.next_siblings:
        if isinstance(sibling, Tag) and sibling.name in {"h1", "h2", "h3", "h4", "h5"}:
            break
        if isinstance(sibling, NavigableString):
            text = clean_text(str(sibling))
        elif isinstance(sibling, Tag):
            text = node_text(sibling)
        else:
            text = None
        if is_noise_text(text):
            break
        if text:
            parts.append(text)
    return trim_noise_text(" ".join(parts))


def extract_line_sections(text: str | None) -> str | None:
    if not text:
        return None

    lines = [line.strip() for line in text.splitlines() if clean_text(line)]
    sections: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if is_noise_text(line):
            break
        if not heading_matches(line, DESCRIPTION_HEADING_MARKERS):
            index += 1
            continue

        heading = clean_text(line)
        parts: list[str] = []
        index += 1
        while index < len(lines):
            current = lines[index]
            if is_noise_text(current) or heading_matches(current, DESCRIPTION_HEADING_MARKERS):
                break
            if not re.fullmatch(r"\d+", current):
                parsed = clean_text(current)
                if parsed:
                    parts.append(parsed)
            index += 1
        if heading and parts:
            sections.append(f"{heading}: {' '.join(parts)}")
        continue

    return trim_noise_text(" ".join(sections)) if sections else None


def extract_section_text(text: str | None, start_markers: list[str], end_markers: list[str]) -> str | None:
    parsed = clean_text(text)
    if not parsed:
        return None

    folded = canonical_casefold(parsed)
    start_positions = [
        (folded.find(canonical_casefold(marker)), len(marker))
        for marker in start_markers
        if folded.find(canonical_casefold(marker)) >= 0
    ]
    if not start_positions:
        return None

    start_index, marker_length = min(start_positions, key=lambda item: item[0])
    content_start = start_index + marker_length
    end_index = len(parsed)
    for marker in end_markers:
        marker_index = folded.find(canonical_casefold(marker), content_start)
        if marker_index >= 0:
            end_index = min(end_index, marker_index)
    return clean_text(parsed[content_start:end_index])


def parse_requirements_text(description: str | None) -> str | None:
    requirements = extract_section_text(description, REQUIREMENTS_START_MARKERS, REQUIREMENTS_END_MARKERS)
    return requirements or clean_text(description)


def parse_title(record: dict[str, Any], soup: BeautifulSoup, json_ld: dict[str, Any]) -> str | None:
    title = first_selector_text(job_scope(soup), ["h1", "[data-testid*='job-title']", "[class*='job-title']"])
    if title:
        return title

    raw_title = json_ld.get("title")
    if isinstance(raw_title, str):
        title = clean_text(raw_title)
        if title:
            return title

    meta_title = first_meta(soup, "og:title", "twitter:title")
    if meta_title:
        return clean_text(re.split(r"\s+[|-]\s+", meta_title)[0])
    if soup.title:
        return clean_text(re.split(r"\s+[|-]\s+", soup.title.get_text(" ", strip=True))[0])
    return None


def parse_company(soup: BeautifulSoup, json_ld: dict[str, Any]) -> str | None:
    hiring_org = json_ld.get("hiringOrganization")
    if isinstance(hiring_org, dict):
        company = clean_text(hiring_org.get("name") if isinstance(hiring_org.get("name"), str) else None)
        if company:
            return company

    scoped = pruned_scope(soup)
    return first_selector_text(
        scoped,
        [
            "[data-testid*='company']",
            "[class*='company-name']",
            "[class*='company'] a",
            "a[href*='/companies/']",
            "a[href*='/company/']",
        ],
    )


def parse_location(soup: BeautifulSoup, json_ld: dict[str, Any], visible_text: str) -> str | None:
    job_location = json_ld.get("jobLocation")
    candidates = job_location if isinstance(job_location, list) else [job_location]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        address = candidate.get("address")
        addresses = address if isinstance(address, list) else [address]
        for item in addresses:
            if not isinstance(item, dict):
                continue
            for field in ("addressRegion", "addressLocality", "streetAddress"):
                value = item.get(field)
                if isinstance(value, str):
                    location = normalize_location(value)
                    if location:
                        return location

    scoped = pruned_scope(soup)
    location_text = first_selector_text(
        scoped,
        [
            "[data-testid*='location']",
            "[class*='location']",
            "[class*='address']",
            "span[class*='city']",
            "div[class*='city']",
        ],
    )
    location = normalize_location(location_text)
    if location:
        return location

    top_text = clean_text((node_text(scoped) or visible_text)[:2000])
    return normalize_location(top_text)


def hidden_salary(value: str | None) -> bool:
    return bool(value and re.search(r"\blogin\s+to\s+view\s+salary\b", value, re.IGNORECASE))


def salary_pattern(value: str | None) -> str | None:
    parsed = clean_text(value)
    if not parsed:
        return None
    patterns = [
        r"\$\s?\d[\d,.]*(?:\s?[-–]\s?\$?\s?\d[\d,.]*)?",
        r"\d[\d,.]*\s?(?:USD|VND|VNĐ)",
        r"\d[\d,.]*(?:\s?[-–]\s?\d[\d,.]*)?\s?(?:triệu|tr|m|mn|k)\b",
        r"(?:up to|upto|lên đến)\s+\$?\s?\d[\d,.]*",
    ]
    for pattern in patterns:
        match = re.search(pattern, parsed, re.IGNORECASE)
        if match:
            return clean_text(match.group(0))
    return None


def parse_salary_raw(soup: BeautifulSoup, visible_text: str) -> str | None:
    scoped = pruned_scope(soup)
    salary_nodes = scoped.select(
        "[data-testid*='salary'], [class*='salary'], [class*='compensation'], [class*='income']"
    )
    for node in salary_nodes:
        text = clean_text(node.get_text(" ", strip=True))
        if hidden_salary(text):
            return "Login to view salary"
        if salary_pattern(text):
            return text

    combined_text = " ".join(part for part in [node_text(scoped), visible_text] if part)
    if hidden_salary(combined_text):
        return "Login to view salary"

    return salary_pattern(combined_text[:1500])


def extract_structured_skills(soup: BeautifulSoup, json_ld: dict[str, Any]) -> list[str]:
    raw_skills = json_ld.get("skills")
    scoped = pruned_scope(soup)
    skills: list[str] = []

    candidates: list[Any]
    if isinstance(raw_skills, list):
        candidates = raw_skills
    else:
        candidates = [raw_skills]
    for candidate in candidates:
        if isinstance(candidate, str):
            for part in re.split(r"\s*[,;]\s*", candidate):
                append_unique(skills, part)
        elif isinstance(candidate, dict):
            name = candidate.get("name")
            if isinstance(name, str):
                append_unique(skills, name)

    for anchor in scoped.find_all("a", href=True):
        href = str(anchor["href"])
        parsed = urlparse(href)
        if "/jobs/search" not in parsed.path:
            continue
        query_keywords = parse_qs(parsed.query).get("keyword") or []
        if not query_keywords:
            continue
        for keyword in query_keywords:
            append_unique(skills, keyword)
        append_unique(skills, anchor.get_text(" ", strip=True))
    return skills


def parse_experience(text: str, infer_level: bool = False) -> tuple[str | None, int | None, int | None]:
    parsed = clean_text(text) or ""
    if re.search(r"not\s+required|no\s+experience\s+required|không\s+yêu\s+cầu\s+kinh\s+nghiệm", parsed, re.IGNORECASE):
        return "Not required", 0, 0

    comma_range = re.search(r"(\d+)\s*(?:years?|năm)\s*[,;/]\s*(\d+)\s*(?:years?|năm)", parsed, re.IGNORECASE)
    if comma_range:
        first = int(comma_range.group(1))
        second = int(comma_range.group(2))
        return comma_range.group(0), min(first, second), max(first, second)

    range_patterns = [
        r"(?:từ|from)\s*(\d+)\s*(?:đến|to|[-–])\s*(\d+)\s*(?:years?|năm)",
        r"(\d+)\s*(?:đến|to|[-–])\s*(\d+)\s*(?:years?|năm)",
    ]
    for pattern in range_patterns:
        range_match = re.search(pattern, parsed, re.IGNORECASE)
        if range_match:
            first = int(range_match.group(1))
            second = int(range_match.group(2))
            return range_match.group(0), min(first, second), max(first, second)

    single_patterns = [
        r"(?:at least|minimum(?: of)?|tối thiểu|ít nhất)\s*(\d+)\+?\s*(?:years?|năm)",
        r"(\d+)\+?\s*(?:years?|năm)",
    ]
    for pattern in single_patterns:
        single_match = re.search(pattern, parsed, re.IGNORECASE)
        if single_match:
            return single_match.group(0), int(single_match.group(1)), None

    if re.search(r"\bfresher\b|\bintern\b|mới tốt nghiệp|sắp tốt nghiệp|internship accepted", parsed, re.IGNORECASE):
        return "fresher", 0, 1
    if not infer_level:
        return None, None, None
    if re.search(r"\bsenior\b", parsed, re.IGNORECASE):
        return "senior", 4, None
    if re.search(r"\bmiddle\b|\bmid\b", parsed, re.IGNORECASE):
        return "middle", 2, 4
    if re.search(r"\bjunior\b", parsed, re.IGNORECASE):
        return "junior", 0, 2
    return None, None, None


def parse_experience_context(soup: BeautifulSoup) -> str | None:
    scoped = pruned_scope(soup)
    explicit_text = first_selector_text(
        scoped,
        [
            "[data-testid*='experience']",
            "[class*='experience']",
            "[data-testid*='level']",
            "[class*='level']",
        ],
    )
    if explicit_text:
        return explicit_text

    lines = [line.strip() for line in scoped.get_text("\n", strip=True).splitlines() if line.strip()]
    top_text = "\n".join(lines[:50])
    match = re.search(r"(?:Experience|Kinh nghiệm|Level|Cấp bậc)\s*:?\s*([^\n]{1,80})", top_text, re.IGNORECASE)
    if match:
        return match.group(0)
    return None


def parse_description(soup: BeautifulSoup, json_ld: dict[str, Any], visible_text: str) -> str | None:
    line_description = extract_line_sections(visible_text)
    if line_description:
        return line_description

    scoped = pruned_scope(soup)
    sections: list[str] = []
    for heading in scoped.find_all(["h2", "h3", "h4"]):
        heading_text = clean_text(heading.get_text(" ", strip=True))
        if is_noise_text(heading_text):
            break
        if not heading_matches(heading_text, DESCRIPTION_HEADING_MARKERS):
            continue
        content = collect_heading_content(heading)
        if content:
            sections.append(f"{heading_text}: {content}")

    if sections:
        return trim_noise_text(" ".join(sections))

    description = json_ld.get("description")
    if isinstance(description, str):
        parsed_text = BeautifulSoup(description, "html.parser").get_text("\n", strip=True)
        parsed = extract_line_sections(parsed_text) or trim_noise_text(clean_text(parsed_text))
        if parsed:
            return parsed

    fallback = trim_noise_text(node_text(scoped)) or trim_noise_text(visible_text[:8000])
    return fallback


def parse_record(record: dict[str, Any]) -> dict[str, Any]:
    soup = soup_from_record(record)
    json_ld = parse_json_ld(record)
    visible_text = record.get("visible_text") or ""
    description = parse_description(soup, json_ld, visible_text)
    requirements_text = parse_requirements_text(description)
    title = parse_title(record, soup, json_ld)
    company = parse_company(soup, json_ld)
    location = parse_location(soup, json_ld, visible_text)
    salary_raw = parse_salary_raw(soup, visible_text)
    salary_min, salary_max, salary_currency = parse_salary_values(salary_raw)

    experience_raw, experience_min, experience_max = parse_experience(parse_experience_context(soup) or "", infer_level=True)
    if experience_raw is None:
        experience_raw, experience_min, experience_max = parse_experience(requirements_text or "")
    if experience_raw is None:
        experience_raw, experience_min, experience_max = parse_experience(title or "", infer_level=True)

    text_for_skills = " ".join(part for part in [title, requirements_text or description] if part)
    structured_skills = extract_structured_skills(soup, json_ld)

    clean_record = {
        "source": record.get("source"),
        "url": record.get("url"),
        "job_id": record.get("job_id"),
        "title": title,
        "company": company,
        "location": location,
        "salary_raw": salary_raw,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": salary_currency,
        "skills": extract_skills(text_for_skills, structured_skills),
        "experience_raw": experience_raw,
        "experience_min": experience_min,
        "experience_max": experience_max,
        "description": description,
        "scraped_at": record.get("scraped_at"),
        "parse_status": "ok" if title or company or description else "low_confidence",
    }
    clean_record.update(
        trend_fields(
            title=title,
            location=location,
            salary_raw=salary_raw,
            experience_raw=experience_raw,
            experience_min=experience_min,
            description=description,
            visible_text=visible_text,
            json_ld=json_ld,
        )
    )
    return clean_record


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    output_path = ensure_parent(path)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CLEAN_FIELDNAMES)
        writer.writeheader()
        for record in records:
            csv_record = dict(record)
            csv_record["skills"] = ", ".join(record.get("skills") or [])
            csv_record["location_cities"] = ", ".join(record.get("location_cities") or [])
            writer.writerow(csv_record)


def parse_file(input_path: Path, jsonl_output: Path, csv_output: Path) -> None:
    if jsonl_output.exists():
        jsonl_output.unlink()

    records: list[dict[str, Any]] = []
    for raw_record in read_jsonl(input_path):
        clean_record = parse_record(raw_record)
        append_jsonl(jsonl_output, clean_record)
        records.append(clean_record)

    write_csv(csv_output, records)
    print(f"Parsed {len(records)} records")
    print(f"JSONL: {jsonl_output}")
    print(f"CSV: {csv_output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse raw TopDev JSONL into clean JSONL and CSV.")
    parser.add_argument("--input", type=Path, default=Path("data/raw/topdev_sample_50.jsonl"))
    parser.add_argument("--jsonl-output", type=Path, default=Path("data/processed/topdev_sample_50_clean.jsonl"))
    parser.add_argument("--csv-output", type=Path, default=Path("data/processed/topdev_sample_50_clean.csv"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parse_file(args.input, args.jsonl_output, args.csv_output)


if __name__ == "__main__":
    main()
