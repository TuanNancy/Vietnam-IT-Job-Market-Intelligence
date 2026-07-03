# Pandas Data Cleaning Learning Plan

## Scope Decision

- Scope: notebook-only.
- Primary file to update during implementation: `notebooks/01_data_inventory_eda.ipynb`.
- Do not edit parser, crawler, tests, raw data, processed data, or report files for this plan.
- Do not export cleaned CSV/JSONL by default. Build clean pandas DataFrames in memory for learning and analysis.
- If a cleaning rule looks useful for production, document it in a notebook TODO/audit cell instead of changing parser code.

## Current Context

- The existing notebook already loads all `data/processed/*_clean.csv`, converts numeric/date columns for EDA, checks schema/fill-rate, inspects duplicate URLs, salary coverage, TopDev salary limitations, skills demand, and current data checks.
- Current processed CSV inventory has 8 clean CSV files, 1,662 loaded rows, 1,433 unique URLs, 421 rows in duplicate URL groups, and 1,433 rows after URL dedupe.
- All loaded rows currently have `parse_status == "ok"`.
- Deduped source coverage is currently:
- `itviec`: 750 rows, numeric salary rate 0.276, skills fill 1.0, experience fill 0.8773, description fill 1.0, location fill 1.0.
- `topcv`: 583 rows, numeric salary rate 0.5232, skills fill 0.7787, experience fill 0.8491, description fill 1.0, location fill 1.0.
- `topdev`: 100 rows, numeric salary rate 0.0, skills fill 1.0, experience fill 0.83, description fill 1.0, location fill 1.0.
- Current EDA flags 8 suspicious numeric salary rows.
- Hidden or non-numeric salary labels are expected data states, not parser failures: ITviec `You'll love it`, TopDev `Login to view salary`, TopCV `Thoả thuận`/missing.

## Goal

Extend the notebook with a structured data-cleaning learning path that teaches pandas methods while producing analysis-ready in-memory views:

- `jobs_all`: all loaded rows, preserving duplicates and `_input_file`.
- `duplicate_audit`: duplicate URL groups with quality/tie-break details.
- `jobs_clean`: canonical one-row-per-URL DataFrame with normalized helper columns.
- `salary_for_analysis`: salary-safe subset excluding hidden, missing, and suspicious salary rows.
- `skills_long`: exploded one-row-per-job-skill table with normalized skill names.
- `issues_long`: row-level data-quality issue log for inspection.
- `quality_by_source`: source-level quality summary after cleaning.

## Design Principles

- Preserve raw columns. Add derived columns such as `*_clean`, `*_norm`, `*_parsed`, `_flag_*`, `_reason_*`, or `_quality_*` instead of overwriting original fields.
- Prefer explicit flags over silent correction. For example, do not clip unrealistic salary values; flag them and exclude from salary analysis.
- Treat hidden/negotiable salary as known missingness. Keep it useful for coverage reporting but exclude it from numeric salary summaries.
- Use pandas idioms that are teachable and repeatable: `.assign()`, `.pipe()`, `.loc[]`, `.where()`, `.mask()`, `.groupby().agg()`, `.explode()`, `.melt()`, `.value_counts()`, and `.query()`.
- Keep parser responsibilities separate. Notebook cleaning can audit and prototype rules, but production extraction/normalization stays in `parsers/*` unless a future implementation explicitly changes scope.

## Notebook Structure To Add

### 1. Add A Cleaning Roadmap Section

Add a markdown section after the current EDA checks explaining:

- The notebook is moving from inventory EDA to cleaning/audit.
- Inputs remain read-only.
- Outputs are in-memory DataFrames.
- Each section has three parts: data goal, pandas methods to learn, and validation checks.

Pandas methods to introduce:

- `DataFrame.copy()` for safe working copies.
- `DataFrame.pipe()` for chaining named cleaning steps.
- `DataFrame.assign()` for adding derived columns without mutating many lines manually.

### 2. Create A Schema Contract Cell

Build a cell that checks required columns against the parser schema and creates `jobs_all` from the already-loaded `jobs` DataFrame.

Implementation shape:

- Define `required_columns` from the known clean field list in the notebook, not by importing parser code unless already convenient.
- Compute `missing_columns` and `extra_columns`.
- Display a schema contract table.
- Assert that required columns are present before cleaning continues.

Pandas methods to teach:

- `pd.Index()`.
- `Index.difference()`.
- `DataFrame.reindex()`.
- `DataFrame.dtypes`.
- `DataFrame.convert_dtypes()`.

Validation checks:

- Required clean columns are present.
- `_input_file` exists.
- Row count of `jobs_all` equals the current loaded row count.

