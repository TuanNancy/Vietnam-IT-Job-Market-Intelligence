# Salary Linear Regression Implementation Plan

## Scope Decisions

- Phase 1 is salary prediction only. Demand forecasting is out of scope.
- Use only Linear Regression for modeling because the goal is learning and understanding the method.
- Add `scikit-learn` to run a standard `LinearRegression` pipeline with preprocessing, train/test split, metrics, and coefficients.
- Do not add Ridge, Lasso, Random Forest, XGBoost, Poisson, or `DummyRegressor` in this phase.
- Do not modify crawlers, parsers, raw data, processed data, or existing analysis CSVs.
- Do not create `.opencode` files. The plan remains in `.kilo/plans`.

## Current Context

- Salary input: `data/analysis/salary_analysis_clean.csv`.
- Current salary subset has 504 numeric salary rows: 202 from `itviec`, 302 from `topcv`.
- Full analysis inventory has 1,433 unique job URLs, but only 504 numeric salary jobs, so the model is biased toward postings that disclose salary.
- TopDev has no numeric salary in current data, so it is excluded from salary modeling.
- `notebooks/03_salary_visualization_matplotlib_seaborn.ipynb` has been updated and run by the user.
- `notebooks/04_salary_linear_regression_baseline.ipynb` already exists, so the new notebook must not use that exact name.

## Files To Change Or Add

- Update `requirements.txt`:
  - Add `scikit-learn>=1.5.0`.
- Add reusable package:
  - `modeling/__init__.py`
  - `modeling/salary_regression.py`
- Add tests:
  - `tests/test_salary_regression.py`
- Add learning notebook:
  - `notebooks/04_salary_linear_regression_cli_kilocode.ipynb`

## Data Preparation

Implement reusable preprocessing in `modeling/salary_regression.py`; the notebook should import and call these functions instead of duplicating all logic.

Required input columns:

- `source`, `url`, `title`, `company`, `location`, `salary_raw`, `salary_currency`, `salary_period`, `salary_midpoint`, `skills`, `experience_min`, `seniority`, `work_mode`, `scraped_at`, `posted_at`.

Target construction:

- Convert `salary_midpoint` to numeric.
- Create `salary_period_clean`:
  - If `salary_period == "year"` but `salary_raw` has no annual signal such as `year`, `annual`, `annually`, or `nam`, treat it as `month` and record this in the audit output.
  - If `salary_period_clean == "year"` and an annual signal exists, divide by 12.
- Create `salary_monthly_vnd`:
  - VND stays as-is.
  - USD is multiplied by `USD_TO_VND = 26000` by default.
- Drop rows where monthly salary is missing or non-positive.
- Create target `log_salary_monthly_vnd = log(salary_monthly_vnd)`.

Feature construction:

- Categorical features:
  - `source`
  - `location_norm` derived from `location`, not `location_cities`
  - `seniority`
  - `work_mode`
- Numeric features:
  - `experience_min`
  - `skill_count`
  - `posted_age_days`, computed from `scraped_at - posted_at`
- Skill features:
  - Parse `skills` into a list.
  - Normalize common aliases already used in notebook 03, such as `js -> javascript`, `reactjs -> react`, `nodejs -> node.js`, `golang -> go`, `postgres -> postgresql`, `k8s -> kubernetes`, `ts -> typescript`, `dotnet -> .net`.
  - Create binary flags for top skills only.
  - Default to top 30 skills, with CLI options `--top-skills` and `--min-skill-count`.

Leakage guardrails:

- Never use these as features: `salary_raw`, `salary_min`, `salary_max`, `salary_midpoint`, `salary_currency`, `salary_period`, `salary_period_clean`, `salary_label`, `salary_monthly_vnd`, `log_salary_monthly_vnd`.
- Keep leakage-prone columns only for audit/display/prediction output.

## Linear Regression Design

Use a scikit-learn pipeline for one model only: `sklearn.linear_model.LinearRegression`.

Preprocessing:

- Numeric pipeline: `SimpleImputer(strategy="median")` then `StandardScaler()`.
- Categorical pipeline: `SimpleImputer(strategy="constant", fill_value="Unknown")` then `OneHotEncoder(handle_unknown="ignore")`.
- Skill flags are numeric binary columns.

Split:

- Use `train_test_split(test_size=0.2, random_state=42)`.
- Stratify by `source` when possible; otherwise fall back to a non-stratified split.

Metrics:

- On log target:
  - `mae_log`
  - `rmse_log`
  - `r2_log`
- On original VND scale after `exp()`:
  - `mae_million_vnd`
  - `rmse_million_vnd`
  - `median_abs_error_million_vnd`
- Group diagnostics:
  - Metrics by `source`.
  - Metrics by `seniority` when enough rows exist.

Interpretability:

