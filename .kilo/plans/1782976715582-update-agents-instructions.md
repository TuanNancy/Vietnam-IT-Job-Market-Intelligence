# Update AGENTS.md Plan

## Goal
- Update `AGENTS.md` in place with compact, high-signal repo guidance for future Kilo sessions.
- Preserve verified useful guidance, remove stale claims, and avoid generic advice.

## Verified Context
- This is a Python prototype run from the repo root so `scrapers.*` and `parsers.*` imports resolve.
- Current executable scope is ITviec, TopDev, TopCV, and trend report generation.
- `opencode.md` is historical and ITviec-era; trust current modules, tests, and `README.md` when they conflict.
- No `pyproject.toml`, task runner, lockfile, CI workflow, pre-commit config, formatter config, or repo-local `kilo.json` was found; `requirements.txt` is the dependency source.
- The pipeline is intentionally two-layer per source: crawlers write raw JSONL, parsers convert raw records to shared clean JSONL/CSV, then `parsers.trend_reports` builds reports.

## Implementation Steps
1. Edit only `AGENTS.md`.
2. Update `## Project Shape` to reflect ITviec, TopDev, TopCV, and trend reports; remove the stale claim that current code supports only ITviec and TopDev.
3. Keep the repo-root import warning and dependency source note.
4. Add or update exact commands:
   - `pip install -r requirements.txt`
   - `python -m compileall scrapers parsers`
   - `python -m unittest discover tests`
   - Focused parser/report tests: `python -m unittest tests.test_itviec_parser tests.test_topdev_parser tests.test_topcv_parser tests.test_topcv_crawler tests.test_trend_reports`
   - Crawl commands for `scrapers.itviec_crawler`, `scrapers.topdev_crawler`, and `scrapers.topcv_crawler` using `--limit`, `--output`, `--pages-per-keyword`, `--delay-min`, `--delay-max`, `--timeout`, and `--retries`.
   - Parse commands for `parsers.itviec_parser`, `parsers.topdev_parser`, and `parsers.topcv_parser`.
   - Report command: `python -m parsers.trend_reports`; mention it defaults to `data/processed/*_clean.jsonl` and writes `data/reports/*.csv`, with optional `--inputs` and `--output-dir`.
5. Update crawl workflow notes:
   - Preserve verified raw data; use new run-specific paths under `data/raw/` and matching `data/processed/` outputs.
   - `--limit` targets unique URLs for that output; crawlers append immediately and dedupe by existing `url`.
   - TopDev and TopCV exit early when existing output already satisfies `--limit`; ITviec still discovers before writing nothing.
   - Keep crawler/parser responsibilities separate: raw HTML, JSON-LD, visible text, HTTP status, fetcher, timestamps in crawlers; normalization/extraction in parsers.
   - Keep constraints against captcha/Cloudflare bypasses, login flows, fast concurrency, LinkedIn/Google Jobs direct crawling, and recruiter/contact scraping.
   - Keep robots/sequential/low-delay behavior.
6. Update URL rules:
   - ITviec detail URLs: `/it-jobs/...-1234` on `itviec.com`.
   - TopDev detail URLs: `/detail-jobs/...-12345`, normalized to host `topdev.vn`.
   - TopCV detail URLs: `/viec-lam/.../123.html`, normalized to host `www.topcv.vn`.
7. Update parser/data quality notes:
   - Shared clean schema is `parsers.common.CLEAN_FIELDNAMES`: base fields `source`, `url`, `job_id`, `title`, `company`, `location`, `salary_raw`, `salary_min`, `salary_max`, `salary_currency`, `skills`, `experience_raw`, `experience_min`, `experience_max`, `description`, `scraped_at`, `parse_status`, plus trend fields `posted_raw`, `posted_at`, `valid_through`, `location_cities`, `seniority`, `work_mode`, `employment_type`, `salary_period`.
   - Prefer JSON-LD `JobPosting`, `baseSalary`, `skills`, `hiringOrganization`, `jobLocation`, posting dates, validity dates, and employment type when available.
   - Preserve hidden/ambiguous salary labels without numeric salary fields: ITviec `You'll love it`/`Thỏa thuận`, TopDev `Login to view salary`, TopCV `Thoa thuan`/`Negotiable`.
   - Skills should come from structured tags plus scoped title/requirements/description, not whole-page/footer text.
   - Experience should come from explicit experience/requirements text first, then title fallback; do not infer level words from arbitrary page body text.
   - Parsers delete/recreate only clean JSONL output and overwrite CSV with UTF-8 BOM; raw input stays read-only.
8. Keep the file compact. Remove redundant tutorial prose, stale ITviec-only next steps, and claims not supported by current code/docs.

## Validation
- Because this is a documentation-only change, inspect `git diff -- AGENTS.md` for accuracy and compactness.
- Do not run crawlers as validation for this task.
- Python tests are not required unless implementation changes executable files by mistake.

## Caveats
- Do not edit `opencode.md`, raw data, processed data, or report outputs for this task.
- Keep any historical virtual-environment warning brief if preserved; it is useful existing guidance but not an executable config fact.
