from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from parsers.common import CLEAN_FIELDNAMES, fold_for_matching, infer_location_cities, trend_fields
from parsers.itviec_parser import append_unique, clean_text, extract_skills, parse_salary_values
from scrapers.storage import append_jsonl, ensure_parent, read_jsonl

DESCRIPTION_HEADING_MARKERS = [
    "mo ta cong viec",
    "yeu cau ung vien",
    "yeu cau cong viec",
    "quyen loi",
    "dia diem lam viec",
    "thoi gian lam viec",
    "responsibilities",
    "requirements",
    "benefits",
]

REQUIREMENTS_START_MARKERS = [
    "yeu cau ung vien",
    "yeu cau cong viec",
    "requirements",
    "your skills",
    "skills",
]

REQUIREMENTS_END_MARKERS = [
    "quyen loi",
    "benefits",
    "dia diem lam viec",
    "thoi gian lam viec",
    "cach thuc ung tuyen",
]

NOISE_MARKERS = [
    "cach thuc ung tuyen",
    "ung vien nop ho so",
    "ung tuyen ngay",
    "viec lam lien quan",
    "goi y viec lam",
    "bi kip tim viec an toan",
    "bao cao tin tuyen dung",
    "tim viec theo khu vuc",
    "tu khoa tim viec lam pho bien",
    "topcv",
    "trung tam ho tro",
]

SALARY_LABELS = [
    "thoa thuan",
    "negotiable",
]

SKILL_LABELS = [
    "ky nang can co",
    "ky nang nen co",
]

SKILL_STOP_LABELS = [
    "tim viec theo khu vuc",
    "goi y viec lam",
    "thong tin chung",
    "quyen loi",
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

    stack = list(blocks) if isinstance(blocks, list) else [blocks]
    while stack:
        candidate = stack.pop(0)
        if isinstance(candidate, list):
            stack.extend(candidate)
            continue
        if not isinstance(candidate, dict):
            continue
        graph = candidate.get("@graph")
        if isinstance(graph, list):
            stack.extend(graph)
        item_type = candidate.get("@type")
        if item_type == "JobPosting" or (isinstance(item_type, list) and "JobPosting" in item_type):
            return candidate
    return {}


def job_scope(soup: BeautifulSoup) -> BeautifulSoup | Tag:
    for selector in [
        "main",
        "article",
        "[class*='job-detail']",
        "[class*='jobDetail']",
        "[id*='job-detail']",
    ]:
        node = soup.select_one(selector)
        if node:
            return node
    return soup.body or soup


def node_text(node: BeautifulSoup | Tag) -> str | None:
    return clean_text(node.get_text(" ", strip=True))


def is_noise_text(value: str | None) -> bool:
    folded = fold_for_matching((value or "")[:180])
    return any(marker in folded for marker in NOISE_MARKERS)


def pruned_scope(soup: BeautifulSoup) -> BeautifulSoup:
    scoped = BeautifulSoup(str(job_scope(soup)), "html.parser")
    for tag in scoped(["script", "style", "noscript", "svg", "footer", "nav", "aside", "form", "iframe"]):
        tag.decompose()

    for container in list(scoped.find_all(["section", "article", "aside", "div", "ul"])):
        heading = container.find(["h2", "h3", "h4", "h5"], recursive=False)
        heading_text = heading.get_text(" ", strip=True) if heading else container.get_text(" ", strip=True)[:120]
        if is_noise_text(heading_text):
            container.decompose()
    return scoped


def heading_matches(text: str | None, markers: list[str]) -> bool:
    folded = fold_for_matching(text)
    return any(marker in folded for marker in markers)


def trim_noise_text(text: str | None) -> str | None:
    parsed = clean_text(text)
    if not parsed:
        return None
    folded = fold_for_matching(parsed)
    end = len(parsed)
    for marker in NOISE_MARKERS:
        index = folded.find(marker)
        if index >= 0:
            end = min(end, index)
    return clean_text(parsed[:end])


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


def extract_labeled_section_text(
    text: str | None,
    start_markers: list[str],
    end_markers: list[str],
    max_lines: int = 80,
) -> str | None:
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if clean_text(line)]
    for index, line in enumerate(lines[:max_lines]):
        folded_line = fold_for_matching(line)
        matched_marker = next((marker for marker in start_markers if marker in folded_line), None)
        if not matched_marker:
            continue

        parts: list[str] = []
        after_marker = line[folded_line.find(matched_marker) + len(matched_marker) :].strip(" :-")
        if clean_text(after_marker):
            parts.append(after_marker)

        for current in lines[index + 1 : max_lines]:
            if is_noise_text(current) or heading_matches(current, end_markers + start_markers):
                break
            if not re.fullmatch(r"\d+", current):
                parsed = clean_text(current)
                if parsed:
                    parts.append(parsed)
        return trim_noise_text(" ".join(parts))
    return None


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


