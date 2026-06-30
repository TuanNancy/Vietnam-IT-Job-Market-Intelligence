# OpenCode Handoff

## Project

Vietnam IT Job Market Intelligence

Workspace root:

```text
G:\project\Vietnam IT Job Market Intelligence
```

## Goal

Build a Python prototype to collect and parse Vietnam IT job postings, starting with ITviec.

The project is intentionally split into two layers:

- Crawler layer: fetch raw pages and store full raw HTML, JSON-LD, visible text, status, and fetch metadata.
- Parser layer: normalize raw records into clean JSONL/CSV with title, company, location, salary, skills, and experience fields.

## Current Status

Implemented and verified a working ITviec pipeline.

Created files:

- `docs/itviec_scrapling_crawl_plan.md`
- `README.md`
- `requirements.txt`
- `scrapers/__init__.py`
- `scrapers/storage.py`
- `scrapers/itviec_crawler.py`
- `parsers/__init__.py`
- `parsers/itviec_parser.py`

Generated data:

- `data/raw/itviec_test_2.jsonl`
- `data/processed/itviec_test_2_clean.jsonl`
- `data/processed/itviec_test_2_clean.csv`
- `data/raw/itviec_sample_50.jsonl`
- `data/processed/itviec_sample_50_clean.jsonl`
- `data/processed/itviec_sample_50_clean.csv`

Latest successful sample:

```text
records: 30
unique_urls: 30
company: 30/30
location: 30/30
salary_raw: 30/30
parse_ok: 30/30
```

## Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Compile check:

```bash
python -m compileall scrapers parsers
```

Crawl ITviec sample:

```bash
python -m scrapers.itviec_crawler --limit 50 --output data/raw/itviec_sample_50.jsonl
```

Parse ITviec sample:

```bash
python -m parsers.itviec_parser --input data/raw/itviec_sample_50.jsonl --jsonl-output data/processed/itviec_sample_50_clean.jsonl --csv-output data/processed/itviec_sample_50_clean.csv
```

Safer crawl command used for the verified 30-record run:

```bash
python -m scrapers.itviec_crawler --limit 30 --output data/raw/itviec_sample_50.jsonl --pages-per-keyword 3 --delay-min 2 --delay-max 4 --timeout 30 --retries 1
```

## Important Implementation Notes

The crawler now discovers ITviec job detail URLs from search-page JSON-LD `ItemList` data first, then falls back to anchor links.

Valid ITviec detail URLs are filtered with a slug pattern ending in a four-digit job ID, such as:

```text
https://itviec.com/it-jobs/software-engineer-python-typescript-skylab-1113
```

Crawler behavior:

- Respects `robots.txt`.
- Uses low request rate by default.
- Appends JSONL records immediately.
- Deduplicates by existing `url` in the output file.
- Stores full raw HTML intentionally.
- Does not bypass captcha, Cloudflare, login, or anti-bot systems.

Parser behavior:

- Prefers JSON-LD fields where useful.
- Uses `h1` for title when available.
- Extracts skills from title and description, not the entire visible page, to avoid footer and `More jobs` noise.
- Leaves numeric salary fields null when salary is ambiguous, negotiable, or represented as `You'll love it`.

## Dependencies

`requirements.txt` currently includes:

- `scrapling>=0.2.99`
- `curl_cffi>=0.15.0`
- `playwright>=1.61.0`
- `browserforge>=1.2.4`
- `beautifulsoup4>=4.12.3`
- `pandas>=2.2.0`

Note: installing Scrapling in the global Python environment produced an `lxml` conflict warning with `docling`. The current project runs, but use a virtual environment before scaling.

## Known Constraints

- Do not crawl LinkedIn with a personal account.
- Do not add captcha or Cloudflare bypass logic.
- Do not scrape recruiter personal contact details.
- Keep concurrency low; current design is sequential.
- Keep crawler and parser responsibilities separate.

## Next Steps

1. Add parser unit tests for representative ITviec raw records.
2. Validate 10-20 clean records manually for title, company, skills, salary, and experience accuracy.
3. Improve experience extraction from requirements sections.
4. Crawl 50 records after validation.
5. Add SQLite when moving to 500-1000 records.
6. Add TopDev as the next source after ITviec is stable.