### 3. Standardize Missing Values And Text Whitespace

Create helper functions that normalize object/string columns for notebook analysis only.

Rules:

- Strip leading/trailing whitespace from string columns.
- Convert empty strings and obvious placeholder strings such as `""`, `"nan"`, `"None"`, and `"<NA>"` to pandas missing values when they are true placeholders.
- Do not convert meaningful salary labels such as `You'll love it`, `Login to view salary`, `Thoả thuận`, `Thỏa thuận`, `Negotiable`, or `Very Attractive!!!` to generic missing before salary classification.
- Preserve original fields and create normalized helper columns only where useful.

Pandas methods to teach:

- `DataFrame.select_dtypes()`.
- `Series.astype("string")`.
- `Series.str.strip()`.
- `Series.replace()`.
- `Series.where()`.
- `Series.mask()`.
- `DataFrame.isna()` and `DataFrame.notna()`.

Validation checks:

- No blank-only values remain in key normalized text columns.
- Raw columns remain available for comparison.

### 4. Normalize Dtypes For Analysis

Add a dtype-cleaning section that makes analysis dtypes explicit.

Rules:

- Numeric columns: `salary_min`, `salary_max`, `experience_min`, `experience_max` with `pd.to_numeric(errors="coerce")`.
- Date columns: `scraped_at`, `posted_at`, `valid_through` with `pd.to_datetime(errors="coerce", utc=True)` into `*_parsed` columns.
- Category-like columns: `source`, `parse_status`, `salary_currency`, `salary_period`, `seniority`, `work_mode`, `employment_type` as `category` for exploration.
- Boolean helper columns use pandas nullable boolean if missingness is meaningful.

Pandas methods to teach:

- `pd.to_numeric()`.
- `pd.to_datetime()`.
- `Series.astype("category")`.
- `DataFrame.memory_usage(deep=True)`.
- `pd.api.types` dtype checks.

Validation checks:

- Numeric helper columns are numeric.
- Parsed date columns are datetime-like.
- Category columns have expected value counts.

### 5. Improve Duplicate URL Audit And Canonical Row Selection

Keep the current dedupe concept but make the selection rule easier to inspect and learn from.

Recommended canonical rule:

- Build `_quality_score_v2` from key field availability: numeric salary, skills, experience, description, location, company, title, parsed dates.
- Add `_is_test_or_sample_file` from `_input_file` using `.str.contains("test|sample", case=False)`.
- Prefer higher `_quality_score_v2`.
- Prefer non-test/sample files.
- Prefer latest `scraped_at_parsed` when available.
- Use `_input_file` as final deterministic tie-breaker.

Create:

- `duplicate_audit`: all duplicated URL rows with quality columns and selected flag.
- `jobs_clean`: deduped canonical rows.

Pandas methods to teach:

- `Series.duplicated(keep=False)`.
- `DataFrame.sort_values()`.
- `DataFrame.drop_duplicates()`.
- `DataFrame.groupby().agg()`.
- `GroupBy.transform()`.
- `Series.rank()` or deterministic sort keys.

Validation checks:

- `len(jobs_clean) == jobs_clean["url"].nunique()`.
- `len(jobs_clean)` equals current unique URL count unless input files change.
- Duplicate audit explains every dropped duplicate row.

### 6. Classify Salary Before Numeric Salary Analysis

Create salary status columns instead of treating every non-numeric salary as a problem.

Recommended columns:

- `salary_visibility`: one of `numeric`, `negotiable`, `hidden_login`, `attractive_label`, `missing`, `suspicious_numeric`.
- `salary_midpoint`: mean of min/max when at least one numeric bound exists.
- `_flag_salary_min_gt_max`.
- `_flag_salary_non_positive`.
- `_flag_salary_missing_currency`.
- `_flag_salary_outlier_by_currency`.
- `_salary_exclusion_reason`.

Rules:

- `TopDev` salary is normally `hidden_login`; exclude from numeric salary analysis but include in coverage reporting.
- ITviec `You'll love it` and similar labels are non-numeric visibility states.
- TopCV `Thoả thuận`/`Thỏa thuận`/`Negotiable` are negotiable.
- Numeric salary rows with missing currency are suspicious.
- Rows with `salary_min > salary_max`, non-positive values, or extreme currency-specific outliers are suspicious and excluded from `salary_for_analysis`.
- Do not mix currencies or periods in salary summaries.

Pandas methods to teach:

- `Series.str.contains()`.
- `Series.between()`.
- `DataFrame.query()`.
- `DataFrame.groupby().agg()`.
- `pd.cut()` for salary bands.
- `Series.value_counts(dropna=False)`.

