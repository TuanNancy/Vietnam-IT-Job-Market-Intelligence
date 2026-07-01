from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from parsers.common import CLEAN_FIELDNAMES, trend_fields
from scrapers.storage import append_jsonl, ensure_parent, read_jsonl

SKILLS = [
    "Python",
    "Java",
    "JavaScript",
    "TypeScript",
    "React",
    "Vue",
    "Angular",
    "Node.js",
    "NodeJS",
    "PHP",
    "Laravel",
    "Go",
    "Golang",
    ".NET",
    "C#",
    "AWS",
    "Azure",
    "GCP",
    "Docker",
    "Kubernetes",
    "SQL",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
    "DevOps",
    "QA",
    "Tester",
    "iOS",
    "Android",
    "Flutter",
    "Kotlin",
    "Swift",
]

SKILL_NORMALIZATION = {
    "NodeJS": "Node.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "ReactJS": "React",
    "reactjs": "React",
    "react.js": "React",
    "Golang": "Go",
    "golang": "Go",
    "PostgreSql": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "Google Cloud": "GCP",
    "google cloud": "GCP",
    "K8s": "Kubernetes",
    "k8s": "Kubernetes",
    "dotnet": ".NET",
    "csharp": "C#",
    "c sharp": "C#",
}

LOCATION_CANONICAL_MAP = {
    "ho chi minh": "Hồ Chí Minh",
    "hồ chí minh": "Hồ Chí Minh",
    "ha noi": "Hà Nội",
    "hà nội": "Hà Nội",
    "da nang": "Đà Nẵng",
    "đà nẵng": "Đà Nẵng",
}

SALARY_LABEL_MAP = {
    "you'll love it": "You'll love it",
    "thỏa thuận": "Thỏa thuận",
}

REQUIREMENTS_START_MARKERS = [
    "Your skills and experience",
    "Skills and experience",
    "Yêu cầu công việc",
    "Yêu cầu ứng viên",
    "Requirements",
]

REQUIREMENTS_END_MARKERS = [
    "Why you'll love working here",
    "Why you will love working here",
    "Phúc lợi",
    "Benefits",
    "More jobs",
    "Thông tin công ty",
]

MILLION_UNITS = {"m", "mn", "million", "triệu", "trieu", "tr"}
THOUSAND_UNITS = {"k"}


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def soup_from_record(record: dict[str, Any]) -> BeautifulSoup:
    return BeautifulSoup(record.get("html") or "", "html.parser")


def first_meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return clean_text(str(tag["content"]))
    return None


