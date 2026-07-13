from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from modeling.salary_regression import (
    LEAKAGE_COLUMNS,
    DEFAULT_USD_TO_VND,
    MODEL_FILENAME,
    build_model_bundle,
    build_prediction_frame,
    experience_range_for_seniority,
    load_model_bundle,
    normalize_skill,
    predict_salary_million_vnd,
    prepare_salary_modeling_data,
    run_salary_linear_regression,
    skill_column_name,
    main as salary_main,
)


def make_row(
    index: int,
    *,
    source: str = "topcv",
    location: str = "Ha Noi",
    salary_raw: str = "20000000 VND",
    salary_currency: str = "VND",
    salary_period: str = "month",
    salary_midpoint: float = 20_000_000,
    skills: str = "Python, SQL",
    experience_min: float = 2,
    seniority: str = "middle",
    work_mode: str = "onsite",
) -> dict[str, object]:
    return {
        "source": source,
        "url": f"https://example.com/jobs/{index}",
        "title": f"Software Engineer {index}",
        "company": "Example Co",
        "location": location,
        "salary_raw": salary_raw,
        "salary_currency": salary_currency,
        "salary_period": salary_period,
        "salary_midpoint": salary_midpoint,
        "skills": skills,
        "experience_min": experience_min,
        "seniority": seniority,
        "work_mode": work_mode,
        "scraped_at": "2026-07-02T00:00:00+00:00",
        "posted_at": "2026-06-30",
    }


def sample_training_frame() -> pd.DataFrame:
    rows = []
    skills = ["Python, SQL", "ReactJS, JS", "NodeJS, PostgreSQL", "Docker, AWS"]
    locations = ["Ha Noi", "TP. HCM", "Da Nang"]
    seniorities = ["junior", "middle", "senior"]
    for index in range(24):
        is_itviec = index % 2 == 0
        experience = float(index % 6)
        midpoint_million = 12 + experience * 4 + (8 if seniorities[index % 3] == "senior" else 0)
        if is_itviec:
            salary_midpoint = midpoint_million * 1_000_000 / DEFAULT_USD_TO_VND
            currency = "USD"
            raw = f"{int(salary_midpoint)} USD"
            source = "itviec"
        else:
            salary_midpoint = midpoint_million * 1_000_000
            currency = "VND"
            raw = f"{int(salary_midpoint)} VND"
            source = "topcv"
        rows.append(
            make_row(
                index,
                source=source,
                location=locations[index % len(locations)],
                salary_raw=raw,
                salary_currency=currency,
                salary_midpoint=salary_midpoint,
                skills=skills[index % len(skills)],
                experience_min=experience,
                seniority="" if index == 5 else seniorities[index % len(seniorities)],
                work_mode="remote" if index % 4 == 0 else "onsite",
            )
        )
    return pd.DataFrame(rows)


