from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from parsers.trend_reports import (
    DEMAND_REPORT,
    QUALITY_REPORT,
    SALARY_REPORT,
    build_demand_rows,
    build_quality_rows,
    build_salary_rows,
    load_records,
    write_reports,
)


class TrendReportTests(unittest.TestCase):
    def test_builds_weekly_demand_salary_and_quality_rows(self) -> None:
        path = Path("topcv_clean.jsonl")
        records = [
            (
                path,
                {
                    "source": "topcv",
                    "url": "https://www.topcv.vn/viec-lam/a/1.html",
                    "title": "Backend Python Developer",
                    "company": "Example Co",
                    "location": "Ha Noi",
                    "salary_min": 10_000_000,
                    "salary_max": 20_000_000,
                    "salary_currency": "VND",
                    "skills": ["Python", "SQL"],
                    "experience_raw": "2 nam",
                    "experience_min": 2,
                    "description": "Build APIs",
                    "posted_at": "2026-07-01",
                    "scraped_at": "2026-07-01T00:00:00+00:00",
                    "parse_status": "ok",
                },
            ),
            (
                path,
                {
                    "source": "topcv",
                    "url": "https://www.topcv.vn/viec-lam/b/2.html",
                    "title": "Frontend React Developer",
                    "company": "Example Co",
                    "location": "Ho Chi Minh",
                    "salary_min": 20_000_000,
                    "salary_max": 30_000_000,
                    "salary_currency": "VND",
                    "skills": ["Python"],
                    "experience_raw": "3 nam",
                    "experience_min": 3,
                    "description": "Build UI",
                    "posted_at": "2026-07-02",
                    "scraped_at": "2026-07-02T00:00:00+00:00",
                    "parse_status": "ok",
                },
            ),
        ]

        demand_rows = build_demand_rows(records)
        salary_rows = build_salary_rows(records)
        quality_rows = build_quality_rows(records)

        python_demand = [row for row in demand_rows if row["skill"] == "Python"][0]
        python_salary = [row for row in salary_rows if row["skill"] == "Python"][0]
        quality = quality_rows[0]

        self.assertEqual(python_demand["week_start"], "2026-06-29")
        self.assertEqual(python_demand["job_count"], 2)
        self.assertEqual(python_salary["salary_count"], 2)
        self.assertEqual(python_salary["salary_midpoint_median"], 20_000_000)
        self.assertEqual(quality["record_count"], 2)
        self.assertEqual(quality["parse_ok_rate"], 1.0)
        self.assertEqual(quality["salary_numeric_fill_rate"], 1.0)

    def test_writes_report_files_from_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            input_path = base / "sample_clean.jsonl"
            output_dir = base / "reports"
            rows = [
                {
                    "source": "itviec",
                    "url": "https://itviec.com/it-jobs/a-1234",
                    "skills": ["Python"],
                    "salary_min": 1000,
                    "salary_max": 2000,
                    "salary_currency": "USD",
                    "experience_min": 2,
                    "posted_at": "2026-07-01",
                    "scraped_at": "2026-07-01T00:00:00+00:00",
                    "parse_status": "ok",
                }
            ]
            with input_path.open("w", encoding="utf-8") as file:
                for row in rows:
                    json.dump(row, file)
                    file.write("\n")

            with redirect_stdout(StringIO()):
                write_reports([input_path], output_dir)
            loaded = load_records([input_path])

            self.assertEqual(len(loaded), 1)
            self.assertTrue((output_dir / DEMAND_REPORT).exists())
            self.assertTrue((output_dir / SALARY_REPORT).exists())
            self.assertTrue((output_dir / QUALITY_REPORT).exists())


if __name__ == "__main__":
    unittest.main()
