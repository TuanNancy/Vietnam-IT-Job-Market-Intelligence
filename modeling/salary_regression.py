from __future__ import annotations

import argparse
import ast
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import joblib
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, median_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DEFAULT_INPUT = Path("data/analysis/salary_analysis_clean.csv")
DEFAULT_OUTPUT_DIR = Path("data/modeling/salary_regression")
DEFAULT_USD_TO_VND = 26_000
MODEL_FILENAME = "model.joblib"
ARTIFACT_FILENAMES = [MODEL_FILENAME, "metrics.csv", "predictions_test.csv", "coefficients.csv", "data_audit.csv"]
TARGET_COLUMN = "log_salary_monthly_vnd"

REQUIRED_COLUMNS = [
    "source",
    "url",
    "title",
    "company",
    "location",
    "salary_raw",
    "salary_currency",
    "salary_period",
    "salary_midpoint",
    "skills",
    "experience_min",
    "seniority",
    "work_mode",
    "scraped_at",
    "posted_at",
]

CATEGORICAL_FEATURES = ["source", "location_norm", "seniority", "work_mode"]
NUMERIC_FEATURES = ["experience_min", "skill_count", "posted_age_days"]
LEAKAGE_COLUMNS = {
    "salary_raw",
    "salary_min",
    "salary_max",
    "salary_midpoint",
    "salary_currency",
    "salary_period",
    "salary_period_clean",
    "salary_label",
    "salary_monthly_vnd",
    "salary_monthly_vnd_m",
    TARGET_COLUMN,
}

SKILL_ALIASES = {
    "js": "javascript",
    "reactjs": "react",
    "react.js": "react",
    "vuejs": "vue",
    "vue.js": "vue",
    "node": "node.js",
    "nodejs": "node.js",
    "golang": "go",
    "postgres": "postgresql",
    "k8s": "kubernetes",
    "ts": "typescript",
    "csharp": "c#",
    "dotnet": ".net",
    "html5": "html",
    "css3": "css",
}


@dataclass(frozen=True)
class SalaryModelingData:
    frame: pd.DataFrame
    feature_columns: list[str]
    target_column: str
    numeric_features: list[str]
    categorical_features: list[str]
    skill_features: list[str]
    top_skills: list[str]
    audit: pd.DataFrame


@dataclass(frozen=True)
class SalaryRegressionResult:
    pipeline: Pipeline
    modeling_data: SalaryModelingData
    metrics: pd.DataFrame
    predictions: pd.DataFrame
    coefficients: pd.DataFrame
    train_rows: int
    test_rows: int


def strip_accents(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).replace("Đ", "D").replace("đ", "d")
    return "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if unicodedata.category(character) != "Mn"
    )


def fold_text(value: Any) -> str:
    return re.sub(r"\s+", " ", strip_accents(value).casefold()).strip()


def clean_text_series(series: pd.Series) -> pd.Series:
    cleaned = series.astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
    return cleaned.mask(cleaned.eq(""), pd.NA)


def normalize_location(value: Any) -> str:
    folded = fold_text(value)
    if re.search(r"\b(?:tp\.?\s*)?(?:hcm|ho chi minh|thanh pho ho chi minh|sai gon)\b", folded):
        return "Ho Chi Minh"
    if re.search(r"\b(?:ha noi|hanoi)\b", folded):
        return "Ha Noi"
    if re.search(r"\b(?:da nang|danang)\b", folded):
        return "Da Nang"
    if not folded or folded == "nan":
        return "Unknown"
    return str(value).strip()