class SalaryRegressionTests(unittest.TestCase):
    def test_intern_experience_is_limited_to_observed_entry_level_range(self) -> None:
        self.assertEqual(experience_range_for_seniority("intern"), (0.0, 1.0))
        self.assertEqual(experience_range_for_seniority("senior"), (0.0, 10.0))

        result = run_salary_linear_regression(sample_training_frame(), top_skills=4, min_skill_count=1)
        bundle = build_model_bundle(result)

        with self.assertRaisesRegex(ValueError, "intern"):
            build_prediction_frame(
                bundle,
                source="topcv",
                location="Ha Noi",
                seniority="intern",
                work_mode="onsite",
                experience_min=2,
            )

    def test_converts_salary_to_monthly_vnd_and_cleans_period(self) -> None:
        frame = pd.DataFrame(
            [
                make_row(1, salary_raw="1000 USD", salary_currency="USD", salary_period="month", salary_midpoint=1000),
                make_row(2, salary_raw="20000000 VND", salary_currency="VND", salary_period="month", salary_midpoint=20_000_000),
                make_row(3, salary_raw="12000000 VND", salary_currency="VND", salary_period="year", salary_midpoint=12_000_000),
                make_row(4, salary_raw="120000 USD per year", salary_currency="USD", salary_period="year", salary_midpoint=120_000),
            ]
        )

        prepared = prepare_salary_modeling_data(frame, top_skills=3, min_skill_count=1)
        by_url = prepared.frame.set_index("url")

        self.assertEqual(by_url.loc["https://example.com/jobs/1", "salary_monthly_vnd"], 26_000_000)
        self.assertEqual(by_url.loc["https://example.com/jobs/2", "salary_monthly_vnd"], 20_000_000)
        self.assertEqual(by_url.loc["https://example.com/jobs/3", "salary_period_clean"], "month")
        self.assertEqual(by_url.loc["https://example.com/jobs/3", "salary_monthly_vnd"], 12_000_000)
        self.assertEqual(by_url.loc["https://example.com/jobs/4", "salary_period_clean"], "year")
        self.assertEqual(by_url.loc["https://example.com/jobs/4", "salary_monthly_vnd"], 260_000_000)

    def test_feature_preparation_normalizes_locations_skills_and_excludes_leakage(self) -> None:
        frame = pd.DataFrame(
            [
                make_row(1, location="TP. HCM", skills="ReactJS, JS, NodeJS"),
                make_row(2, location="Hà Nội", skills="Golang, K8S, Postgres"),
                make_row(3, location="Danang", skills="Dotnet, CSharp, TypeScript"),
                make_row(4, location="Unknown Place", skills="Python, SQL"),
                make_row(5, location="Ho Chi Minh", skills="React.js, Node, PostgreSQL"),
            ]
        )

        prepared = prepare_salary_modeling_data(frame, top_skills=20, min_skill_count=1)

        self.assertIn("Ho Chi Minh", set(prepared.frame["location_norm"]))
        self.assertIn("Ha Noi", set(prepared.frame["location_norm"]))
        self.assertIn("Da Nang", set(prepared.frame["location_norm"]))
        self.assertEqual(normalize_skill("ReactJS"), "react")
        self.assertEqual(normalize_skill("NodeJS"), "node.js")
        self.assertEqual(normalize_skill("Golang"), "go")
        self.assertEqual(normalize_skill("K8S"), "kubernetes")

        react_column = skill_column_name("react")
        node_column = skill_column_name("node.js")
        self.assertIn(react_column, prepared.skill_features)
        self.assertIn(node_column, prepared.skill_features)
        self.assertEqual(int(prepared.frame.loc[0, react_column]), 1)
        self.assertEqual(int(prepared.frame.loc[0, node_column]), 1)
        self.assertFalse(set(prepared.feature_columns) & LEAKAGE_COLUMNS)

    def test_fit_returns_metrics_predictions_and_coefficients(self) -> None:
        result = run_salary_linear_regression(
            sample_training_frame(),
            top_skills=4,
            min_skill_count=1,
            test_size=0.25,
            random_state=7,
        )

        overall = result.metrics.loc[result.metrics["scope"].eq("overall")].iloc[0]
        self.assertEqual(result.train_rows + result.test_rows, 24)
        self.assertTrue(np.isfinite(overall["mae_log"]))
        self.assertTrue(np.isfinite(overall["rmse_log"]))
        self.assertTrue((result.predictions["predicted_salary_million_vnd"] > 0).all())
        self.assertGreater(len(result.coefficients), 0)
        self.assertIn("feature", result.coefficients.columns)

    def test_model_bundle_includes_observed_salary_and_prediction_interval(self) -> None:
        frame = sample_training_frame()
        frame = pd.concat(
            [
                frame,
                pd.DataFrame(
                    [
                        make_row(100, seniority="intern", experience_min=0, salary_midpoint=4_000_000),
                        make_row(101, seniority="intern", experience_min=1, salary_midpoint=6_000_000),
                    ]
                ),
            ],
            ignore_index=True,
        )
        result = run_salary_linear_regression(frame, top_skills=4, min_skill_count=1, random_state=7)
        bundle = build_model_bundle(result)

        observed = bundle["observed_salary_by_seniority"]["intern"]
        self.assertEqual(observed["rows"], 2)
        self.assertEqual(observed["median_million_vnd"], 5.0)

        prediction_frame = build_prediction_frame(
            bundle,
            source="topcv",
            location="Ha Noi",
            seniority="intern",
            work_mode="onsite",
            experience_min=0,
        )
        prediction = predict_salary_million_vnd(bundle, prediction_frame)
        self.assertIn("prediction_low_million_vnd", prediction)
        self.assertIn("prediction_high_million_vnd", prediction)
        self.assertLessEqual(
            prediction["prediction_low_million_vnd"],
            prediction["predicted_salary_million_vnd"],
        )
        self.assertGreaterEqual(
            prediction["prediction_high_million_vnd"],
            prediction["predicted_salary_million_vnd"],
        )

    def test_model_bundle_only_offers_categories_seen_by_the_fitted_pipeline(self) -> None:
        frame = pd.concat(
            [sample_training_frame(), pd.DataFrame([make_row(102, location="Rare Location")])],
            ignore_index=True,
        )
        result = run_salary_linear_regression(
            frame,
            top_skills=4,
            min_skill_count=1,
            test_size=0.25,
            random_state=4,
        )
        bundle = build_model_bundle(result)

        self.assertNotIn("Rare Location", bundle["category_options"]["location_norm"])

    def test_main_writes_expected_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            input_path = base / "salary.csv"
            output_dir = base / "outputs"
            sample_training_frame().to_csv(input_path, index=False, encoding="utf-8-sig")

            argv = [
                "salary_regression",
                "--input",
                str(input_path),
                "--output-dir",
                str(output_dir),
                "--top-skills",
                "4",
                "--min-skill-count",
                "1",
                "--test-size",
                "0.25",
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(StringIO()):
                salary_main()

            self.assertTrue((output_dir / "metrics.csv").exists())
            self.assertTrue((output_dir / "predictions_test.csv").exists())
            self.assertTrue((output_dir / "coefficients.csv").exists())
            self.assertTrue((output_dir / "data_audit.csv").exists())
            self.assertTrue((output_dir / MODEL_FILENAME).exists())

            bundle = load_model_bundle(output_dir / MODEL_FILENAME)
            prediction_frame = build_prediction_frame(
                bundle,
                source="topcv",
                location="Ha Noi",
                seniority="middle",
                work_mode="onsite",
                experience_min=2,
                selected_skills=["Python", "SQL"],
            )
            prediction = predict_salary_million_vnd(bundle, prediction_frame)
            self.assertGreater(prediction["predicted_salary_million_vnd"], 0)


if __name__ == "__main__":
    unittest.main()
