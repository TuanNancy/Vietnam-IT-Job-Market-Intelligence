# Agent Notes

## Project Shape
- Python prototype for Vietnam IT job data collection; run commands from the repo root so `scrapers.*` and `parsers.*` imports resolve.
- Current code supports ITviec and TopDev. `README.md` and `opencode.md` are ITviec-era and miss TopDev; trust `scrapers/*_crawler.py`, `parsers/*_parser.py`, and tests for current scope.
- No `pyproject.toml`, task runner, lockfile, CI config, formatter config, or repo-local `kilo.json` is present; `requirements.txt` is the dependency source.
- The pipeline is intentionally two-layer per source: crawlers write raw JSONL, then parsers convert raw records to the shared clean JSONL/CSV schema.

## Commands
- Install dependencies: `pip install -r requirements.txt`; prefer a virtual environment because a previous global install produced an `lxml` conflict warning with `docling`.
- Compile check: `python -m compileall scrapers parsers`.
- Parser tests: `python -m unittest tests.test_itviec_parser tests.test_topdev_parser`.
- ITviec crawl: `python -m scrapers.itviec_crawler --limit 50 --output data/raw/itviec_sample_50.jsonl`.
- ITviec parse: `python -m parsers.itviec_parser --input data/raw/itviec_sample_50.jsonl --jsonl-output data/processed/itviec_sample_50_clean.jsonl --csv-output data/processed/itviec_sample_50_clean.csv`.
- TopDev crawl: `python -m scrapers.topdev_crawler --limit 50 --output data/raw/topdev_sample_50.jsonl`.
- TopDev parse: `python -m parsers.topdev_parser --input data/raw/topdev_sample_50.jsonl --jsonl-output data/processed/topdev_sample_50_clean.jsonl --csv-output data/processed/topdev_sample_50_clean.csv`.

## Quality Crawl Workflow
- Preserve verified raw data by default; for a fresh run, use new paths such as `data/raw/<source>_<run_name>.jsonl` and matching `data/processed/<source>_<run_name>_clean.*` outputs.
- Safer verified crawl shape: `python -m scrapers.<source>_crawler --limit 30 --output data/raw/<source>_<run_name>.jsonl --pages-per-keyword 3 --delay-min 2 --delay-max 4 --timeout 30 --retries 1`.
- `--limit` means desired unique URLs for that output file; crawlers append immediately and dedupe by existing `url`.
- TopDev exits early when existing output already satisfies `--limit`; ITviec still discovers search pages before saving nothing, so avoid rerunning ITviec against already-satisfied outputs.
- After crawling, parse and inspect at least 10 clean records for detail-page URLs, non-empty title/company/description, displayed location/salary_raw accuracy, duplicate URLs, and `parse_status`.

## Crawl Constraints
- Keep crawler and parser responsibilities separate: crawlers store raw HTML, JSON-LD, visible text, HTTP status, fetcher, and timestamps; parsers own all normalization/extraction.
- Do not add captcha/Cloudflare bypasses, login flows, fast concurrency, LinkedIn/Google Jobs direct crawling, or recruiter/contact scraping.
- Both crawlers respect `robots.txt`, run sequentially, use low delays, and stop or skip on obvious block/challenge pages.
- ITviec detail URLs must look like `/it-jobs/...-1234`; TopDev detail URLs must look like `/detail-jobs/...-12345` and normalize to host `topdev.vn`.
- Full raw HTML in `data/raw/*.jsonl` is intentional so parser changes can be tested by regenerating processed outputs without re-crawling.

## Parser/Data Quality Notes
- Both parsers emit this clean schema: `source`, `url`, `job_id`, `title`, `company`, `location`, `salary_raw`, `salary_min`, `salary_max`, `salary_currency`, `skills`, `experience_raw`, `experience_min`, `experience_max`, `description`, `scraped_at`, `parse_status`.
- Prefer JSON-LD fields when available, especially `JobPosting`, `baseSalary`, `skills`, `hiringOrganization`, and `jobLocation`.
- Preserve hidden/ambiguous salary labels: ITviec `You'll love it`/`Thỏa thuận` and TopDev `Login to view salary` should leave numeric salary fields null.
- Skills come from structured tags plus title/requirements/description, not whole-page text, to avoid footer, blog, company-card, and `More jobs` noise.
- Experience should come from explicit experience/requirements text first, then title-level fallback; do not infer level words from arbitrary body text.
- Parsers delete/recreate only the clean JSONL output and overwrite CSV with UTF-8 BOM; raw input is read-only.
- When parser logic changes, regenerate processed outputs from existing raw JSONL and run `python -m unittest tests.test_itviec_parser tests.test_topdev_parser`.
