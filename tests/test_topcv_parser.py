from __future__ import annotations

import unittest

from parsers.topcv_parser import parse_experience, parse_record, parse_salary_values


def make_record(html: str, visible_text: str = "") -> dict[str, object]:
    return {
        "source": "topcv",
        "url": "https://www.topcv.vn/viec-lam/back-end-developer/2084326.html",
        "job_id": "topcv_2084326",
        "html": html,
        "json_ld": [],
        "visible_text": visible_text,
        "scraped_at": "2026-07-01T00:00:00+00:00",
    }


class SalaryTests(unittest.TestCase):
    def test_parses_visible_vnd_salary(self) -> None:
        record = make_record(
            """
            <html><body><main>
              <h1>Backend Python Developer</h1>
              <a class="company-name" href="/cong-ty/example">Example Co</a>
              <div class="salary">Muc luong: 15 - 20 trieu</div>
              <div class="location">Ha Noi</div>
              <section><h2>Yeu cau ung vien</h2><p>Tu 2 den 4 nam kinh nghiem Python SQL.</p></section>
              <section><h2>Mo ta cong viec</h2><p>Build APIs.</p></section>
            </main></body></html>
            """
        )

        parsed = parse_record(record)

        self.assertEqual(parsed["salary_raw"], "Muc luong: 15 - 20 trieu")
        self.assertEqual(parse_salary_values(parsed["salary_raw"]), (15_000_000, 20_000_000, "VND"))
        self.assertEqual(parsed["salary_min"], 15_000_000)
        self.assertEqual(parsed["salary_max"], 20_000_000)
        self.assertEqual(parsed["salary_currency"], "VND")

    def test_parses_usd_salary(self) -> None:
        record = make_record(
            """
            <html><body><main>
              <h1>Tester</h1>
              <a class="company-name" href="/cong-ty/example">Example Co</a>
              <div class="salary">Tu 1,000 USD</div>
            </main></body></html>
            """
        )

        parsed = parse_record(record)

        self.assertEqual(parsed["salary_min"], 1000)
        self.assertIsNone(parsed["salary_max"])
        self.assertEqual(parsed["salary_currency"], "USD")

    def test_preserves_negotiable_salary_without_numeric_values(self) -> None:
        record = make_record(
            """
            <html><body><main>
              <h1>Frontend Developer</h1>
              <a class="company-name" href="/cong-ty/example">Example Co</a>
              <div class="salary">Thoa thuan</div>
            </main></body></html>
            """
        )

        parsed = parse_record(record)

        self.assertEqual(parsed["salary_raw"], "Thoa thuan")
        self.assertIsNone(parsed["salary_min"])
        self.assertIsNone(parsed["salary_max"])


class ExperienceTests(unittest.TestCase):
    def test_parses_not_required(self) -> None:
        self.assertEqual(parse_experience("Khong yeu cau"), ("Khong yeu cau", 0, 0))

    def test_parses_under_one_year(self) -> None:
        self.assertEqual(parse_experience("Duoi 1 nam"), ("Duoi 1 nam", 0, 1))

    def test_parses_over_five_years(self) -> None:
        self.assertEqual(parse_experience("Tren 5 nam"), ("Tren 5 nam", 5, None))


class ParseRecordTests(unittest.TestCase):
    def test_extracts_core_fields_skills_and_trend_fields(self) -> None:
        record = make_record(
            """
            <html><body><main>
              <h1>Senior Backend Python Developer</h1>
              <a class="company-name" href="/cong-ty/example">Example Co</a>
              <div class="salary">Muc luong: 15 - 20 trieu / thang</div>
              <div class="location">Ha Noi</div>
              <div class="skills"><span>Python</span><span>SQL</span></div>
              <section><h2>Mo ta cong viec</h2><p>Build APIs.</p></section>
              <section><h2>Yeu cau ung vien</h2><p>Tu 2 den 4 nam kinh nghiem Python SQL.</p></section>
              <section><h2>Quyen loi</h2><p>Monthly salary review.</p></section>
              <section><h2>Viec lam lien quan</h2><p>Java footer noise 5 nam.</p></section>
            </main></body></html>
            """,
            visible_text="Dang 1 tuan truoc\nHa Noi\nRemote accepted",
        )

        parsed = parse_record(record)

        self.assertEqual(parsed["title"], "Senior Backend Python Developer")
        self.assertEqual(parsed["company"], "Example Co")
        self.assertEqual(parsed["location"], "Ha Noi")
        self.assertEqual(parsed["skills"], ["Python", "SQL"])
        self.assertEqual(parsed["experience_min"], 2)
        self.assertEqual(parsed["experience_max"], 4)
        self.assertEqual(parsed["seniority"], "senior")
        self.assertEqual(parsed["work_mode"], "remote")
        self.assertEqual(parsed["salary_period"], "month")
        self.assertEqual(parsed["location_cities"], ["Ha Noi"])
        self.assertEqual(parsed["posted_raw"], "Dang 1 tuan truoc")
        self.assertIn("Build APIs", parsed["description"])
        self.assertNotIn("Java footer noise", parsed["description"])
        self.assertEqual(parsed["parse_status"], "ok")

    def test_uses_json_ld_dates_and_employment_type(self) -> None:
        record = make_record(
            """
            <html><body><main>
              <h1>Backend Developer</h1>
              <a class="company-name" href="/cong-ty/example">Example Co</a>
            </main></body></html>
            """
        )
        record["json_ld"] = [
            {
                "@type": "JobPosting",
                "datePosted": "2026-07-01",
                "validThrough": "2026-08-01",
                "employmentType": "FULL_TIME",
            }
        ]

        parsed = parse_record(record)

        self.assertEqual(parsed["posted_at"], "2026-07-01")
        self.assertEqual(parsed["valid_through"], "2026-08-01")
        self.assertEqual(parsed["employment_type"], "full_time")


if __name__ == "__main__":
    unittest.main()
