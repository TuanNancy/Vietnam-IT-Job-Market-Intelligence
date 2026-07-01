from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from parsers.common import parse_datetime
from scrapers.storage import ensure_parent, read_jsonl

DEMAND_REPORT = "demand_by_week_skill.csv"
SALARY_REPORT = "salary_by_week_skill.csv"
EXPERIENCE_REPORT = "experience_by_week_skill.csv"
QUALITY_REPORT = "source_quality_by_run.csv"


def default_inputs() -> list[Path]:
    return sorted(Path("data/processed").glob("*_clean.jsonl"))


def load_records(paths: Iterable[Path]) -> list[tuple[Path, dict[str, Any]]]:
    records: list[tuple[Path, dict[str, Any]]] = []
    for path in paths:
        for record in read_jsonl(path):
            records.append((path, record))
    return records


def week_start(record: dict[str, Any]) -> str | None:
    parsed = parse_datetime(record.get("posted_at")) or parse_datetime(record.get("scraped_at"))
    if parsed is None:
        return None
    start = parsed.date() - timedelta(days=parsed.weekday())
    return start.isoformat()


def skill_values(record: dict[str, Any]) -> list[str]:
    skills = record.get("skills")
    if isinstance(skills, list):
        parsed = [str(skill).strip() for skill in skills if str(skill).strip()]
    elif isinstance(skills, str):
        parsed = [skill.strip() for skill in skills.split(",") if skill.strip()]
    else:
        parsed = []
    return parsed or ["(unknown)"]


def numeric_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def salary_midpoint(record: dict[str, Any]) -> float | None:
    salary_min = numeric_value(record.get("salary_min"))
    salary_max = numeric_value(record.get("salary_max"))
    if salary_min is not None and salary_max is not None:
        return (salary_min + salary_max) / 2
    return salary_min if salary_min is not None else salary_max


def build_demand_rows(records: list[tuple[Path, dict[str, Any]]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for _, record in records:
        week = week_start(record)
        if not week:
            continue
        source = str(record.get("source") or "unknown")
        url = str(record.get("url") or record.get("job_id") or "")
        for skill in skill_values(record):
            groups[(week, source, skill)].add(url)

    rows = [
        {
            "week_start": week,
            "source": source,
            "skill": skill,
            "job_count": len(urls),
        }
        for (week, source, skill), urls in groups.items()
    ]
    return sorted(rows, key=lambda row: (row["week_start"], row["source"], row["skill"]))


def build_salary_rows(records: list[tuple[Path, dict[str, Any]]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    for _, record in records:
        week = week_start(record)
        midpoint = salary_midpoint(record)
        if not week or midpoint is None:
            continue
        source = str(record.get("source") or "unknown")
        currency = str(record.get("salary_currency") or "unknown")
        for skill in skill_values(record):
            groups[(week, source, skill, currency)].append(midpoint)

    rows: list[dict[str, Any]] = []
    for (week, source, skill, currency), values in groups.items():
        rows.append(
            {
                "week_start": week,
                "source": source,
                "skill": skill,
                "salary_currency": currency,
                "salary_count": len(values),
                "salary_midpoint_median": int(round(median(values))),
                "salary_midpoint_min": int(round(min(values))),
                "salary_midpoint_max": int(round(max(values))),
            }
        )
    return sorted(rows, key=lambda row: (row["week_start"], row["source"], row["skill"], row["salary_currency"]))


def build_experience_rows(records: list[tuple[Path, dict[str, Any]]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for _, record in records:
        week = week_start(record)
        experience_min = numeric_value(record.get("experience_min"))
        if not week or experience_min is None:
            continue
        source = str(record.get("source") or "unknown")
        for skill in skill_values(record):
            groups[(week, source, skill)].append(experience_min)

    rows: list[dict[str, Any]] = []
    for (week, source, skill), values in groups.items():
        rows.append(
            {
                "week_start": week,
                "source": source,
                "skill": skill,
                "experience_count": len(values),
                "experience_min_median": median(values),
                "experience_min_min": min(values),
                "experience_min_max": max(values),
            }
        )
    return sorted(rows, key=lambda row: (row["week_start"], row["source"], row["skill"]))


def fill_rate(records: list[dict[str, Any]], field: str) -> float:
    if not records:
        return 0.0
    filled = sum(1 for record in records if record.get(field) not in (None, "", []))
    return round(filled / len(records), 4)


def build_quality_rows(records: list[tuple[Path, dict[str, Any]]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for path, record in records:
        source = str(record.get("source") or "unknown")
        groups[(path.name, source)].append(record)

    rows: list[dict[str, Any]] = []
    for (input_file, source), group_records in groups.items():
        salary_numeric = sum(
            1
            for record in group_records
            if record.get("salary_min") not in (None, "") or record.get("salary_max") not in (None, "")
        )
        parse_ok = sum(1 for record in group_records if record.get("parse_status") == "ok")
        rows.append(
            {
                "input_file": input_file,
                "source": source,
                "record_count": len(group_records),
                "parse_ok_rate": round(parse_ok / len(group_records), 4),
                "title_fill_rate": fill_rate(group_records, "title"),
                "company_fill_rate": fill_rate(group_records, "company"),
                "location_fill_rate": fill_rate(group_records, "location"),
                "salary_raw_fill_rate": fill_rate(group_records, "salary_raw"),
                "salary_numeric_fill_rate": round(salary_numeric / len(group_records), 4),
                "experience_fill_rate": fill_rate(group_records, "experience_raw"),
                "skills_fill_rate": fill_rate(group_records, "skills"),
                "description_fill_rate": fill_rate(group_records, "description"),
            }
        )
    return sorted(rows, key=lambda row: (row["input_file"], row["source"]))


def write_report(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    output_path = ensure_parent(path)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_reports(input_paths: list[Path], output_dir: Path) -> None:
    records = load_records(input_paths)
    demand_rows = build_demand_rows(records)
    salary_rows = build_salary_rows(records)
    experience_rows = build_experience_rows(records)
    quality_rows = build_quality_rows(records)

    write_report(output_dir / DEMAND_REPORT, demand_rows, ["week_start", "source", "skill", "job_count"])
    write_report(
        output_dir / SALARY_REPORT,
        salary_rows,
        [
            "week_start",
            "source",
            "skill",
            "salary_currency",
            "salary_count",
            "salary_midpoint_median",
            "salary_midpoint_min",
            "salary_midpoint_max",
        ],
    )
    write_report(
        output_dir / EXPERIENCE_REPORT,
        experience_rows,
        [
            "week_start",
            "source",
            "skill",
            "experience_count",
            "experience_min_median",
            "experience_min_min",
            "experience_min_max",
        ],
    )
    write_report(
        output_dir / QUALITY_REPORT,
        quality_rows,
        [
            "input_file",
            "source",
            "record_count",
            "parse_ok_rate",
            "title_fill_rate",
            "company_fill_rate",
            "location_fill_rate",
            "salary_raw_fill_rate",
            "salary_numeric_fill_rate",
            "experience_fill_rate",
            "skills_fill_rate",
            "description_fill_rate",
        ],
    )
    print(f"Loaded {len(records)} records from {len(input_paths)} input files")
    print(f"Reports: {output_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build weekly demand, salary, experience, and quality reports.")
    parser.add_argument("--inputs", nargs="*", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("data/reports"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_paths = args.inputs if args.inputs else default_inputs()
    write_reports(input_paths=input_paths, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
