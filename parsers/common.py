from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

BASE_CLEAN_FIELDNAMES = [
    "source",
    "url",
    "job_id",
    "title",
    "company",
    "location",
    "salary_raw",
    "salary_min",
    "salary_max",
    "salary_currency",
    "skills",
    "experience_raw",
    "experience_min",
    "experience_max",
    "description",
    "scraped_at",
    "parse_status",
]

TREND_FIELDNAMES = [
    "posted_raw",
    "posted_at",
    "valid_through",
    "location_cities",
    "seniority",
    "work_mode",
    "employment_type",
    "salary_period",
]

CLEAN_FIELDNAMES = BASE_CLEAN_FIELDNAMES + TREND_FIELDNAMES

CITY_PATTERNS = [
    ("Ho Chi Minh", r"\b(?:tp\.?\s*)?(?:hcm|ho chi minh|thanh pho ho chi minh|sai gon)\b"),
    ("Ha Noi", r"\b(?:ha noi|hanoi)\b"),
    ("Da Nang", r"\b(?:da nang|danang)\b"),
    ("Binh Duong", r"\bbinh duong\b"),
    ("Dong Nai", r"\bdong nai\b"),
    ("Can Tho", r"\bcan tho\b"),
    ("Hai Phong", r"\bhai phong\b"),
]


def strip_accents(value: str) -> str:
    value = value.replace("Đ", "D").replace("đ", "d")
    return "".join(
        character for character in unicodedata.normalize("NFD", value) if unicodedata.category(character) != "Mn"
    )


def fold_for_matching(value: str | None) -> str:
    return strip_accents(value or "").casefold()


def clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = re.sub(r"\s+", " ", value).strip()
    return parsed or None


def normalize_date(value: Any) -> str | None:
    parsed = clean_optional_text(value)
    if not parsed:
        return None
    return parsed


def infer_location_cities(*values: Any) -> list[str]:
    text = " ".join(value for value in values if isinstance(value, str))
    folded = fold_for_matching(text)
    cities: list[str] = []
    for city, pattern in CITY_PATTERNS:
        if re.search(pattern, folded) and city not in cities:
            cities.append(city)
    return cities


def infer_seniority(title: str | None, experience_raw: str | None, experience_min: int | None) -> str | None:
    folded = fold_for_matching(" ".join(part for part in [title, experience_raw] if part))
    if re.search(r"\b(?:intern|internship|thuc tap)\b", folded):
        return "intern"
    if re.search(r"\b(?:fresher|entry|junior|moi tot nghiep)\b", folded):
        return "junior"
    if re.search(r"\b(?:lead|principal|architect|manager|truong nhom)\b", folded):
        return "lead"
    if re.search(r"\b(?:senior|sr\.?)\b", folded):
        return "senior"
    if re.search(r"\b(?:middle|mid)\b", folded):
        return "middle"
    if experience_min is not None:
        if experience_min >= 5:
            return "senior"
        if experience_min >= 2:
            return "middle"
        return "junior"
    return None


def infer_work_mode(text: str | None) -> str | None:
    folded = fold_for_matching(text)
    if re.search(r"\b(?:remote|work from home|lam viec tu xa)\b", folded):
        return "remote"
    if re.search(r"\b(?:hybrid|linh hoat)\b", folded):
        return "hybrid"
    if re.search(r"\b(?:onsite|on-site|van phong|office)\b", folded):
        return "onsite"
    return None


def infer_employment_type(text: str | None, structured_value: Any = None) -> str | None:
    if isinstance(structured_value, list):
        structured_text = " ".join(str(value) for value in structured_value)
    elif structured_value is not None:
        structured_text = str(structured_value)
    else:
        structured_text = ""

    folded = fold_for_matching(f"{structured_text} {text or ''}")
    if re.search(r"\b(?:full time|full-time|full_time|toan thoi gian)\b", folded):
        return "full_time"
    if re.search(r"\b(?:part time|part-time|part_time|ban thoi gian)\b", folded):
        return "part_time"
    if re.search(r"\b(?:internship|intern|thuc tap)\b", folded):
        return "internship"
    if re.search(r"\b(?:contract|freelance|hop dong)\b", folded):
        return "contract"
    return None


def infer_salary_period(salary_raw: str | None, description: str | None = None) -> str | None:
    folded = fold_for_matching(f"{salary_raw or ''} {description or ''}")
    if re.search(r"\b(?:thang|month|monthly)\b", folded):
        return "month"
    if re.search(r"\b(?:nam|year|annual|annually)\b", folded):
        return "year"
    if salary_raw and re.search(r"\d", salary_raw):
        return "month"
    return None


def trend_fields(
    *,
    title: str | None,
    location: str | None,
    salary_raw: str | None,
    experience_raw: str | None,
    experience_min: int | None,
    description: str | None,
    visible_text: str | None,
    json_ld: dict[str, Any] | None = None,
) -> dict[str, Any]:
    json_ld = json_ld or {}
    combined_text = " ".join(part for part in [title, location, description, visible_text] if part)
    return {
        "posted_raw": normalize_date(json_ld.get("datePosted")),
        "posted_at": normalize_date(json_ld.get("datePosted")),
        "valid_through": normalize_date(json_ld.get("validThrough")),
        "location_cities": infer_location_cities(location, visible_text, description),
        "seniority": infer_seniority(title, experience_raw, experience_min),
        "work_mode": infer_work_mode(combined_text),
        "employment_type": infer_employment_type(combined_text, json_ld.get("employmentType")),
        "salary_period": infer_salary_period(salary_raw, description),
    }


def parse_datetime(value: Any) -> datetime | None:
    parsed = clean_optional_text(value)
    if not parsed:
        return None
    candidate = parsed.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None