def to_listish(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if pd.isna(value):
        return []
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def normalize_skill(value: Any) -> str:
    folded = fold_text(value).replace("&", " and ")
    folded = re.sub(r"\s+", " ", folded).strip()
    return SKILL_ALIASES.get(folded, folded)


def skill_column_name(skill: str) -> str:
    safe = skill.replace("#", " sharp ").replace("+", " plus ")
    safe = re.sub(r"[^a-z0-9]+", "_", fold_text(safe)).strip("_")
    return f"skill__{safe or 'unknown'}"


def validate_required_columns(frame: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(f"Missing required salary modeling columns: {missing_text}")


def _one_hot_encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:  # pragma: no cover - compatibility for older local sklearn installs
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def select_top_skills(frame: pd.DataFrame, top_skills: int = 30, min_skill_count: int = 5) -> list[str]:
    counter: Counter[str] = Counter()
    for skills in frame["skills_norm_list"]:
        counter.update(set(skills))
    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return [skill for skill, count in ranked if count >= min_skill_count][:top_skills]


def add_skill_flags(frame: pd.DataFrame, top_skills: list[str]) -> tuple[pd.DataFrame, list[str]]:
    output = frame.copy()
    columns: list[str] = []
    used_columns: set[str] = set()
    for skill in top_skills:
        base_column = skill_column_name(skill)
        column = base_column
        suffix = 2
        while column in used_columns:
            column = f"{base_column}_{suffix}"
            suffix += 1
        used_columns.add(column)
        columns.append(column)
        output[column] = output["skills_norm_list"].apply(lambda values, skill=skill: int(skill in values))
    return output, columns


def prepare_salary_modeling_data(
    frame: pd.DataFrame,
    *,
    top_skills: int = 30,
    min_skill_count: int = 5,
    usd_to_vnd: int = DEFAULT_USD_TO_VND,
) -> SalaryModelingData:
    validate_required_columns(frame)
    original_rows = len(frame)
    output = frame.copy()

    text_columns = [
        "source",
        "url",
        "title",
        "company",
        "location",
        "salary_raw",
        "salary_currency",
        "salary_period",
        "skills",
        "seniority",
        "work_mode",
    ]
    for column in text_columns:
        output[column] = clean_text_series(output[column])

    output["salary_midpoint"] = pd.to_numeric(output["salary_midpoint"], errors="coerce")
    output["experience_min"] = pd.to_numeric(output["experience_min"], errors="coerce")
    output["scraped_at_dt"] = pd.to_datetime(output["scraped_at"], errors="coerce", utc=True, format="mixed")
    output["posted_at_dt"] = pd.to_datetime(output["posted_at"], errors="coerce", utc=True, format="mixed")
    output["posted_age_days"] = (output["scraped_at_dt"] - output["posted_at_dt"]).dt.days

    salary_raw_folded = output["salary_raw"].map(fold_text)
    raw_has_annual_signal = salary_raw_folded.str.contains(
        r"\b(?:year|annual|annually|nam)\b",
        na=False,
    )
    output["salary_period_clean"] = output["salary_period"].astype("string").str.casefold().str.strip()
    year_without_annual_signal = output["salary_period_clean"].eq("year") & ~raw_has_annual_signal
    output.loc[year_without_annual_signal, "salary_period_clean"] = "month"

    output["salary_monthly_vnd"] = output["salary_midpoint"]
    usd_mask = output["salary_currency"].astype("string").str.upper().eq("USD")
    annual_mask = output["salary_period_clean"].eq("year") & raw_has_annual_signal
    output.loc[usd_mask, "salary_monthly_vnd"] = output.loc[usd_mask, "salary_monthly_vnd"] * usd_to_vnd
    output.loc[annual_mask, "salary_monthly_vnd"] = output.loc[annual_mask, "salary_monthly_vnd"] / 12
    output["salary_monthly_vnd_m"] = output["salary_monthly_vnd"] / 1_000_000

    output["location_norm"] = output["location"].map(normalize_location).astype("string")
    output["skills_list"] = output["skills"].apply(to_listish)
    output["skills_norm_list"] = output["skills_list"].apply(
        lambda values: sorted({normalize_skill(value) for value in values if normalize_skill(value)})
    )
    output["skill_count"] = output["skills_norm_list"].str.len()

    valid_salary = output["salary_monthly_vnd"].notna() & output["salary_monthly_vnd"].gt(0)
    output = output.loc[valid_salary].copy()
    output[TARGET_COLUMN] = np.log(output["salary_monthly_vnd"])

    selected_skills = select_top_skills(output, top_skills=top_skills, min_skill_count=min_skill_count)
    output, skill_columns = add_skill_flags(output, selected_skills)
    feature_columns = [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES, *skill_columns]

    leakage_overlap = sorted(set(feature_columns) & LEAKAGE_COLUMNS)
    if leakage_overlap:
        raise AssertionError(f"Leakage columns included as features: {leakage_overlap}")

    audit_rows: list[dict[str, Any]] = [
        {"metric": "input_rows", "value": original_rows},
        {"metric": "modeling_rows", "value": len(output)},
        {"metric": "dropped_invalid_salary_rows", "value": int(original_rows - len(output))},
        {"metric": "usd_to_vnd", "value": usd_to_vnd},
        {"metric": "salary_period_year_without_annual_signal", "value": int(year_without_annual_signal.sum())},
        {"metric": "salary_period_annual_signal_rows", "value": int(raw_has_annual_signal.sum())},
        {"metric": "top_skill_count", "value": len(selected_skills)},
        {"metric": "feature_count", "value": len(feature_columns)},
    ]
    for column in [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]:
        audit_rows.append({"metric": f"missing_rate_{column}", "value": round(float(output[column].isna().mean()), 4)})
    for skill in selected_skills:
        audit_rows.append({"metric": f"top_skill_jobs_{skill}", "value": int(output["skills_norm_list"].apply(lambda values, skill=skill: skill in values).sum())})

    return SalaryModelingData(
        frame=output,
        feature_columns=feature_columns,
        target_column=TARGET_COLUMN,
        numeric_features=list(NUMERIC_FEATURES),
        categorical_features=list(CATEGORICAL_FEATURES),
        skill_features=skill_columns,
        top_skills=selected_skills,
        audit=pd.DataFrame(audit_rows),
    )


def build_linear_regression_pipeline(modeling_data: SalaryModelingData) -> Pipeline:
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value="Unknown")),
            ("onehot", _one_hot_encoder()),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, modeling_data.numeric_features),
            ("categorical", categorical_pipeline, modeling_data.categorical_features),
            ("skill", "passthrough", modeling_data.skill_features),
        ]
    )
    return Pipeline(
        steps=[
            ("preprocess", preprocessor),
            ("model", LinearRegression()),
        ]
    )


