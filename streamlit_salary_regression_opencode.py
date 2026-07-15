from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pandas as pd
import sklearn
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modeling.salary_regression import (  # noqa: E402
    ARTIFACT_FILENAMES,
    DEFAULT_OUTPUT_DIR,
    MODEL_FILENAME,
    build_prediction_frame,
    load_model_bundle,
    predict_salary_million_vnd,
)

SAFE_MODEL_SUBFOLDER = "safe_baseline"
DEFAULT_POSTED_AGE_DAYS = 7

SENIORITY_LABELS = {
    "Unknown": "Chưa xác định",
    "intern": "Thực tập",
    "junior": "Mới đi làm",
    "middle": "Trung cấp",
    "senior": "Cấp cao",
    "lead": "Trưởng nhóm",
}
WORK_MODE_LABELS = {
    "onsite": "Tại văn phòng",
    "hybrid": "Kết hợp",
    "remote": "Từ xa",
}
LOCATION_LABELS = {
    "Bắc Ninh": "Bắc Ninh",
    "Da Nang": "Đà Nẵng",
    "Gia Lai": "Gia Lai",
    "Ha Noi": "Hà Nội",
    "Ho Chi Minh": "TP. Hồ Chí Minh",
    "Hưng Yên": "Hưng Yên",
    "Hải Phòng": "Hải Phòng",
    "Khánh Hòa": "Khánh Hòa",
    "Nhật Bản": "Nhật Bản",
    "Ninh Bình": "Ninh Bình",
    "Nước Ngoài": "Nước ngoài",
    "Thanh Hóa": "Thanh Hóa",
    "Thành phố khác": "Thành phố khác",
    "Tây Ninh": "Tây Ninh",
    "Đồng Nai": "Đồng Nai",
}
SOURCE_LABELS = {"itviec": "ITviec", "topcv": "TopCV"}


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def display_option(value: str, labels: dict[str, str]) -> str:
    return labels.get(value, value)


