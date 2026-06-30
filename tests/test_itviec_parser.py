from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from parsers.itviec_parser import extract_skills, parse_experience, parse_location, parse_record, parse_salary_values


def make_soup(html: str = "<html></html>") -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


class ParseLocationTests(unittest.TestCase):
    def test_prefers_address_region_from_job_location_list(self) -> None:
        json_ld = {
            "jobLocation": [
                {
                    "@type": "Place",
                    "address": {
                        "@type": "PostalAddress",
                        "addressLocality": "Not Available",
                        "addressRegion": "Hà Nội",
                        "addressCountry": "VN",
                    },
                }
            ]
        }

        self.assertEqual(parse_location(make_soup(), json_ld, ""), "Hà Nội")

    def test_falls_back_to_address_locality_when_region_missing(self) -> None:
        json_ld = {
            "jobLocation": {
                "@type": "Place",
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": "Đà Nẵng",
                },
            }
        }

        self.assertEqual(parse_location(make_soup(), json_ld, ""), "Đà Nẵng")

    def test_uses_selector_when_json_ld_is_missing(self) -> None:
        soup = make_soup('<div class="job-location">Ha Noi</div>')

        self.assertEqual(parse_location(soup, {}, ""), "Hà Nội")

    def test_uses_visible_text_as_last_resort(self) -> None:
        visible_text = "This role is based in Ho Chi Minh with hybrid work."

        self.assertEqual(parse_location(make_soup(), {}, visible_text), "Hồ Chí Minh")

    def test_returns_none_when_no_location_signal_exists(self) -> None:
        self.assertIsNone(parse_location(make_soup(), {}, "No city listed here."))


class ParseSalaryValuesTests(unittest.TestCase):
    def test_parses_label_only_salary_as_non_numeric(self) -> None:
        self.assertEqual(parse_salary_values("You'll love it"), (None, None, None))

    def test_parses_up_to_usd_salary(self) -> None:
        self.assertEqual(parse_salary_values("Up to $3000"), (None, 3000, "USD"))

    def test_parses_million_vnd_range(self) -> None:
        self.assertEqual(parse_salary_values("12 - 55m (negotiable)"), (12_000_000, 55_000_000, "VND"))

    def test_parses_trieu_range(self) -> None:
        self.assertEqual(parse_salary_values("40 - 60 triệu"), (40_000_000, 60_000_000, "VND"))

    def test_parses_decimal_k_range(self) -> None:
        self.assertEqual(parse_salary_values("1.5k - 2k USD"), (1500, 2000, "USD"))


class ExtractSkillsTests(unittest.TestCase):
    def test_uses_structured_itviec_skill_tags_and_normalizes_aliases(self) -> None:
        skills = extract_skills("Backend service with PostgreSQL", ["NodeJS", "ReactJS", "PostgreSql", "FastAPI"])

        self.assertEqual(skills, ["Node.js", "React", "PostgreSQL", "FastAPI"])


class ParseExperienceTests(unittest.TestCase):
    def test_parses_vietnamese_tu_den_range(self) -> None:
        self.assertEqual(parse_experience("Kinh nghiệm: Từ 1 đến 3 năm làm việc thực tế"), ("Từ 1 đến 3 năm", 1, 3))

    def test_parses_at_least_years(self) -> None:
        self.assertEqual(parse_experience("At least 7 years in data engineering"), ("At least 7 years", 7, None))

    def test_does_not_infer_level_words_from_requirement_context_by_default(self) -> None:
        text = "Treat AI output as a draft from a fast, overconfident junior, not as truth."

        self.assertEqual(parse_experience(text), (None, None, None))

    def test_can_infer_level_words_for_title_fallback(self) -> None:
        self.assertEqual(parse_experience("Senior Backend Engineer", infer_level=True), ("senior", 4, None))


class ParseRecordTests(unittest.TestCase):
    def test_does_not_parse_experience_from_more_jobs_text(self) -> None:
        record = {
            "source": "itviec",
            "url": "https://itviec.com/it-jobs/software-developer-example-1234",
            "job_id": "itviec_software-developer-example-1234",
            "html": """
                <html>
                  <head><title>Software Developer | ITviec</title></head>
                  <body><h1>Software Developer</h1></body>
                </html>
            """,
            "json_ld": [
                {
                    "@context": "http://schema.org",
                    "@type": "JobPosting",
                    "title": "Software Developer",
                    "description": "<h2>Your skills and experience</h2><p>Good Python fundamentals.</p><h2>Why you'll love working here</h2><p>Salary review once per year.</p>",
                    "skills": "Python, FastAPI, NodeJS",
                    "hiringOrganization": {"name": "Example Co"},
                    "jobLocation": {
                        "address": {
                            "addressRegion": "Ho Chi Minh",
                        }
                    },
                }
            ],
            "visible_text": "Your skills and experience Good Python More jobs Senior Java Developer 5 years",
            "scraped_at": "2026-06-30T10:00:00+00:00",
        }

        parsed = parse_record(record)

        self.assertIsNone(parsed["experience_raw"])
        self.assertEqual(parsed["skills"], ["Python", "FastAPI", "Node.js"])


if __name__ == "__main__":
    unittest.main()