def first_selector_text(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = clean_text(node.get_text(" ", strip=True))
            if text:
                return text
    return None


def normalize_location(value: str | None) -> str | None:
    parsed = clean_text(value)
    if not parsed:
        return None

    lowered = parsed.casefold()
    if lowered in {"not available", "n/a", "na"}:
        return None

    return LOCATION_CANONICAL_MAP.get(lowered, parsed)


def canonical_casefold(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def normalize_skill_name(value: str | None) -> str | None:
    parsed = clean_text(value)
    if not parsed:
        return None

    normalized = unicodedata.normalize("NFC", parsed).strip(" ,")
    return SKILL_NORMALIZATION.get(normalized) or SKILL_NORMALIZATION.get(canonical_casefold(normalized)) or normalized


def append_unique(values: list[str], value: str | None) -> None:
    normalized = normalize_skill_name(value)
    if not normalized:
        return
    if all(canonical_casefold(existing) != canonical_casefold(normalized) for existing in values):
        values.append(normalized)


def normalize_salary_text(value: str | None) -> str | None:
    parsed = clean_text(value)
    if not parsed:
        return None

    normalized = unicodedata.normalize("NFC", parsed)
    return SALARY_LABEL_MAP.get(canonical_casefold(normalized), normalized)


def salary_unit_multiplier(unit: str | None) -> int | None:
    if not unit:
        return None

    normalized_unit = canonical_casefold(unit)
    if normalized_unit in MILLION_UNITS:
        return 1_000_000
    if normalized_unit in THOUSAND_UNITS:
        return 1_000
    return None


def parse_salary_number(number_text: str, allow_decimal: bool) -> float | None:
    normalized = number_text.replace(" ", "")
    if not normalized:
        return None

    if allow_decimal:
        if normalized.count(",") == 1 and "." not in normalized:
            whole, fractional = normalized.split(",")
            if fractional.isdigit() and len(fractional) <= 2:
                return float(f"{whole}.{fractional}")
        if normalized.count(".") == 1 and "," not in normalized:
            whole, fractional = normalized.split(".")
            if fractional.isdigit() and len(fractional) <= 2:
                return float(normalized)

    compact = normalized.replace(",", "").replace(".", "")
    if not compact.isdigit():
        return None
    return float(compact)


def infer_salary_currency(salary_raw: str) -> str | None:
    normalized = canonical_casefold(salary_raw)
    if re.search(r"\d(?:[\d.,]*)(?:\s*)(?:triệu|trieu|tr|m|mn|million)\b", normalized):
        return "VND"
    if "vnđ" in normalized or "vnd" in normalized:
        return "VND"
    if "$" in salary_raw or "usd" in normalized:
        return "USD"
    return None


def extract_location_from_address(address: dict[str, Any]) -> str | None:
    for field in ("addressRegion", "addressLocality"):
        value = address.get(field)
        if isinstance(value, str):
            normalized = normalize_location(value)
            if normalized:
                return normalized
    return None


def extract_location_from_job_location(job_location: Any) -> str | None:
    candidates = job_location if isinstance(job_location, list) else [job_location]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        address = candidate.get("address")
        if isinstance(address, dict):
            normalized = extract_location_from_address(address)
            if normalized:
                return normalized

        if isinstance(address, list):
            for item in address:
                if not isinstance(item, dict):
                    continue
                normalized = extract_location_from_address(item)
                if normalized:
                    return normalized
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


def extract_structured_skills(json_ld: dict[str, Any]) -> list[str]:
    raw_skills = json_ld.get("skills")
    if not raw_skills:
        return []

    candidates: list[Any]
    if isinstance(raw_skills, list):
        candidates = raw_skills
    else:
        candidates = [raw_skills]

    skills: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, str):
            for part in re.split(r"\s*[,;]\s*", candidate):
                append_unique(skills, part)
        elif isinstance(candidate, dict):
            name = candidate.get("name")
            if isinstance(name, str):
                append_unique(skills, name)
    return skills


def extract_section_text(text: str | None, start_markers: list[str], end_markers: list[str]) -> str | None:
    parsed = clean_text(text)
    if not parsed:
        return None

    lowered = canonical_casefold(parsed)
    start_positions = [
        (lowered.find(canonical_casefold(marker)), len(marker))
        for marker in start_markers
        if lowered.find(canonical_casefold(marker)) >= 0
    ]
    if not start_positions:
        return None

    start_index, marker_length = min(start_positions, key=lambda item: item[0])
    content_start = start_index + marker_length
    end_index = len(parsed)
    for marker in end_markers:
        marker_index = lowered.find(canonical_casefold(marker), content_start)
        if marker_index >= 0:
            end_index = min(end_index, marker_index)
    return clean_text(parsed[content_start:end_index])


def parse_requirements_text(description: str | None, visible_text: str | None) -> str | None:
    for text in (description, visible_text):
        requirements_text = extract_section_text(text, REQUIREMENTS_START_MARKERS, REQUIREMENTS_END_MARKERS)
        if requirements_text:
            return requirements_text
    return clean_text(description)


def parse_title(record: dict[str, Any], soup: BeautifulSoup, json_ld: dict[str, Any]) -> str | None:
    title = first_selector_text(soup, ["h1", "[data-testid*='job-title']", ".job-title"])
    if title:
        return title

    title = clean_text(json_ld.get("title") if isinstance(json_ld.get("title"), str) else None)
    if title:
        return title

    meta_title = first_meta(soup, "og:title", "twitter:title")
    if meta_title:
        return re.split(r"\s+[-|]\s+", meta_title)[0].strip()
    return None


def parse_company(soup: BeautifulSoup, json_ld: dict[str, Any]) -> str | None:
    hiring_org = json_ld.get("hiringOrganization")
    if isinstance(hiring_org, dict):
        company = clean_text(hiring_org.get("name") if isinstance(hiring_org.get("name"), str) else None)
        if company:
            return company

    return first_selector_text(
        soup,
        [
            "[data-testid*='company']",
            ".company-name",
            "a[href*='/companies/']",
            "a[href*='/company/']",
        ],
    )


def parse_location(soup: BeautifulSoup, json_ld: dict[str, Any], visible_text: str) -> str | None:
    normalized_location = extract_location_from_job_location(json_ld.get("jobLocation"))
    if normalized_location:
        return normalized_location

    location_text = first_selector_text(
        soup,
        [
            "[data-testid*='location']",
            ".job-location",
            "span[class*='location']",
            "div[class*='location']",
        ],
    )
    if location_text:
        normalized = normalize_location(location_text)
        if normalized:
            return normalized

    lowered_visible_text = visible_text.casefold()
    for variant, canonical in LOCATION_CANONICAL_MAP.items():
        if variant in lowered_visible_text:
            return canonical
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
                return normalize_salary_text(f"{min_value} - {max_value} {currency or ''}")
            if raw_value:
                return normalize_salary_text(str(raw_value))
        raw = normalize_salary_text(json.dumps(base_salary, ensure_ascii=False))
        if raw:
            return raw

    salary_text = first_selector_text(
        soup,
        [
            "[data-testid*='salary']",
            ".salary",
            "span[class*='salary']",
            "div[class*='salary']",
        ],
    )
    if salary_text:
        return normalize_salary_text(salary_text)

    patterns = [
        r"\$\s?\d[\d,.]*(?:\s?[-–]\s?\$?\s?\d[\d,.]*)?",
        r"\d[\d,.]*\s?(?:USD|VND|VNĐ)",
        r"\d[\d,.]*(?:\s?[-–]\s?\d[\d,.]*)?\s?(?:triệu|tr|m|mn|k)\b(?:\s*\((?:negotiable|thỏa thuận)\))?",
        r"(?:up to|upto|lên đến)\s+\$?\s?\d[\d,.]*",
        r"(?:negotiable|thỏa thuận)",
    ]
    for pattern in patterns:
        match = re.search(pattern, visible_text, re.IGNORECASE)
        if match:
            return normalize_salary_text(match.group(0))
    return None


def parse_salary_values(salary_raw: str | None) -> tuple[int | None, int | None, str | None]:
    if not salary_raw:
        return None, None, None

    currency = infer_salary_currency(salary_raw)
    tokens = re.findall(r"(\d[\d,.]*)(?:\s*(k|m|mn|million|triệu|trieu|tr))?", salary_raw, re.IGNORECASE)
    if not tokens:
        return None, None, currency

    explicit_multipliers = [salary_unit_multiplier(unit) for _, unit in tokens if salary_unit_multiplier(unit) is not None]
    default_multiplier = explicit_multipliers[0] if explicit_multipliers else 1

    numbers: list[int] = []
    for number_text, unit in tokens:
        multiplier = salary_unit_multiplier(unit) or default_multiplier
        parsed_number = parse_salary_number(number_text, allow_decimal=multiplier != 1)
        if parsed_number is None:
            continue
        numbers.append(int(round(parsed_number * multiplier)))

    if not numbers:
        return None, None, currency
    if len(numbers) == 1:
        if re.search(r"up to|upto|lên đến", salary_raw, re.IGNORECASE):
            return None, numbers[0], currency
        return numbers[0], None, currency
    return min(numbers[0], numbers[1]), max(numbers[0], numbers[1]), currency


def extract_skills(text: str, structured_skills: list[str] | None = None) -> list[str]:
    found: list[str] = []
    for skill in structured_skills or []:
        append_unique(found, skill)

    for skill in SKILLS:
        pattern = re.escape(skill).replace("\\.", r"[.]?")
        if re.search(rf"(?<![A-Za-z0-9+#]){pattern}(?![A-Za-z0-9+#])", text, re.IGNORECASE):
            append_unique(found, skill)
    return found


def parse_experience(text: str, infer_level: bool = False) -> tuple[str | None, int | None, int | None]:
    range_patterns = [
        r"(?:từ|from)\s*(\d+)\s*(?:đến|to|[-–])\s*(\d+)\s*(?:years?|năm)",
        r"(\d+)\s*(?:đến|to|[-–])\s*(\d+)\s*(?:years?|năm)",
    ]
    for pattern in range_patterns:
        range_match = re.search(pattern, text, re.IGNORECASE)
        if range_match:
            return range_match.group(0), int(range_match.group(1)), int(range_match.group(2))

    single_patterns = [
        r"(?:at least|minimum(?: of)?|tối thiểu|ít nhất)\s*(\d+)\+?\s*(?:years?|năm)",
        r"(\d+)\+?\s*(?:years?|năm)",
    ]
    for pattern in single_patterns:
        single_match = re.search(pattern, text, re.IGNORECASE)
        if single_match:
            return single_match.group(0), int(single_match.group(1)), None

    if re.search(r"\bfresher\b|\bintern\b|mới tốt nghiệp|sắp tốt nghiệp|internship accepted", text, re.IGNORECASE):
        return "fresher", 0, 1
    if not infer_level:
        return None, None, None
    if re.search(r"\bsenior\b", text, re.IGNORECASE):
        return "senior", 4, None
    if re.search(r"\bjunior\b", text, re.IGNORECASE):
        return "junior", 0, 2
    return None, None, None


def parse_description(soup: BeautifulSoup, json_ld: dict[str, Any], visible_text: str) -> str | None:
    description = json_ld.get("description")
    if isinstance(description, str):
        parsed = clean_text(BeautifulSoup(description, "html.parser").get_text(" ", strip=True))
        if parsed:
            return parsed

    description_text = first_selector_text(
        soup,
        [
            "[data-testid*='description']",
            ".job-description",
            "section[class*='description']",
            "div[class*='description']",
            "main",
        ],
    )
    return description_text or clean_text(visible_text[:8000])


def parse_record(record: dict[str, Any]) -> dict[str, Any]:
    soup = soup_from_record(record)
    json_ld = parse_json_ld(record)
    visible_text = record.get("visible_text") or ""
    description = parse_description(soup, json_ld, visible_text)
    requirements_text = parse_requirements_text(description, visible_text)
    title = parse_title(record, soup, json_ld)
    company = parse_company(soup, json_ld)
    location = parse_location(soup, json_ld, visible_text)
    salary_raw = parse_salary_raw(soup, json_ld, visible_text)
    salary_min, salary_max, salary_currency = parse_salary_values(salary_raw)
    experience_raw, experience_min, experience_max = parse_experience(requirements_text or "")
    if experience_raw is None:
        experience_raw, experience_min, experience_max = parse_experience(title or "", infer_level=True)

    text_for_skills = " ".join(part for part in [title, requirements_text or description] if part)
    structured_skills = extract_structured_skills(json_ld)

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
    parser = argparse.ArgumentParser(description="Parse raw ITviec JSONL into clean JSONL and CSV.")
    parser.add_argument("--input", type=Path, default=Path("data/raw/itviec_sample_50.jsonl"))
    parser.add_argument("--jsonl-output", type=Path, default=Path("data/processed/itviec_sample_50_clean.jsonl"))
    parser.add_argument("--csv-output", type=Path, default=Path("data/processed/itviec_sample_50_clean.csv"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parse_file(args.input, args.jsonl_output, args.csv_output)


if __name__ == "__main__":
    main()