def format_million_vnd(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " triệu VNĐ/tháng"


def find_model_dirs(model_root: Path) -> list[Path]:
    candidates: list[Path] = []
    if (model_root / MODEL_FILENAME).exists():
        candidates.append(model_root)
    if model_root.exists():
        candidates.extend(path.parent for path in sorted(model_root.rglob(MODEL_FILENAME)))

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(candidate)
    return sorted(
        unique,
        key=lambda path: (path.name != SAFE_MODEL_SUBFOLDER, str(path).casefold()),
    )


def artifact_status(output_dir: Path) -> pd.DataFrame:
    rows = []
    for filename in ARTIFACT_FILENAMES:
        path = output_dir / filename
        rows.append(
            {
                "Tệp": filename,
                "Sẵn sàng": "Có" if path.exists() else "Không",
                "Đường dẫn": display_path(path),
                "Dung lượng (KB)": round(path.stat().st_size / 1024, 1) if path.exists() else None,
            }
        )
    return pd.DataFrame(rows)


def option_list(bundle: dict[str, Any], column: str, fallback: list[str]) -> list[str]:
    values = bundle.get("category_options", {}).get(column, [])
    cleaned = [str(value) for value in values if str(value).strip()]
    return cleaned or fallback


def model_runtime_sklearn_version(bundle: dict[str, Any]) -> str | None:
    metadata = bundle.get("runtime_metadata")
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("scikit_learn_version")
    return str(value) if value else None


def translate_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    if "scope" in output:
        output["scope"] = output["scope"].replace({"overall": "Tổng thể", "group": "Theo nhóm"})
    if "group_column" in output:
        output["group_column"] = output["group_column"].replace(
            {"source": "Nguồn", "seniority": "Cấp độ"}
        )
    if "group_value" in output:
        output["group_value"] = output["group_value"].map(
            lambda value: display_option(str(value), SENIORITY_LABELS)
            if str(value) in SENIORITY_LABELS
            else display_option(str(value), SOURCE_LABELS)
        )
    return output.rename(
        columns={
            "scope": "Phạm vi",
            "group_column": "Nhóm theo",
            "group_value": "Giá trị nhóm",
            "n": "Số tin",
            "mae_log": "MAE log",
            "rmse_log": "RMSE log",
            "r2_log": "R² log",
            "mae_million_vnd": "MAE (triệu VNĐ/tháng)",
            "rmse_million_vnd": "RMSE (triệu VNĐ/tháng)",
            "median_abs_error_million_vnd": "Trung vị sai số tuyệt đối (triệu VNĐ/tháng)",
        }
    )


def translate_coefficients(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(
        columns={
            "feature": "Đặc trưng",
            "coefficient": "Hệ số",
            "abs_coefficient": "Độ lớn tuyệt đối",
        }
    )


def translate_observed_salary(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    if "seniority" in output:
        output["seniority"] = output["seniority"].map(
            lambda value: display_option(str(value), SENIORITY_LABELS)
        )
    return output.rename(
        columns={
            "seniority": "Cấp độ",
            "rows": "Số tin",
            "median_million_vnd": "Trung vị (triệu VNĐ/tháng)",
            "p10_million_vnd": "P10 (triệu VNĐ/tháng)",
            "p90_million_vnd": "P90 (triệu VNĐ/tháng)",
        }
    )


def translate_audit(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns={"metric": "Chỉ số", "value": "Giá trị"})


@st.cache_resource
def cached_load_model(model_path: str) -> dict[str, Any]:
    return load_model_bundle(Path(model_path))


def default_model_path() -> Path:
    return resolve_repo_path(DEFAULT_OUTPUT_DIR) / SAFE_MODEL_SUBFOLDER / MODEL_FILENAME


def set_selected_model(path: Path) -> None:
    st.session_state["selected_model_path"] = str(path.resolve())
    cached_load_model.clear()


def selected_model_path() -> Path:
    if "selected_model_path" not in st.session_state:
        set_selected_model(default_model_path())
    return Path(st.session_state["selected_model_path"])


def render_prediction_result(bundle: dict[str, Any], form_values: dict[str, Any]) -> None:
    seniority = str(form_values["seniority"])
    experience_min = float(form_values["experience_min"])
    if seniority == "intern" and experience_min > 1:
        st.error("Với cấp độ Thực tập, kinh nghiệm phải nằm trong khoảng 0–1 năm.")
        return

    try:
        prediction_frame = build_prediction_frame(
            bundle,
            source=str(form_values["source"]),
            location=str(form_values["location"]),
            seniority=None if seniority == "Unknown" else seniority,
            work_mode=str(form_values["work_mode"]),
            experience_min=experience_min,
            posted_age_days=float(form_values["posted_age_days"]),
            selected_skills=list(form_values["selected_skills"]),
        )
        prediction = predict_salary_million_vnd(bundle, prediction_frame)
    except ValueError as exc:
        st.error(f"Không thể tạo dự đoán: {exc}")
        return

    observed_by_seniority = bundle.get("observed_salary_by_seniority", {})
    observed = observed_by_seniority.get(seniority) if isinstance(observed_by_seniority, dict) else None
    st.divider()
    st.subheader("Kết quả")
    if seniority == "intern" and isinstance(observed, dict):
        st.warning(
            "Dữ liệu Thực tập còn ít. Vì vậy app ưu tiên thống kê lương quan sát được thay vì "
            "coi dự đoán theo kỹ năng là ước lượng đáng tin cậy."
        )
        observed_left, observed_right = st.columns(2)
        with observed_left:
            st.metric("Trung vị lương Thực tập quan sát được", format_million_vnd(float(observed["median_million_vnd"])))
        with observed_right:
            st.metric(
                "Khoảng P10–P90 quan sát được",
                f"{format_million_vnd(float(observed['p10_million_vnd']))} – "
                f"{format_million_vnd(float(observed['p90_million_vnd']))}",
            )
        st.caption(f"Số tin Thực tập có lương số: {int(observed['rows'])}.")
        with st.expander("Xem ước lượng mô hình nền (tham khảo kỹ thuật)"):
            st.metric("Ước lượng từ mô hình", format_million_vnd(prediction["predicted_salary_million_vnd"]))
    else:
        st.metric("Ước lượng lương từ mô hình", format_million_vnd(prediction["predicted_salary_million_vnd"]))
        low = prediction.get("prediction_low_million_vnd")
        high = prediction.get("prediction_high_million_vnd")
        if low is not None and high is not None:
            st.caption(
                "Khoảng sai số 90% trên tập kiểm tra: "
                f"{format_million_vnd(float(low))} – {format_million_vnd(float(high))}."
            )
        else:
            st.info("Mô hình này chưa có dữ liệu hiệu chuẩn khoảng sai số. Hãy huấn luyện lại mô hình.")

    st.warning(
        "Đây là ước lượng từ mẫu dữ liệu tuyển dụng tại một thời điểm, không phải mức đề nghị lương hoặc kết luận chính xác."
    )
    with st.expander("Chi tiết kỹ thuật"):
        st.caption(f"Giá trị log của lương dự đoán: {prediction['predicted_log_salary']:.4f}")
        st.dataframe(prediction_frame, width="stretch", hide_index=True)


def render_admin(bundle: dict[str, Any], model_path: Path) -> None:
    with st.expander("Quản trị kỹ thuật", expanded=False):
        st.caption("Khu vực này dành cho việc nạp hoặc huấn luyện mô hình; không cần dùng khi trình diễn dự đoán.")
        model_root_text = st.text_input(
            "Thư mục chứa mô hình",
            value=str(resolve_repo_path(DEFAULT_OUTPUT_DIR)),
            key="admin_model_root",
        )
        model_root = resolve_repo_path(model_root_text)
        model_dirs = find_model_dirs(model_root)

        if model_dirs:
            selected_dir = st.selectbox(
                "Mô hình đã huấn luyện có sẵn",
                options=model_dirs,
                format_func=display_path,
                key="admin_selected_model_dir",
            )
            if st.button("Nạp mô hình đã chọn", key="load_selected_model"):
                set_selected_model(selected_dir / MODEL_FILENAME)
                st.rerun()
            st.dataframe(
                pd.DataFrame(
                    {
                        "Thư mục": [display_path(path) for path in model_dirs],
                        "Mô hình": [display_path(path / MODEL_FILENAME) for path in model_dirs],
                    }
                ),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("Chưa tìm thấy mô hình nào trong thư mục đã chọn.")

        custom_model_text = st.text_input(
            "Hoặc nhập đường dẫn model.joblib",
            value="",
            key="admin_custom_model_path",
        )
        if st.button("Nạp mô hình theo đường dẫn", key="load_custom_model"):
            custom_model_path = resolve_repo_path(custom_model_text)
            if not custom_model_text.strip():
                st.error("Hãy nhập đường dẫn tới tệp model.joblib.")
            elif custom_model_path.name != MODEL_FILENAME:
                st.error("Tệp cần nạp phải có tên model.joblib.")
            elif not custom_model_path.exists():
                st.error("Không tìm thấy tệp model tại đường dẫn đã nhập.")
            else:
                set_selected_model(custom_model_path)
                st.rerun()

        trained_with = model_runtime_sklearn_version(bundle)
        if trained_with is None:
            st.warning("Mô hình hiện tại chưa có thông tin phiên bản scikit-learn. Hãy huấn luyện lại để theo dõi tương thích.")
        elif trained_with != sklearn.__version__:
            st.warning(
                f"Mô hình được huấn luyện với scikit-learn {trained_with}, nhưng app đang chạy {sklearn.__version__}. "
                "Hãy huấn luyện lại trước khi demo."
            )
        else:
            st.success(f"Mô hình tương thích với scikit-learn {sklearn.__version__}.")

        st.divider()
        st.subheader("Huấn luyện qua Notebook")
        st.info(
            "Để giữ đầy đủ bước khám phá dữ liệu, biểu đồ và kiểm tra kết quả, mô hình chỉ được huấn luyện "
            "trong notebook; Streamlit không huấn luyện trực tiếp."
        )
        st.code(
            ".\\.venv\\Scripts\\jupyter.exe notebook notebooks/04_salary_linear_regression_training.ipynb",
            language="powershell",
        )
        st.caption("Mở notebook, chạy lần lượt tất cả cell; cell cuối sẽ ghi model mới vào safe_baseline cho Streamlit nạp.")

        st.subheader("Tệp của mô hình đang nạp")
        st.caption(display_path(model_path))
        st.dataframe(artifact_status(model_path.parent), width="stretch", hide_index=True)


def render_model_information(bundle: dict[str, Any], model_path: Path) -> None:
    st.subheader("Thông tin mô hình")
    st.write("Mô hình đang dùng: **Hồi quy tuyến tính** dự đoán log lương tháng từ nguồn, khu vực, cấp độ, kinh nghiệm, tuổi tin và kỹ năng.")
    st.caption("Ước lượng thể hiện mối liên hệ trong mẫu dữ liệu; không xác định quan hệ nhân quả cho một ứng viên.")
    model_left, model_right = st.columns(2)
    with model_left:
        st.write(f"Dòng huấn luyện: **{bundle.get('train_rows', '—')}**")
    with model_right:
        st.write(f"Dòng kiểm tra: **{bundle.get('test_rows', '—')}**")

    metrics = bundle.get("metrics")
    if isinstance(metrics, pd.DataFrame):
        with st.expander("Chỉ số đánh giá", expanded=True):
            st.dataframe(translate_metrics(metrics), width="stretch", hide_index=True)

    coefficients = bundle.get("coefficients")
    if isinstance(coefficients, pd.DataFrame) and not coefficients.empty:
        with st.expander("Đặc trưng có hệ số lớn"):
            display_columns = [column for column in ["feature", "coefficient", "abs_coefficient"] if column in coefficients]
            st.dataframe(translate_coefficients(coefficients[display_columns].head(30)), width="stretch", hide_index=True)
            signed = coefficients.sort_values("coefficient")
            chart_data = pd.concat([signed.head(10), signed.tail(10)]).drop_duplicates("feature")
            st.bar_chart(chart_data.set_index("feature")["coefficient"])
            st.caption("Các hệ số danh mục được so sánh với một nhóm tham chiếu bị loại bỏ khi mã hóa; không mang ý nghĩa nhân quả.")

    observed_by_seniority = bundle.get("observed_salary_by_seniority")
    if isinstance(observed_by_seniority, dict) and observed_by_seniority:
        with st.expander("Lương quan sát theo cấp độ"):
            observed_rows = [
                {"seniority": seniority, **stats}
                for seniority, stats in observed_by_seniority.items()
                if isinstance(stats, dict)
            ]
            st.dataframe(translate_observed_salary(pd.DataFrame(observed_rows)), width="stretch", hide_index=True)

    audit = bundle.get("audit")
    if isinstance(audit, pd.DataFrame):
        with st.expander("Kiểm tra dữ liệu huấn luyện"):
            st.dataframe(translate_audit(audit), width="stretch", hide_index=True)

    render_admin(bundle, model_path)


st.set_page_config(page_title="Dự báo lương CNTT Việt Nam", layout="wide")
st.title("Dự báo lương CNTT Việt Nam")
st.caption("Minh hoạ Hồi quy tuyến tính trên mẫu dữ liệu tin tuyển dụng công khai tại một thời điểm.")

model_path = selected_model_path()
if not model_path.exists():
    st.warning("Chưa tìm thấy mô hình để demo.")
    st.code(
        ".\\.venv\\Scripts\\python.exe -m modeling.salary_regression --input data/analysis/salary_analysis_clean.csv --output-dir data/modeling/salary_regression/safe_baseline",
        language="powershell",
    )
    st.stop()

try:
    bundle = cached_load_model(str(model_path))
except Exception as exc:  # pragma: no cover - Streamlit UI guard
    st.error(f"Không thể nạp mô hình: {exc}")
    st.stop()

if notice := st.session_state.pop("model_notice", None):
    st.success(notice)

predict_tab, explain_tab = st.tabs(["Dự đoán lương", "Thông tin mô hình"])

with predict_tab:
    st.subheader("Nhập thông tin tin tuyển dụng")
    st.caption("Chọn thông tin có trong tin tuyển dụng rồi bấm Dự đoán lương. App không tự tạo kết quả khi bạn mới mở trang.")

    source_options = option_list(bundle, "source", ["topcv", "itviec"])
    location_options = option_list(bundle, "location_norm", ["Ha Noi", "Ho Chi Minh", "Da Nang"])
    seniority_options = list(dict.fromkeys(["Unknown", *option_list(bundle, "seniority", ["intern", "junior", "middle", "senior", "lead"])]))
    work_mode_options = option_list(bundle, "work_mode", ["onsite", "hybrid", "remote"])

    with st.form("prediction_form"):
        left, right = st.columns(2)
        with left:
            source = st.selectbox(
                "Nguồn dữ liệu",
                options=source_options,
                index=None,
                placeholder="Chọn nguồn",
                format_func=lambda value: display_option(value, SOURCE_LABELS),
            )
            location = st.selectbox(
                "Khu vực làm việc",
                options=location_options,
                index=None,
                placeholder="Chọn khu vực",
                format_func=lambda value: display_option(value, LOCATION_LABELS),
            )
            seniority = st.selectbox(
                "Cấp độ",
                options=seniority_options,
                index=None,
                placeholder="Chọn cấp độ",
                format_func=lambda value: display_option(value, SENIORITY_LABELS),
            )
            work_mode = st.selectbox(
                "Hình thức làm việc",
                options=work_mode_options,
                index=None,
                placeholder="Chọn hình thức",
                format_func=lambda value: display_option(value, WORK_MODE_LABELS),
            )
        with right:
            experience_min = st.number_input(
                "Kinh nghiệm tối thiểu (năm)",
                min_value=0.0,
                max_value=10.0,
                value=0.0,
                step=0.5,
                help="Nếu chọn Thực tập, chỉ nhập từ 0 đến 1 năm.",
            )
            posted_age_days = st.slider(
                "Số ngày từ khi tin được đăng",
                min_value=0,
                max_value=90,
                value=DEFAULT_POSTED_AGE_DAYS,
                help="Mô hình dùng trường này vì dữ liệu huấn luyện có tuổi tin tuyển dụng.",
            )
            selected_skills = st.multiselect(
                "Kỹ năng có trong mô tả công việc",
                options=bundle.get("top_skills", []),
                default=[],
                help="Chỉ các kỹ năng có trong danh sách mô hình mới được đưa vào dự đoán.",
            )
        submitted = st.form_submit_button("Dự đoán lương", type="primary")

    if submitted:
        missing = [
            label
            for label, value in {
                "Nguồn dữ liệu": source,
                "Khu vực làm việc": location,
                "Cấp độ": seniority,
                "Hình thức làm việc": work_mode,
            }.items()
            if value is None
        ]
        if missing:
            st.error("Hãy chọn đầy đủ: " + ", ".join(missing) + ".")
        else:
            render_prediction_result(
                bundle,
                {
                    "source": source,
                    "location": location,
                    "seniority": seniority,
                    "work_mode": work_mode,
                    "experience_min": experience_min,
                    "posted_age_days": posted_age_days,
                    "selected_skills": selected_skills,
                },
            )

with explain_tab:
    render_model_information(bundle, model_path)