- Extract coefficients from the fitted Linear Regression pipeline using feature names from the preprocessor.
- Sort coefficients by absolute magnitude.
- In the notebook, explain that coefficients describe associations under this model, not causal effects.

## CLI Design

Implement executable module:

```bash
python -m modeling.salary_regression --input data/analysis/salary_analysis_clean.csv --output-dir data/modeling/salary_regression
```

Arguments:

- `--input`, default `data/analysis/salary_analysis_clean.csv`
- `--output-dir`, default `data/modeling/salary_regression`
- `--top-skills`, default `30`
- `--min-skill-count`, default `5`
- `--test-size`, default `0.2`
- `--random-state`, default `42`
- `--usd-to-vnd`, default `26000`

CLI outputs:

- Print concise Linear Regression metrics to stdout.
- Write `metrics.csv`.
- Write `predictions_test.csv` with URL/title/source/company plus actual and predicted salary in million VND.
- Write `coefficients.csv`.
- Write `data_audit.csv` with row counts, dropped rows, period-cleaning counts, top-skill counts, and missing-rate summary.

Do not persist a pickle/joblib model in phase 1.

## Notebook Design

Create `notebooks/04_salary_linear_regression_cli_kilocode.ipynb` with these sections:

1. Objective and caveats.
2. Load salary data and show source/currency/seniority coverage.
3. Reuse module preprocessing to build monthly VND target and model features.
4. Explain why the target is `log_salary_monthly_vnd`.
5. Create train/test split.
6. Train `LinearRegression` only.
7. Evaluate metrics on log and VND scales.
8. Inspect predictions and largest residuals.
9. Inspect coefficients and explain what positive/negative coefficients mean.
10. Conclude with limitations and next learning steps.

Notebook caveats to state clearly:

- This is a salary baseline, not a market-wide salary truth.
- Numeric salary rows are only 504 of 1,433 unique jobs.
- TopDev is excluded because it has no numeric salary.
- The model learns associations from current scraped postings, not causal salary drivers.

## Tests

Add `tests/test_salary_regression.py` covering:

- Salary conversion:
  - USD monthly midpoint converts to VND.
  - VND monthly midpoint stays in VND.
  - `salary_period == "year"` without annual signal is cleaned to `month`.
  - Annual signal rows are divided by 12.
- Feature prep:
  - Location normalization maps HCM, Ha Noi, and Da Nang variants.
  - Skill aliases normalize expected variants.
  - Top-skill flag columns are deterministic.
  - Leakage fields are excluded from feature columns.
- Modeling:
  - Training returns Linear Regression metrics.
  - Predictions are positive after inverse log transform.
  - Coefficients can be produced from the fitted pipeline.
- CLI/write path:
  - Use a temporary CSV and output directory.
  - Confirm `metrics.csv`, `predictions_test.csv`, `coefficients.csv`, and `data_audit.csv` are created.

## Validation Commands

Run after implementation:

```bash
pip install -r requirements.txt
python -m compileall scrapers parsers modeling
python -m unittest tests.test_salary_regression
python -m unittest discover tests
python -m modeling.salary_regression --input data/analysis/salary_analysis_clean.csv --output-dir data/modeling/salary_regression
```

Manual validation:

- Inspect `metrics.csv` and confirm metrics are finite and reasonable.
- Inspect `predictions_test.csv` for impossible-looking predictions.
- Inspect `coefficients.csv` and confirm feature names are readable.
- Inspect `data_audit.csv` and confirm row counts align with the known 504 numeric salary rows.
- Open `notebooks/04_salary_linear_regression_cli_kilocode.ipynb` and run all cells top to bottom.

## Risks And Constraints

- Current salary model is biased toward postings with disclosed salary.
- Source and currency are highly confounded: ITviec is mostly USD, TopCV is mostly VND.
- Current `salary_period = year` issue should be audited in preprocessing but fixed in parser in a separate phase.
- With only 504 rows, coefficients can be unstable, especially rare skill flags.
- Do not claim this model predicts the whole Vietnam IT market.
- Demand forecasting remains out of scope until there are more consistent weekly snapshots.

## Acceptance Criteria

- `scikit-learn` is added to dependencies.
- Salary modeling code is importable and executable via `python -m modeling.salary_regression`.
- Only `LinearRegression` is trained; no Ridge, Lasso, tree model, XGBoost, Poisson, or `DummyRegressor` is introduced.
- Notebook `notebooks/04_salary_linear_regression_cli_kilocode.ipynb` runs from repo root or notebook directory using repo-root discovery.
- Tests pass with `python -m unittest discover tests`.
- CLI produces metrics, predictions, coefficients, and audit CSVs without modifying raw/processed/parser outputs.
- Notebook clearly explains Linear Regression and does not overstate forecasting reliability.