def _feature_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    features = frame[columns].copy().astype(object)
    return features.where(features.notna(), np.nan)


def _train_test_indices(frame: pd.DataFrame, *, test_size: float, random_state: int) -> tuple[pd.Index, pd.Index]:
    indices = frame.index.to_numpy()
    stratify = frame["source"] if frame["source"].value_counts(dropna=False).min() >= 2 else None
    try:
        train_index, test_index = train_test_split(
            indices,
            test_size=test_size,
            random_state=random_state,
            stratify=stratify,
        )
    except ValueError:
        train_index, test_index = train_test_split(indices, test_size=test_size, random_state=random_state)
    return pd.Index(train_index), pd.Index(test_index)


def _metric_row(scope: str, group_column: str, group_value: str, y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    actual_m = np.exp(y_true) / 1_000_000
    predicted_m = np.exp(y_pred) / 1_000_000
    return {
        "scope": scope,
        "group_column": group_column,
        "group_value": group_value,
        "n": len(y_true),
        "mae_log": mean_absolute_error(y_true, y_pred),
        "rmse_log": math.sqrt(mean_squared_error(y_true, y_pred)),
        "r2_log": r2_score(y_true, y_pred) if len(y_true) > 1 else np.nan,
        "mae_million_vnd": mean_absolute_error(actual_m, predicted_m),
        "rmse_million_vnd": math.sqrt(mean_squared_error(actual_m, predicted_m)),
        "median_abs_error_million_vnd": median_absolute_error(actual_m, predicted_m),
    }


def build_metrics(test_frame: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray, *, min_group_size: int = 2) -> pd.DataFrame:
    rows = [_metric_row("overall", "", "", y_true, y_pred)]
    scored = test_frame[["source", "seniority"]].copy()
    scored["y_true"] = y_true
    scored["y_pred"] = y_pred
    for column in ["source", "seniority"]:
        for value, group in scored.groupby(column, dropna=False):
            if len(group) < min_group_size:
                continue
            rows.append(
                _metric_row(
                    "group",
                    column,
                    "Unknown" if pd.isna(value) else str(value),
                    group["y_true"].to_numpy(),
                    group["y_pred"].to_numpy(),
                )
            )
    return pd.DataFrame(rows)


def build_predictions(test_frame: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray) -> pd.DataFrame:
    predictions = test_frame[
        ["url", "title", "company", "source", "location", "location_norm", "seniority", "experience_min"]
    ].copy()
    predictions["actual_log_salary"] = y_true
    predictions["predicted_log_salary"] = y_pred
    predictions["actual_salary_million_vnd"] = np.exp(y_true) / 1_000_000
    predictions["predicted_salary_million_vnd"] = np.exp(y_pred) / 1_000_000
    predictions["residual_million_vnd"] = predictions["actual_salary_million_vnd"] - predictions["predicted_salary_million_vnd"]
    predictions["abs_error_million_vnd"] = predictions["residual_million_vnd"].abs()
    return predictions.sort_values("abs_error_million_vnd", ascending=False).reset_index(drop=True)


def build_coefficients(pipeline: Pipeline) -> pd.DataFrame:
    preprocessor = pipeline.named_steps["preprocess"]
    model = pipeline.named_steps["model"]
    try:
        feature_names = list(preprocessor.get_feature_names_out())
    except AttributeError:  # pragma: no cover - older sklearn fallback
        feature_names = [f"feature_{index}" for index in range(len(model.coef_))]
    coefficients = pd.DataFrame(
        {
            "feature": feature_names,
            "coefficient": model.coef_,
        }
    )
    coefficients["abs_coefficient"] = coefficients["coefficient"].abs()
    return coefficients.sort_values("abs_coefficient", ascending=False).reset_index(drop=True)


def fit_salary_linear_regression(
    modeling_data: SalaryModelingData,
    *,
    test_size: float = 0.2,
    random_state: int = 42,
) -> SalaryRegressionResult:
    frame = modeling_data.frame
    if len(frame) < 5:
        raise ValueError("Need at least 5 salary rows to fit a train/test Linear Regression baseline")

    train_index, test_index = _train_test_indices(frame, test_size=test_size, random_state=random_state)
    train_frame = frame.loc[train_index].copy()
    test_frame = frame.loc[test_index].copy()

    pipeline = build_linear_regression_pipeline(modeling_data)
    x_train = _feature_frame(train_frame, modeling_data.feature_columns)
    x_test = _feature_frame(test_frame, modeling_data.feature_columns)
    y_train = train_frame[modeling_data.target_column].to_numpy()
    y_test = test_frame[modeling_data.target_column].to_numpy()

    pipeline.fit(x_train, y_train)
    y_pred = pipeline.predict(x_test)

    return SalaryRegressionResult(
        pipeline=pipeline,
        modeling_data=modeling_data,
        metrics=build_metrics(test_frame, y_test, y_pred),
        predictions=build_predictions(test_frame, y_test, y_pred),
        coefficients=build_coefficients(pipeline),
        train_rows=len(train_frame),
        test_rows=len(test_frame),
    )


def run_salary_linear_regression(
    frame: pd.DataFrame,
    *,
    top_skills: int = 30,
    min_skill_count: int = 5,
    usd_to_vnd: int = DEFAULT_USD_TO_VND,
    test_size: float = 0.2,
    random_state: int = 42,
) -> SalaryRegressionResult:
    modeling_data = prepare_salary_modeling_data(
        frame,
        top_skills=top_skills,
        min_skill_count=min_skill_count,
        usd_to_vnd=usd_to_vnd,
    )
    return fit_salary_linear_regression(modeling_data, test_size=test_size, random_state=random_state)


def write_outputs(result: SalaryRegressionResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result.metrics.to_csv(output_dir / "metrics.csv", index=False, encoding="utf-8-sig")
    result.predictions.to_csv(output_dir / "predictions_test.csv", index=False, encoding="utf-8-sig")
    result.coefficients.to_csv(output_dir / "coefficients.csv", index=False, encoding="utf-8-sig")
    result.modeling_data.audit.to_csv(output_dir / "data_audit.csv", index=False, encoding="utf-8-sig")
    save_model_bundle(result, output_dir / MODEL_FILENAME)


def build_model_bundle(result: SalaryRegressionResult) -> dict[str, Any]:
    modeling_data = result.modeling_data
    frame = modeling_data.frame
    category_options = {
        column: sorted(frame[column].dropna().astype(str).unique().tolist())
        for column in modeling_data.categorical_features
    }
    return {
        "model_type": "LinearRegression",
        "target_column": modeling_data.target_column,
        "pipeline": result.pipeline,
        "feature_columns": modeling_data.feature_columns,
        "numeric_features": modeling_data.numeric_features,
        "categorical_features": modeling_data.categorical_features,
        "skill_features": modeling_data.skill_features,
        "top_skills": modeling_data.top_skills,
        "skill_feature_map": dict(zip(modeling_data.top_skills, modeling_data.skill_features, strict=False)),
        "category_options": category_options,
        "metrics": result.metrics,
        "coefficients": result.coefficients,
        "audit": modeling_data.audit,
        "train_rows": result.train_rows,
        "test_rows": result.test_rows,
        "usd_to_vnd": DEFAULT_USD_TO_VND,
    }


def save_model_bundle(result: SalaryRegressionResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(build_model_bundle(result), path)


def load_model_bundle(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {path}")
    bundle = joblib.load(path)
    if not isinstance(bundle, dict) or "pipeline" not in bundle:
        raise ValueError(f"Invalid salary model bundle: {path}")
    return bundle


def build_prediction_frame(
    bundle: dict[str, Any],
    *,
    source: str,
    location: str,
    seniority: str | None,
    work_mode: str,
    experience_min: float,
    posted_age_days: float = 7,
    selected_skills: list[str] | None = None,
    extra_skill_count: int = 0,
) -> pd.DataFrame:
    selected_skill_set = {
        normalize_skill(skill)
        for skill in (selected_skills or [])
        if normalize_skill(skill)
    }
    skill_feature_map = bundle.get("skill_feature_map") or dict(
        zip(bundle.get("top_skills", []), bundle.get("skill_features", []), strict=False)
    )
    row: dict[str, Any] = {
        "source": source,
        "location_norm": normalize_location(location),
        "seniority": seniority or np.nan,
        "work_mode": work_mode,
        "experience_min": experience_min,
        "skill_count": len(selected_skill_set) + max(0, int(extra_skill_count)),
        "posted_age_days": posted_age_days,
    }
    for column in bundle.get("skill_features", []):
        row[column] = 0
    for skill in selected_skill_set:
        column = skill_feature_map.get(skill)
        if column:
            row[column] = 1
    frame = pd.DataFrame([row])
    return _feature_frame(frame, list(bundle["feature_columns"]))


def predict_salary_million_vnd(bundle: dict[str, Any], prediction_frame: pd.DataFrame) -> dict[str, float]:
    predicted_log_salary = float(bundle["pipeline"].predict(prediction_frame)[0])
    predicted_salary_million_vnd = float(np.exp(predicted_log_salary) / 1_000_000)
    return {
        "predicted_log_salary": predicted_log_salary,
        "predicted_salary_million_vnd": predicted_salary_million_vnd,
    }


def print_metrics(metrics: pd.DataFrame) -> None:
    overall = metrics.loc[metrics["scope"].eq("overall")].iloc[0]
    print("Linear Regression salary baseline")
    print(f"Rows in test set: {int(overall['n'])}")
    print(f"MAE log salary: {overall['mae_log']:.4f}")
    print(f"RMSE log salary: {overall['rmse_log']:.4f}")
    print(f"R2 log salary: {overall['r2_log']:.4f}")
    print(f"MAE: {overall['mae_million_vnd']:.2f} million VND/month")
    print(f"RMSE: {overall['rmse_million_vnd']:.2f} million VND/month")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a salary Linear Regression baseline.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-skills", type=int, default=30)
    parser.add_argument("--min-skill-count", type=int, default=5)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--usd-to-vnd", type=int, default=DEFAULT_USD_TO_VND)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frame = pd.read_csv(args.input, encoding="utf-8-sig")
    result = run_salary_linear_regression(
        frame,
        top_skills=args.top_skills,
        min_skill_count=args.min_skill_count,
        usd_to_vnd=args.usd_to_vnd,
        test_size=args.test_size,
        random_state=args.random_state,
    )
    write_outputs(result, args.output_dir)
    print_metrics(result.metrics)
    print(f"Outputs: {args.output_dir}")
    print(f"Model file: {args.output_dir / MODEL_FILENAME}")
    print("Artifacts:")
    for filename in ARTIFACT_FILENAMES:
        print(f"- {args.output_dir / filename}")


if __name__ == "__main__":
    main()