Validation checks:

- Every row has exactly one `salary_visibility` value.
- `salary_for_analysis` contains only rows with numeric salary, non-suspicious flags, currency, and period.
- Salary summaries group by `source`, `salary_currency`, and `salary_period`.

### 7. Parse, Explode, And Normalize Skills

Build on the existing `parse_listish()` helper but add a cleaner teaching section.

Recommended outputs:

- `skills_list_raw`: parsed list from `skills`.
- `skills_list_clean`: normalized, de-duplicated list per job.
- `skills_long`: exploded long table with `url`, `source`, `title`, `company`, and `skill_clean`.

Initial normalization examples:

- Case/spacing normalization: trim, collapse spaces, standardize common casing.
- Synonyms only when safe: `Javascript`/`JavaScript`, `Typescript`/`TypeScript`, `Restful Api`/`REST API`, `Go (golang)`/`Go`, `Postgresql`/`PostgreSQL`.
- Keep raw skill values in an audit table before applying mappings.

Pandas methods to teach:

- `Series.apply()` for list parsing.
- `DataFrame.explode()`.
- `Series.map()` for synonym dictionaries.
- `DataFrame.merge()` for optional mapping tables.
- `DataFrame.value_counts()`.
- `DataFrame.groupby().size()`.

Validation checks:

- `skills_long["skill_clean"]` has no blank strings.
- Per-job skill duplicates are removed after normalization.
- Show top raw skill variants that still need a mapping.

### 8. Normalize Location And Work Mode For Analysis

Use the existing `location` and `location_cities` fields to create analysis-friendly location views.

Recommended columns:

- `city_list`: parsed list from `location_cities` or inferred from `location` where safe.
- `primary_city`: first city when available.
- `is_remote_location`: true when location/work mode indicates remote.
- `work_mode_clean`: normalized work mode category.

Rules:

- Do not over-infer exact districts or addresses.
- Keep remote as work mode/location signal, not a city.
- Preserve multi-city records by using an exploded `locations_long` view if needed.

Pandas methods to teach:

- `Series.str.contains()`.
- `Series.str.extract()`.
- `DataFrame.explode()`.
- `pd.crosstab()`.
- `GroupBy.nunique()`.

Validation checks:

- Location fill remains high by source.
- Remote jobs can be counted separately from city-based jobs.
- Multi-city records do not disappear from demand analysis.

### 9. Clean Experience And Seniority Fields

Create a section that validates existing parser outputs and builds learning-friendly bands.

Recommended columns:

- `_flag_experience_min_gt_max`.
- `_flag_experience_outlier` for values above a high threshold such as 15 years, for audit only.
- `experience_band` using `pd.cut()`.
- `seniority_clean` that keeps parser seniority but displays missing/unknown clearly.

Rules:

- Do not infer seniority from arbitrary body text in the notebook.
- Use `experience_raw`, `experience_min`, `experience_max`, and title-level parser output for audit.
- Keep `Khong yeu cau`/no-experience cases as valid zero experience when already parsed as 0.

Pandas methods to teach:

- `pd.cut()`.
- `Series.fillna()`.
- `DataFrame.groupby().agg()`.
- `pd.crosstab()`.
- `DataFrame.sort_values()`.

Validation checks:

- No valid clean experience row has `experience_min > experience_max`.
- Zero-experience rows are reviewed separately instead of treated as missing.

### 10. Validate Dates And Build Time Features

Add a date-cleaning section for analysis freshness and weekly grouping.

Recommended columns:

- `posted_date`.
- `scraped_date`.
- `valid_through_date`.
- `analysis_week_start` from `posted_at_parsed`, falling back to `scraped_at_parsed`.
- `_flag_valid_before_posted`.
- `_flag_future_posted_at` if relevant.

Pandas methods to teach:

- `Series.dt.date`.
- `Series.dt.to_period()` or weekly grouping with `pd.Grouper()`.
- `Series.combine_first()`.
- `DataFrame.resample()` only if a datetime index is useful.

Validation checks:

- Weekly groups match the conceptual logic in `parsers.trend_reports.week_start()`.
- Rows without posted date still have a fallback analysis week from scraped date when possible.

### 11. Add Description/Text Quality Features

Use text quality metrics for audit, not for broad parser inference.

Recommended columns:

- `description_length`.
- `description_word_count`.
- `_flag_short_description`.
- `_description_preview` for display.

Pandas methods to teach:

- `Series.str.len()`.
- `Series.str.count()`.
- `Series.str.slice()`.
- `DataFrame.nlargest()` and `DataFrame.nsmallest()`.