def normalize_location(value: str | None) -> str | None:
    parsed = clean_text(value)
    if not parsed:
        return None
    folded = fold_for_matching(parsed)
    if folded in {"not available", "n/a", "na"}:
        return None
    if re.search(r"\b(?:tp\.?\s*)?(?:hcm|ho chi minh|thanh pho ho chi minh|sai gon)\b", folded):
        return "Ho Chi Minh"
    if re.search(r"\b(?:ha noi|hanoi)\b", folded):
        return "Ha Noi"
    if re.search(r"\b(?:da nang|danang)\b", folded):
        return "Da Nang"
    return parsed


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
            "a[href*='/cong-ty/']",
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
                location = normalize_location(item.get(field) if isinstance(item.get(field), str) else None)
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

    line_location = extract_labeled_section_text(
        scoped.get_text("\n", strip=True),
        ["dia diem lam viec"],
        ["thoi gian lam viec", "cach thuc ung tuyen", "viec lam lien quan"],
    )
    location = normalize_location(line_location)
    if location:
        return location

    cities = infer_location_cities(visible_text, node_text(scoped))
    return cities[0] if cities else None


def salary_pattern(value: str | None) -> str | None:
    parsed = clean_text(value)
    if not parsed:
        return None
    folded = fold_for_matching(parsed)
    for label in SALARY_LABELS:
        if label in folded:
            return "Thoa thuan" if label == "thoa thuan" else "Negotiable"

    patterns = [
        r"\$\s?\d[\d,.]*(?:\s?[-–]\s?\$?\s?\d[\d,.]*)?",
        r"\d[\d,.]*\s?(?:USD|VND|VND)",
        r"\d[\d,.]*(?:\s?[-–]\s?\d[\d,.]*)?\s?(?:trieu|triệu|million|m|mn|tr|k)\b(?:\s?VND)?",
        r"(?:up to|upto|tu|from|len den)\s+\$?\s?\d[\d,.]*(?:\s?(?:USD|trieu|triệu|million|m|mn|tr|k))?",
    ]
    for pattern in patterns:
        match = re.search(pattern, parsed, re.IGNORECASE)
        if match:
            return clean_text(match.group(0))
    return None


def parse_salary_raw(soup: BeautifulSoup, json_ld: dict[str, Any], visible_text: str) -> str | None:
    base_salary = json_ld.get("baseSalary")
    if isinstance(base_salary, dict):
        value = base_salary.get("value")
        currency = base_salary.get("currency")
        if isinstance(value, dict):
            min_value = value.get("minValue")
            max_value = value.get("maxValue")
            raw_value = value.get("value")
            if min_value and max_value:
                return clean_text(f"{min_value} - {max_value} {currency or ''}")
            if raw_value:
                return clean_text(str(raw_value))

    scoped = pruned_scope(soup)
    for node in scoped.select("[data-testid*='salary'], [class*='salary'], [class*='wage'], [class*='income']"):
        text = clean_text(node.get_text(" ", strip=True))
        salary = salary_pattern(text)
        if salary:
            return text if salary not in {"Thoa thuan", "Negotiable"} else salary

    combined_text = " ".join(part for part in [node_text(scoped), visible_text] if part)
    return salary_pattern(combined_text[:2500])


