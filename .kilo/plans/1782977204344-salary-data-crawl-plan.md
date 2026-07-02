# Salary-Focused Data Crawl Plan

Status: finalized for implementation on 2026-07-02.

## Goal
- Increase the usable salary-regression dataset to at least 500 clean unique records with numeric salary fields (`salary_min` or `salary_max`).
- Keep raw crawl data reproducible and preserve existing verified outputs; do not overwrite existing raw/processed files unless explicitly creating a new derived dataset.
- Improve data quality before modeling; more rows alone does not prevent Linear Regression overfitting.

## Current Verified Baseline
- Existing clean data: `itviec_20260701_100_clean.jsonl`, `topcv_20260702_100_clean.jsonl`, `topdev_20260701_100_clean.jsonl` each have 100 records.
- Existing source quality report shows salary numeric rows approximately: ITviec 27, TopCV 55, TopDev 0.
- Current salary-regression usable baseline is about 82 rows, not 300, because hidden/negotiable salaries do not provide labels.
- `data/raw/topcv_20260702_100.jsonl` is absent even though `data/processed/topcv_20260702_100_clean.*` exists; do not delete or assume this TopCV clean file can be regenerated.
- TopDev should be excluded from the 500 salary-row target because current salary is hidden as `Login to view salary` and login/bypass is out of scope.

## Decisions
- Optimize for salary-labeled records, not total job count.
- Target: at least 500 unique clean records with numeric salary from TopCV and ITviec combined.
- TopDev can remain useful for demand/skills trend reports, but not for salary regression until salary extraction changes without login/bypass.
- Use low-delay sequential crawls only; respect robots.txt and stop on block/captcha pages.
- Use iterative batches: crawl, parse, audit, then decide whether to raise `--limit` and continue.

## Crawl Strategy
1. Start with TopCV because current `salary_numeric_fill_rate` is highest.
2. Use a new raw output, for example `data/raw/topcv_salary_20260702.jsonl`; the existing TopCV raw 100 is missing, so dedupe against existing TopCV clean data during the final merge/audit.
3. Run TopCV in batches by increasing `--limit` on the same output file, for example 500, then 800, then 1000 if needed. TopCV dedupes by URL inside the chosen output file and exits early when already satisfied.
4. Use broader IT-related keywords for TopCV while keeping them job-market relevant: `it cong-nghe-thong-tin python java frontend backend react nodejs devops data tester qa mobile android ios ai`.
5. Parse after every TopCV batch and count unique salary numeric rows across existing and new clean outputs.
6. Use ITviec as the second source if TopCV alone does not reach 500 salary rows or if the dataset needs source diversity.
7. For ITviec, prefer seeding a new run file from existing raw `data/raw/itviec_20260701_100.jsonl` before crawling more, rather than appending to the old file or starting from an empty file that likely recrawls duplicates. If seeding is not done, final merge must dedupe by URL.
8. Do not crawl TopDev for the salary target unless the user separately asks for trend/demand expansion.

## Suggested Commands
- TopCV batch 1:
  `python -m scrapers.topcv_crawler --limit 500 --output data/raw/topcv_salary_20260702.jsonl --keywords it cong-nghe-thong-tin python java frontend backend react nodejs devops data tester qa mobile android ios ai --pages-per-keyword 20 --delay-min 2 --delay-max 4 --timeout 30 --retries 1`
- Parse TopCV batch:
  `python -m parsers.topcv_parser --input data/raw/topcv_salary_20260702.jsonl --jsonl-output data/processed/topcv_salary_20260702_clean.jsonl --csv-output data/processed/topcv_salary_20260702_clean.csv`
- If salary rows remain below target, rerun the same TopCV command with `--limit 800`, then `--limit 1000`.
- ITviec supplemental crawl if needed:
  `python -m scrapers.itviec_crawler --limit 500 --output data/raw/itviec_salary_20260702.jsonl --keywords python java frontend backend react nodejs devops data tester qa mobile android ios ai --pages-per-keyword 20 --delay-min 2 --delay-max 4 --timeout 30 --retries 1`
- Parse ITviec supplemental crawl:
  `python -m parsers.itviec_parser --input data/raw/itviec_salary_20260702.jsonl --jsonl-output data/processed/itviec_salary_20260702_clean.jsonl --csv-output data/processed/itviec_salary_20260702_clean.csv`
- Build reports into a run-specific directory to avoid overwriting current reports:
  `python -m parsers.trend_reports --inputs data/processed/itviec_20260701_100_clean.jsonl data/processed/topcv_20260702_100_clean.jsonl data/processed/topcv_salary_20260702_clean.jsonl data/processed/itviec_salary_20260702_clean.jsonl --output-dir data/reports/salary_20260702`

## Quality Gate
- Aggregate selected clean JSONL files and dedupe by `url` before counting target rows.
- Required target: at least 500 deduped rows where `salary_min` or `salary_max` is numeric.
- Required sanity checks:
  - `parse_status == "ok"` for nearly all rows; investigate any non-ok rows.
  - `title`, `company`, `location`, and `description` fill rates stay high, ideally >= 0.95.
  - `skills` fill rate should be tracked separately; do not use low-quality whole-page text to inflate skills.
  - Salary rows must have positive values; if both min and max exist, `salary_min <= salary_max`.
  - Do not mix salary currencies in Linear Regression without normalization; for the first model, either filter to the dominant currency or explicitly convert before training.
  - Exclude hidden/ambiguous salaries such as `Thỏa thuận`, `Negotiable`, `You'll love it`, and `Login to view salary` from regression labels.
