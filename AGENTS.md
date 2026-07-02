# Agent Notes

## Project Shape
- Python prototype for public Vietnam IT job collection; run commands from the repo root so `scrapers.*` and `parsers.*` imports resolve.
- Current executable scope is ITviec, TopDev, TopCV, and trend reports; `opencode.md` is historical ITviec-era context, so trust current modules, tests, and `README.md` when they conflict.
- Pipeline: crawlers append raw JSONL, parsers convert raw records to shared clean JSONL/CSV, and `parsers.trend_reports` aggregates clean outputs.
- No root app `pyproject.toml`, task runner, lockfile, CI workflow, pre-commit config, formatter/linter/type config, or repo-local `kilo.json` is present; `requirements.txt` is the app dependency source. `.kilo/package*.json` is Kilo plugin metadata, not the app toolchain.
- `scrapers.fetching` tries Scrapling first and falls back to `urllib`; do not assume a Playwright browser install step exists just because Playwright is in `requirements.txt`.

## Commands
- Install dependencies: `pip install -r requirements.txt`; prefer a virtual environment because a previous global install produced an `lxml` conflict warning with `docling`.
- Compile check: `python -m compileall scrapers parsers`.
- Full tests: `python -m unittest discover tests`.
- Focused parser/crawler/report tests: `python -m unittest tests.test_itviec_parser tests.test_topdev_parser tests.test_topcv_parser tests.test_topcv_crawler tests.test_trend_reports`.
- ITviec crawl: `python -m scrapers.itviec_crawler --limit 50 --output data/raw/itviec_run.jsonl --pages-per-keyword 3 --delay-min 2 --delay-max 4 --timeout 30 --retries 1`.
- TopDev crawl: `python -m scrapers.topdev_crawler --limit 50 --output data/raw/topdev_run.jsonl --pages-per-keyword 3 --delay-min 2 --delay-max 4 --timeout 30 --retries 1`.
- TopCV crawl: `python -m scrapers.topcv_crawler --limit 50 --output data/raw/topcv_run.jsonl --pages-per-keyword 3 --delay-min 2 --delay-max 4 --timeout 30 --retries 1`.
- ITviec parse: `python -m parsers.itviec_parser --input data/raw/itviec_run.jsonl --jsonl-output data/processed/itviec_run_clean.jsonl --csv-output data/processed/itviec_run_clean.csv`.
- TopDev parse: `python -m parsers.topdev_parser --input data/raw/topdev_run.jsonl --jsonl-output data/processed/topdev_run_clean.jsonl --csv-output data/processed/topdev_run_clean.csv`.
- TopCV parse: `python -m parsers.topcv_parser --input data/raw/topcv_run.jsonl --jsonl-output data/processed/topcv_run_clean.jsonl --csv-output data/processed/topcv_run_clean.csv`.
- Reports: `python -m parsers.trend_reports`; defaults to `data/processed/*_clean.jsonl` and writes `data/reports/*.csv`. Override with `--inputs ... --output-dir data/reports`.

## Quality Crawl Workflow
- Preserve verified raw data by default; for a fresh run, use new paths such as `data/raw/<source>_<run_name>.jsonl` and matching `data/processed/<source>_<run_name>_clean.*` outputs.
- `--limit` means desired unique URLs for that output file; crawlers append immediately and dedupe by existing `url`.
- TopDev and TopCV exit early when existing output already satisfies `--limit`; ITviec still discovers search pages before saving nothing, so avoid rerunning ITviec against already-satisfied outputs.
- After crawling, parse and inspect at least 10 clean records for detail-page URLs, non-empty title/company/description, displayed location/salary_raw accuracy, duplicate URLs, and `parse_status`.

## Crawl Constraints
- Keep crawler and parser responsibilities separate: crawlers store raw HTML, JSON-LD, visible text, HTTP status, fetcher, and timestamps; parsers own all normalization/extraction.
- Do not add captcha/Cloudflare bypasses, login flows, fast concurrency, LinkedIn/Google Jobs direct crawling, or recruiter/contact scraping.
- Crawlers respect `robots.txt`, run sequentially, use low delays, and stop or skip on obvious block/challenge pages.
- ITviec detail URLs must be on `itviec.com` and look like `/it-jobs/...-1234`.
- TopDev detail URLs must look like `/detail-jobs/...-12345` and normalize to host `topdev.vn`.
- TopCV detail URLs must look like `/viec-lam/.../123.html` and normalize to host `www.topcv.vn`.
- Full raw HTML in `data/raw/*.jsonl` is intentional so parser changes can be tested by regenerating processed outputs without re-crawling.

## Parser/Data Quality Notes
- Parsers emit `parsers.common.CLEAN_FIELDNAMES`: `source`, `url`, `job_id`, `title`, `company`, `location`, `salary_raw`, `salary_min`, `salary_max`, `salary_currency`, `skills`, `experience_raw`, `experience_min`, `experience_max`, `description`, `scraped_at`, `parse_status`, `posted_raw`, `posted_at`, `valid_through`, `location_cities`, `seniority`, `work_mode`, `employment_type`, `salary_period`.
- For parser changes, prefer JSON-LD `JobPosting` fields when exposed: `baseSalary`, `skills`, `hiringOrganization`, `jobLocation`, posting dates, validity dates, and employment type.
- Preserve hidden/ambiguous salary labels without numeric salary fields: ITviec `You'll love it`/`Thỏa thuận`, TopDev `Login to view salary`, and TopCV `Thoa thuan`/`Negotiable`.
- Skills come from structured tags plus title/requirements/description, not whole-page text, to avoid footer, blog, company-card, and `More jobs` noise.
- Experience should come from explicit experience/requirements text first, then title-level fallback; do not infer level words from arbitrary body text.
- Parsers delete/recreate only the clean JSONL output and overwrite CSV with UTF-8 BOM; raw input is read-only.
- When parser logic changes, regenerate affected processed outputs from existing raw JSONL and run the focused test command above; rerun reports if trend fields changed.