def extract_structured_skills(soup: BeautifulSoup, json_ld: dict[str, Any]) -> list[str]:
    skills: list[str] = []
    raw_skills = json_ld.get("skills")
    candidates = raw_skills if isinstance(raw_skills, list) else [raw_skills]
    for candidate in candidates:
        if isinstance(candidate, str):
            for part in re.split(r"\s*[,;|]\s*", candidate):
                append_unique(skills, part)
        elif isinstance(candidate, dict):
            name = candidate.get("name")
            if isinstance(name, str):
                append_unique(skills, name)

    scoped = pruned_scope(soup)
    for node in scoped.select("[class*='skill'] a, [class*='skill'] span, a[href*='keyword='], a[href*='tag']"):
        text = clean_text(node.get_text(" ", strip=True))
        if text and 1 <= len(text) <= 40:
            append_unique(skills, text)

    skill_text = extract_labeled_section_text(scoped.get_text("\n", strip=True), SKILL_LABELS, SKILL_STOP_LABELS)
    if skill_text:
        for skill in extract_skills(skill_text):
            append_unique(skills, skill)
    return skills


def parse_experience(text: str, infer_level: bool = False) -> tuple[str | None, int | None, int | None]:
    parsed = clean_text(text) or ""
    folded = fold_for_matching(parsed)
    if re.search(r"\b(?:khong yeu cau|not required|no experience required)\b", folded):
        return "Khong yeu cau", 0, 0
    if re.search(r"\b(?:fresher|intern|thuc tap|moi tot nghiep)\b", folded):
        return "fresher", 0, 1

    under_match = re.search(r"(?:duoi|under)\s*(\d+)\s*(?:nam|years?)", folded)
    if under_match:
        max_years = int(under_match.group(1))
        return "Duoi " + under_match.group(1) + " nam", 0, max_years

    over_match = re.search(r"(?:tren|over|more than)\s*(\d+)\s*(?:nam|years?)", folded)
    if over_match:
        min_years = int(over_match.group(1))
        return "Tren " + over_match.group(1) + " nam", min_years, None

    range_patterns = [
        r"(?:tu|from)\s*(\d+)\s*(?:den|to|[-–])\s*(\d+)\s*(?:nam|years?)",
        r"(\d+)\s*(?:den|to|[-–])\s*(\d+)\s*(?:nam|years?)",
    ]
    for pattern in range_patterns:
        match = re.search(pattern, folded)
        if match:
            first = int(match.group(1))
            second = int(match.group(2))
            return match.group(0), min(first, second), max(first, second)

    single_patterns = [
        r"(?:toi thieu|it nhat|minimum(?: of)?|at least)\s*(\d+)\+?\s*(?:nam|years?)",
        r"(\d+)\+?\s*(?:nam|years?)",
    ]
    for pattern in single_patterns:
        match = re.search(pattern, folded)
        if match:
            return match.group(0), int(match.group(1)), None

    if not infer_level:
        return None, None, None
    if re.search(r"\b(?:lead|principal|architect|manager)\b", folded):
        return "lead", 5, None
    if re.search(r"\b(?:senior|sr\.?)\b", folded):
        return "senior", 4, None
    if re.search(r"\b(?:middle|mid)\b", folded):
        return "middle", 2, 4
    if re.search(r"\bjunior\b", folded):
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

    text = scoped.get_text("\n", strip=True)
    labeled = extract_labeled_section_text(text, ["kinh nghiem"], DESCRIPTION_HEADING_MARKERS + NOISE_MARKERS)
    if labeled:
        return labeled

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    top_text = "\n".join(lines[:60])
    match = re.search(
        r"(?:Kinh nghiệm|Experience|Level|Cấp bậc)\s*:?\s*([^\n]{1,100})",
        top_text,
        re.IGNORECASE,
    )
    if match:
        return match.group(0)
    return None