- Manually inspect at least 10-20 new salary-positive records per source for detail-page URL validity, displayed salary accuracy, title/company/location correctness, and duplicate leakage.

## Modeling Guidance
- Plain `LinearRegression` on the current ~82 salary rows is high-risk if features include many sparse skills, title tokens, companies, or locations.
- Even with 500 salary rows, overfitting is still possible; validate with train/test split or k-fold cross-validation and compare against a simple baseline such as median salary by source/location/seniority.
- Prefer a regularized baseline (`Ridge`, `Lasso`, or `ElasticNet`) over unregularized Linear Regression for sparse one-hot/text features.
- Model target should be a normalized salary midpoint, for example midpoint of `salary_min`/`salary_max`, with clear currency and period handling.
- Keep TopDev out of the salary model until numeric salary labels are available without login/bypass.

## Failure Modes
- TopCV/ITviec may produce fewer new unique URLs than requested because keywords overlap; raise `--pages-per-keyword` or add relevant keywords only after auditing duplicates.
- Crawl may hit block/captcha pages; stop or skip according to existing crawler behavior and do not add bypasses.
- Existing clean TopCV 100 cannot be regenerated from raw unless raw is recovered or recrawled.
- Large total job count can still be weak for salary modeling if salary numeric fill rate drops.

## Validation Checklist
1. Parse every new raw crawl output into new clean JSONL/CSV files.
2. Build run-specific trend/source-quality reports.
3. Produce an aggregate audit of deduped clean rows by source: total rows, salary numeric rows, duplicate URLs, fill rates, salary currency counts, and suspicious salary ranges.
4. Confirm the 500 salary-row target before training any regression model.
5. If parser code changes are made during implementation, run `python -m unittest tests.test_itviec_parser tests.test_topcv_parser tests.test_trend_reports` and regenerate affected processed outputs from raw.
6. If no code changes are made, crawler/parser execution plus audit reports are the primary validation.

## Execution Handover - 2026-07-02 15:49 +07
- User requested to stop execution before parsing completed.
- Dependencies were installed with `pip install -r requirements.txt` after the first crawler attempt failed on missing `bs4`.
- TopCV salary crawl batch completed successfully into new raw output: `data/raw/topcv_salary_20260702.jsonl`.
- Confirmed raw record count: 500 JSONL rows.
- Parse command was started but aborted by the user before completion:
  `python -m parsers.topcv_parser --input data/raw/topcv_salary_20260702.jsonl --jsonl-output data/processed/topcv_salary_20260702_clean.jsonl --csv-output data/processed/topcv_salary_20260702_clean.csv`
- No `data/processed/topcv_salary_20260702_clean.*` files were present immediately after the abort.
- Next safe resume step is to run the parse command above, then audit deduped numeric salary rows across:
  `data/processed/itviec_20260701_100_clean.jsonl`, `data/processed/topcv_20260702_100_clean.jsonl`, and `data/processed/topcv_salary_20260702_clean.jsonl`.
- Do not rerun the TopCV crawl at `--limit 500` unless the raw file is intentionally discarded or the crawler's existing-output early exit behavior is desired.

## Implementation Results - 2026-07-02 20:40 +07
- Parsed TopCV salary raw output into:
  `data/processed/topcv_salary_20260702_clean.jsonl` and `data/processed/topcv_salary_20260702_clean.csv`.
- TopCV was extended from `--limit 500` to `--limit 800`; many detail fetches returned HTTP 429, so TopCV crawling was stopped and ITviec was used for the remaining target.
- Seeded `data/raw/itviec_salary_20260702.jsonl` from `data/raw/itviec_20260701_100.jsonl`, then crawled ITviec supplemental data to 750 raw records using the original and extra relevant keywords.
- Parsed ITviec salary output into:
  `data/processed/itviec_salary_20260702_clean.jsonl` and `data/processed/itviec_salary_20260702_clean.csv`.
- Generated run-specific reports and audit artifacts under `data/reports/salary_20260702/`.
- Final aggregate audit across ITviec baseline, TopCV baseline, TopCV salary batch, and ITviec salary batch:
  total rows before dedupe: 1525; unique URLs: 1333; duplicate records by URL: 192; unique numeric salary rows: 512; target met: yes.
- By source after dedupe: ITviec 750 unique rows with 207 numeric salary rows; TopCV 583 unique rows with 305 numeric salary rows.
- Currency counts among numeric salary rows: USD 185, VND 323, unknown 4.
- Suspicious salary audit flagged 4 rows; excluding all flagged rows still leaves 508 salary-positive rows, above the 500 target.
- Validation passed:
  `python -m unittest tests.test_itviec_parser tests.test_topcv_parser tests.test_trend_reports`
  and `python -m compileall scrapers parsers`.
