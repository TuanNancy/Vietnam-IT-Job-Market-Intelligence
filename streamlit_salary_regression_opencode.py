from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modeling.salary_regression import (  # noqa: E402
    ARTIFACT_FILENAMES,
    DEFAULT_INPUT,
    DEFAULT_OUTPUT_DIR,
    MODEL_FILENAME,
    build_prediction_frame,
    load_model_bundle,
    predict_salary_million_vnd,
    run_salary_linear_regression,
    write_outputs,
)

DEFAULT_MODEL_PATH = DEFAULT_OUTPUT_DIR / MODEL_FILENAME


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


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
    return unique


def artifact_status(output_dir: Path) -> pd.DataFrame:
    rows = []
    for filename in ARTIFACT_FILENAMES:
        path = output_dir / filename
        rows.append(
            {
                "artifact": filename,
                "exists": path.exists(),
                "path": display_path(path),
                "size_kb": round(path.stat().st_size / 1024, 1) if path.exists() else None,
            }
        )
    return pd.DataFrame(rows)


@st.cache_resource
def cached_load_model(model_path: str) -> dict:
    return load_model_bundle(Path(model_path))


def option_list(bundle: dict, column: str, fallback: list[str]) -> list[str]:
    values = bundle.get("category_options", {}).get(column, [])
    cleaned = [str(value) for value in values if str(value).strip()]
    return cleaned or fallback


def train_model_from_sidebar(
    salary_path: Path,
    output_dir: Path,
    top_skills: int,
    min_skill_count: int,
    test_size: float,
    random_state: int,
) -> Path:
    frame = pd.read_csv(salary_path, encoding="utf-8-sig")
    result = run_salary_linear_regression(
        frame,
        top_skills=top_skills,
        min_skill_count=min_skill_count,
        test_size=test_size,
        random_state=random_state,
    )
    write_outputs(result, output_dir)
    cached_load_model.clear()
    return output_dir / MODEL_FILENAME


st.set_page_config(page_title="IT Salary Linear Regression", layout="wide")
st.title("IT Salary Linear Regression")
st.caption("Demo du bao luong CNTT Viet Nam bang sklearn.linear_model.LinearRegression.")

with st.sidebar:
    st.header("Model files")
    salary_path = resolve_repo_path(st.text_input("Salary CSV", value=str(DEFAULT_INPUT)))
    model_root = resolve_repo_path(st.text_input("Model root folder", value=str(DEFAULT_OUTPUT_DIR)))

    model_dirs = find_model_dirs(model_root)
    if model_dirs:
        selected_model_dir = st.selectbox(
            "Available trained folder",
            options=model_dirs,
            format_func=display_path,
            index=0,
        )
    else:
        selected_model_dir = model_root
        st.info("No trained model found yet.")

    model_path = selected_model_dir / MODEL_FILENAME
    custom_model_path = st.text_input("Model file to load", value=str(model_path))
    model_path = resolve_repo_path(custom_model_path)

    with st.expander("Model folders found", expanded=bool(model_dirs)):
        if model_dirs:
            st.dataframe(
                pd.DataFrame(
                    {
                        "folder": [display_path(path) for path in model_dirs],
                        "model_file": [display_path(path / MODEL_FILENAME) for path in model_dirs],
                    }
                ),
                use_container_width=True,
            )
        else:
            st.write("No model folders found yet.")

    st.divider()
    st.subheader("Train / update")
    output_subfolder = st.text_input("Optional train subfolder", value="")
    output_dir = model_root / output_subfolder.strip() if output_subfolder.strip() else model_root
    st.caption(f"Train will write: `{display_path(output_dir / MODEL_FILENAME)}`")
    top_skills = st.slider("Top skills", min_value=5, max_value=50, value=30, step=5)
    min_skill_count = st.slider("Min skill count", min_value=1, max_value=20, value=5)
    test_size = st.slider("Test size", min_value=0.1, max_value=0.4, value=0.2, step=0.05)
    random_state = st.number_input("Random state", min_value=0, value=42, step=1)

    if st.button("Train Linear Regression", type="primary"):
        try:
            with st.spinner(f"Training and writing {display_path(output_dir / MODEL_FILENAME)} ..."):
                trained_model_path = train_model_from_sidebar(
                    salary_path=salary_path,
                    output_dir=output_dir,
                    top_skills=top_skills,
                    min_skill_count=min_skill_count,
                    test_size=float(test_size),
                    random_state=int(random_state),
                )
            model_path = trained_model_path
            st.success(f"Model written: {display_path(trained_model_path)}")
            st.dataframe(artifact_status(output_dir), use_container_width=True)
        except Exception as exc:  # pragma: no cover - Streamlit UI guard
            st.error(f"Train failed: {exc}")

if not model_path.exists():
    st.warning("No model file yet. Train locally from terminal first, or use the sidebar train button.")
    st.code(
        "python -m modeling.salary_regression --input data/analysis/salary_analysis_clean.csv --output-dir data/modeling/salary_regression",
        language="bash",
    )
    st.code(
        ".\\scripts\\train_salary_regression.ps1",
        language="powershell",
    )
    st.stop()