def parse_description(soup: BeautifulSoup, json_ld: dict[str, Any], visible_text: str) -> str | None:
    scoped = pruned_scope(soup)
    text_with_lines = scoped.get_text("\n", strip=True)
    line_description = extract_line_sections(text_with_lines) or extract_line_sections(visible_text)
    if line_description:
        return line_description

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

    return trim_noise_text(node_text(scoped)) or trim_noise_text(visible_text[:8000])


def parse_posted_raw(visible_text: str, json_ld: dict[str, Any]) -> str | None:
    date_posted = json_ld.get("datePosted")
    if isinstance(date_posted, str) and clean_text(date_posted):
        return clean_text(date_posted)

    lines = [line.strip() for line in visible_text.splitlines() if clean_text(line)]
    for line in lines[:120]:
        folded = fold_for_matching(line)
        if re.search(r"\b(?:dang|cap nhat|posted|updated)\b", folded):
            return clean_text(line)
    return None


def parse_requirements_text(description: str | None) -> str | None:
    return extract_labeled_section_text(description, REQUIREMENTS_START_MARKERS, REQUIREMENTS_END_MARKERS) or clean_text(
        description
    )


def parse_record(record: dict[str, Any]) -> dict[str, Any]:
    soup = soup_from_record(record)
    json_ld = parse_json_ld(record)
    visible_text = record.get("visible_text") or ""
    description = parse_description(soup, json_ld, visible_text)
    requirements_text = parse_requirements_text(description)
    title = parse_title(record, soup, json_ld)
    company = parse_company(soup, json_ld)
    location = parse_location(soup, json_ld, visible_text)
    salary_raw = parse_salary_raw(soup, json_ld, visible_text)
    salary_min, salary_max, salary_currency = parse_salary_values(salary_raw)

    experience_raw, experience_min, experience_max = parse_experience(parse_experience_context(soup) or "")
    if experience_raw is None:
        experience_raw, experience_min, experience_max = parse_experience(requirements_text or "")
    if experience_raw is None:
        experience_raw, experience_min, experience_max = parse_experience(title or "", infer_level=True)

    structured_skills = extract_structured_skills(soup, json_ld)
    skill_text = " ".join(part for part in [title, requirements_text or description, node_text(pruned_scope(soup))] if part)

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
        "skills": extract_skills(skill_text, structured_skills),
        "experience_raw": experience_raw,
        "experience_min": experience_min,
        "experience_max": experience_max,
        "description": description,
        "scraped_at": record.get("scraped_at"),
        "parse_status": "ok" if title or company or description else "low_confidence",
    }
    extra_fields = trend_fields(
        title=title,
        location=location,
        salary_raw=salary_raw,
        experience_raw=experience_raw,
        experience_min=experience_min,
        description=description,
        visible_text=visible_text,
        json_ld=json_ld,
    )
    extra_fields["posted_raw"] = extra_fields["posted_raw"] or parse_posted_raw(visible_text, json_ld)
    clean_record.update(extra_fields)
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
    parser = argparse.ArgumentParser(description="Parse raw TopCV JSONL into clean JSONL and CSV.")
    parser.add_argument("--input", type=Path, default=Path("data/raw/topcv_sample_50.jsonl"))
    parser.add_argument("--jsonl-output", type=Path, default=Path("data/processed/topcv_sample_50_clean.jsonl"))
    parser.add_argument("--csv-output", type=Path, default=Path("data/processed/topcv_sample_50_clean.csv"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parse_file(args.input, args.jsonl_output, args.csv_output)


if __name__ == "__main__":
    main()
