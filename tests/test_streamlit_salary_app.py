from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "streamlit_salary_regression_opencode.py"


def load_app() -> AppTest:
    return AppTest.from_file(str(APP_PATH), default_timeout=30).run()


class StreamlitSalaryAppTests(unittest.TestCase):
    def test_initial_screen_is_vietnamese_and_does_not_predict(self) -> None:
        app = load_app()

        self.assertFalse(app.exception)
        self.assertEqual([item.value for item in app.title], ["Dự báo lương CNTT Việt Nam"])
        self.assertEqual([item.label for item in app.tabs], ["Dự đoán lương", "Thông tin mô hình"])
        self.assertEqual([item.value for item in app.selectbox[:4]], [None, None, None, None])
        self.assertFalse(app.metric)
        self.assertEqual(app.button[0].label, "Dự đoán lương")
        self.assertIn("Huấn luyện qua Notebook", [item.value for item in app.subheader])
        self.assertTrue(any("jupyter.exe notebook" in item.value for item in app.code))
        self.assertNotIn("Huấn luyện Hồi quy tuyến tính", [item.label for item in app.button])

    def test_valid_submit_shows_vietnamese_prediction_and_interval(self) -> None:
        app = load_app()
        for widget, value in zip(
            app.selectbox[:4],
            ["topcv", "Ho Chi Minh", "middle", "onsite"],
            strict=True,
        ):
            widget.set_value(value)
        app.number_input[0].set_value(2.0)
        app.multiselect[0].set_value(["sql", "python", "aws"])
        app.button[0].click().run()

        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertIn("Ước lượng lương từ mô hình", [item.label for item in app.metric])
        self.assertTrue(any("Khoảng sai số 90%" in item.value for item in app.caption))

    def test_intern_with_more_than_one_year_shows_vietnamese_validation_error(self) -> None:
        app = load_app()
        for widget, value in zip(
            app.selectbox[:4],
            ["topcv", "Ho Chi Minh", "intern", "onsite"],
            strict=True,
        ):
            widget.set_value(value)
        app.number_input[0].set_value(2.0)
        app.button[0].click().run()

        self.assertFalse(app.exception)
        self.assertIn(
            "Với cấp độ Thực tập, kinh nghiệm phải nằm trong khoảng 0–1 năm.",
            [item.value for item in app.error],
        )
        self.assertFalse(app.metric)


if __name__ == "__main__":
    unittest.main()
