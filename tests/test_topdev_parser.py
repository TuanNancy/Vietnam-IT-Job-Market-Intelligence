from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from parsers.topdev_parser import normalize_location, parse_experience, parse_record, parse_salary_values


def make_record(html: str, visible_text: str = "") -> dict[str, object]:
    return {
        "source": "topdev",
        "url": "https://topdev.vn/detail-jobs/senior-backend-engineer-12345",
        "job_id": "topdev_senior-backend-engineer-12345",
        "html": html,
        "json_ld": [],
        "visible_text": visible_text,
        "scraped_at": "2026-07-01T00:00:00+00:00",
    }


class SalaryTests(unittest.TestCase):
    def test_hidden_salary_is_preserved_without_numeric_values(self) -> None:
        record = make_record(
            """
            <html><body><main>
              <h1>Backend Engineer</h1>
              <a class="company-name" href="/companies/example">Example Co</a>
              <div class="salary">Login to view salary</div>
              <section><h2>Benefits</h2><p>Lương 8 - 12 triệu/tháng after probation.</p></section>
            </main></body></html>
            """
        )

        parsed = parse_record(record)

        self.assertEqual(parsed["salary_raw"], "Login to view salary")
        self.assertIsNone(parsed["salary_min"])
        self.assertIsNone(parsed["salary_max"])
        self.assertIsNone(parsed["salary_currency"])

    def test_parses_visible_vnd_salary_area(self) -> None:
        record = make_record(
            """
            <html><body><main>
              <h1>Frontend Engineer</h1>
              <a class="company-name" href="/companies/example">Example Co</a>
              <div class="salary">Mức lương: 11 - 18 triệu</div>
            </main></body></html>
            """
        )

        parsed = parse_record(record)

        self.assertEqual(parsed["salary_raw"], "Mức lương: 11 - 18 triệu")
        self.assertEqual(parse_salary_values(parsed["salary_raw"]), (11_000_000, 18_000_000, "VND"))


class LocationTests(unittest.TestCase):
    def test_normalizes_common_locations_and_district_prefixes(self) -> None:
        self.assertEqual(normalize_location("Hồ Chí Minh"), "Hồ Chí Minh")
        self.assertEqual(normalize_location("Quận 1, Ho Chi Minh"), "Hồ Chí Minh")
        self.assertEqual(normalize_location("Cầu Giấy, Hà Nội"), "Hà Nội")
        self.assertEqual(normalize_location("Đà Nẵng"), "Đà Nẵng")


class SkillTests(unittest.TestCase):
    def test_extracts_skill_tags_and_normalizes_aliases(self) -> None:
        record = make_record(
            """
            <html><body><main>
              <h1>NodeJS ReactJS Developer</h1>
              <a class="company-name" href="/companies/example">Example Co</a>
              <a href="/jobs/search?keyword=NodeJS">NodeJS</a>
              <a href="/jobs/search?keyword=ReactJS">ReactJS</a>
              <a href="/jobs/search?keyword=Golang">Golang</a>
              <section><h2>Your skills & qualifications</h2><p>Build APIs.</p></section>
            </main></body></html>
            """
        )

        parsed = parse_record(record)

        self.assertEqual(parsed["skills"], ["Node.js", "React", "Go"])


class ExperienceTests(unittest.TestCase):
    def test_parses_not_required(self) -> None:
        self.assertEqual(parse_experience("Not required"), ("Not required", 0, 0))

    def test_parses_fresher(self) -> None:
        self.assertEqual(parse_experience("Fresher or Intern accepted"), ("fresher", 0, 1))

    def test_parses_single_years(self) -> None:
        self.assertEqual(parse_experience("3 years in backend development"), ("3 years", 3, None))

    def test_parses_comma_separated_year_range(self) -> None:
        self.assertEqual(parse_experience("2 years, 5 years"), ("2 years, 5 years", 2, 5))

    def test_title_level_senior_fallback(self) -> None:
        record = make_record(
            """
            <html><body><main>
              <h1>Senior Backend Engineer</h1>
              <a class="company-name" href="/companies/example">Example Co</a>
              <section><h2>Your role & responsibilities</h2><p>Build services.</p></section>
            </main></body></html>
            """
        )

        parsed = parse_record(record)

        self.assertEqual(parsed["experience_raw"], "senior")
        self.assertEqual(parsed["experience_min"], 4)
        self.assertIsNone(parsed["experience_max"])


class NoiseAvoidanceTests(unittest.TestCase):
    def test_avoids_other_jobs_company_cards_footer_and_blog_noise(self) -> None:
        record = make_record(
            """
            <html><body>
              <main>
                <h1>Backend Engineer</h1>
                <a class="company-name" href="/companies/example">Example Co</a>
                <div class="location">District 3, Ho Chi Minh</div>
                <div class="salary">Login to view salary</div>
                <a href="/jobs/search?keyword=Python">Python</a>
                <section>
                  <h2>Your skills & qualifications</h2>
                  <p>Good SQL knowledge.</p>
                </section>
                <section>
                  <h2>Your role & responsibilities</h2>
                  <p>Build backend APIs.</p>
                </section>
                <section>
                  <h2>Other jobs at this company</h2>
                  <a href="/jobs/search?keyword=Java">Java</a>
                  <p>Senior Java Developer 5 years</p>
                </section>
                <section>
                  <h2>TopDev Blog</h2>
                  <p>React hiring trends.</p>
                </section>
              </main>
              <footer>NodeJS footer links</footer>
            </body></html>
            """
        )

        parsed = parse_record(record)

        self.assertEqual(parsed["location"], "Hồ Chí Minh")
        self.assertEqual(parsed["skills"], ["Python", "SQL"])
        self.assertIsNone(parsed["experience_raw"])
        self.assertIn("Build backend APIs", parsed["description"])
        self.assertNotIn("Other jobs", parsed["description"])
        self.assertNotIn("Senior Java", parsed["description"])
        self.assertNotIn("React hiring trends", parsed["description"])
        self.assertEqual(parsed["parse_status"], "ok")


if __name__ == "__main__":
    unittest.main()