Validation checks:

- Very short descriptions are inspected by source.
- Description-based metrics do not alter core parser fields.

### 12. Build A Row-Level Issue Log

Create boolean issue columns first, then reshape them into `issues_long`.

Recommended issue columns:

- Missing title/company/location/description.
- Duplicate URL dropped from canonical view.
- Missing skills.
- Missing experience.
- Salary hidden/negotiable/missing/suspicious.
- Date parse missing or inconsistent.
- Experience inconsistent.

Pandas methods to teach:

- Boolean masks with `&`, `|`, and `~`.
- `DataFrame.filter(regex="^_flag_")`.
- `DataFrame.melt()`.
- `DataFrame.stack()`.
- `DataFrame.loc[]`.

Validation checks:

- `issues_long` only contains rows where the issue flag is true.
- Issue counts by source are reproducible from boolean columns.
- `quality_by_source` is generated from `jobs_clean`, not all duplicate rows.

### 13. Build Final Analysis Tables In Memory

At the end of the notebook, display final tables and explain what each is for.

Required tables:

- `jobs_clean`: canonical job-level table.
- `salary_for_analysis`: numeric salary rows safe for salary summaries.
- `skills_long`: skill demand table.
- `quality_by_source`: source-level quality and coverage.
- `issues_long`: audit/debug table.

Pandas methods to teach:

- `DataFrame.sample()`.
- `DataFrame.head()`.
- `DataFrame.describe(include="all")`.
- `DataFrame.groupby().agg()`.
- `DataFrame.pivot_table()`.
- `DataFrame.style` optionally for notebook display only.

Validation checks:

- `jobs_clean` has unique URLs.
- `salary_for_analysis` does not include hidden/negotiable/missing salary states.
- `skills_long` joins back to `jobs_clean` by URL.
- The final quality summary can explain why TopDev salary numeric coverage is 0 without treating it as a failed parse.

### 14. Add A Pandas Method Index For Learning

Add a final markdown table that maps common data-cleaning tasks to methods used in the notebook.

Include these task-to-method mappings:

- Select columns/rows: `[]`, `.loc[]`, `.filter()`.
- Inspect data: `.info()`, `.describe()`, `.value_counts()`, `.sample()`.
- Missing values: `.isna()`, `.notna()`, `.fillna()`, `.where()`, `.mask()`.
- Text cleaning: `.str.strip()`, `.str.contains()`, `.str.extract()`, `.str.replace()`.
- Types: `pd.to_numeric()`, `pd.to_datetime()`, `.astype()`, `.convert_dtypes()`.
- Duplicates: `.duplicated()`, `.drop_duplicates()`.
- Aggregation: `.groupby()`, `.agg()`, `.transform()`, `.value_counts()`.
- Reshaping: `.explode()`, `.melt()`, `.pivot_table()`, `.stack()`.
- Time: `.dt`, `pd.Grouper()`, `.resample()`.
- Chaining: `.assign()`, `.pipe()`, `.query()`.

For each method group, include one small example using this job dataset.

## Validation Plan

Run the notebook cells after implementation and verify:

- The original load still reports all current processed files and row counts.
- `jobs_all` row count equals the loaded `jobs` row count.
- `jobs_clean` has one row per URL.
- All required clean fields from the parser schema are still present.
- All derived date columns parse without unexpected dtype regressions.
- `salary_visibility` covers every row in `jobs_clean`.
- `salary_for_analysis` excludes hidden, negotiable, missing, and suspicious salary rows.
- `skills_long` has no empty `skill_clean` values.
- `quality_by_source` is explainable and does not treat TopDev hidden salary as a parser failure.
- No files in `data/raw`, `data/processed`, `data/reports`, `parsers`, `scrapers`, or `tests` are modified.

No unit tests are required for notebook-only changes. If implementation later changes parser or report code, run the focused parser/report tests documented in `AGENTS.md`.

## Risks And Guardrails

- Notebook cleaning can drift from production parser behavior. Keep derived notebook columns separate and document parser-improvement candidates instead of silently changing source code.
- Skill synonym mapping can over-merge distinct technologies. Keep raw skill values and show an unmapped-variant audit table.
- Salary labels differ by source and language. Classify hidden/negotiable labels before applying numeric checks.
- Multiple processed runs include overlapping URLs from sample/test/full/salary files. Make dedupe ranking visible so the selected canonical row is auditable.
- Date availability may vary by source. Use scraped date fallback for analysis week, matching the report code's fallback intent.

## Open Questions

- None for the notebook-only implementation.