try:
    bundle = cached_load_model(str(model_path))
except Exception as exc:  # pragma: no cover - Streamlit UI guard
    st.error(f"Could not load model: {exc}")
    st.stop()

predict_tab, explain_tab, usage_tab = st.tabs(["Predict", "Model", "Usage"])

with predict_tab:
    st.subheader("Nhap thong tin job")

    source_options = option_list(bundle, "source", ["topcv", "itviec"])
    location_options = option_list(bundle, "location_norm", ["Ha Noi", "Ho Chi Minh", "Da Nang"])
    seniority_options = ["Unknown", *option_list(bundle, "seniority", ["intern", "junior", "middle", "senior", "lead"])]
    seniority_options = list(dict.fromkeys(seniority_options))
    work_mode_options = option_list(bundle, "work_mode", ["onsite", "hybrid", "remote"])

    left, right = st.columns(2)
    with left:
        source = st.selectbox("Source", options=source_options)
        location = st.selectbox("Location", options=location_options)
        default_seniority_index = seniority_options.index("middle") if "middle" in seniority_options else 0
        seniority = st.selectbox("Seniority", options=seniority_options, index=default_seniority_index)
        work_mode = st.selectbox("Work mode", options=work_mode_options)
    with right:
        experience_min = st.slider("Minimum experience, years", min_value=0.0, max_value=12.0, value=2.0, step=0.5)
        posted_age_days = st.slider("Posted age days", min_value=0, max_value=90, value=7)
        top_skill_options = bundle.get("top_skills", [])
        selected_skills = st.multiselect("Top skills in JD", options=top_skill_options, default=top_skill_options[:2])
        extra_skill_count = st.slider("Other skill count", min_value=0, max_value=15, value=0)

    prediction_frame = build_prediction_frame(
        bundle,
        source=source,
        location=location,
        seniority=None if seniority == "Unknown" else seniority,
        work_mode=work_mode,
        experience_min=float(experience_min),
        posted_age_days=float(posted_age_days),
        selected_skills=list(selected_skills),
        extra_skill_count=int(extra_skill_count),
    )
    prediction = predict_salary_million_vnd(bundle, prediction_frame)

    st.metric(
        "Predicted salary",
        f"{prediction['predicted_salary_million_vnd']:.1f} million VND/month",
    )
    st.caption(f"Predicted log salary: {prediction['predicted_log_salary']:.4f}")

    with st.expander("Feature row sent to model"):
        st.dataframe(prediction_frame, use_container_width=True)

with explain_tab:
    st.subheader("Model artifact")
    st.write(f"Model file: `{display_path(model_path)}`")
    st.write(f"Model type: `{bundle.get('model_type', 'LinearRegression')}`")
    st.write(f"Train rows: `{bundle.get('train_rows')}` | Test rows: `{bundle.get('test_rows')}`")
    st.code("log_salary = intercept + coefficient_1*x_1 + coefficient_2*x_2 + ...", language="text")

    metrics = bundle.get("metrics")
    if isinstance(metrics, pd.DataFrame):
        st.subheader("Metrics")
        st.dataframe(metrics, use_container_width=True)

    coefficients = bundle.get("coefficients")
    if isinstance(coefficients, pd.DataFrame) and not coefficients.empty:
        st.subheader("Largest coefficients")
        display_columns = [
            column
            for column in ["feature", "coefficient", "abs_coefficient"]
            if column in coefficients.columns
        ]
        st.dataframe(coefficients[display_columns].head(30), use_container_width=True)

        signed = coefficients.sort_values("coefficient")
        chart_data = pd.concat([signed.head(10), signed.tail(10)]).drop_duplicates("feature")
        st.bar_chart(chart_data.set_index("feature")["coefficient"])

    audit = bundle.get("audit")
    if isinstance(audit, pd.DataFrame):
        st.subheader("Data audit")
        st.dataframe(audit, use_container_width=True)

    st.subheader("Artifact files")
    st.dataframe(artifact_status(model_path.parent), use_container_width=True)

with usage_tab:
    st.subheader("Train model")
    st.markdown("Main path: train locally from terminal in the repo root.")
    st.code(
        "python -m modeling.salary_regression --input data/analysis/salary_analysis_clean.csv --output-dir data/modeling/salary_regression",
        language="bash",
    )
    st.markdown("Windows helper script:")
    st.code(".\\scripts\\train_salary_regression.ps1", language="powershell")
    st.markdown("The notebook is optional for review/teaching only, not the required training path.")

    st.subheader("Run Streamlit")
    st.code("streamlit run streamlit_salary_regression_opencode.py", language="bash")

    st.subheader("Training outputs")
    st.markdown(
        """
- `data/modeling/salary_regression/model.joblib`: trained Linear Regression bundle.
- `data/modeling/salary_regression/metrics.csv`: MAE, RMSE, R2.
- `data/modeling/salary_regression/predictions_test.csv`: actual vs predicted on the test set.
- `data/modeling/salary_regression/coefficients.csv`: coefficients for inspection.
- `data/modeling/salary_regression/data_audit.csv`: rows, feature counts, missing rates, and top skill counts.
"""
    )
