# Vietnam IT Job Market Intelligence

Python prototype for collecting public Vietnam IT job postings and preparing trend-ready datasets.

Current scope:

```text
- Crawl ITviec, TopDev, and TopCV public job pages
- Store full raw HTML, JSON-LD, visible text, status, fetcher, and timestamps in JSONL
- Parse clean JSONL/CSV with salary, skills, experience, and trend fields
- Build weekly demand, salary, experience, and source-quality CSV reports
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run checks:

```bash
python -m compileall scrapers parsers
python -m unittest discover tests
```

Safer crawl shape:

```bash
python -m scrapers.itviec_crawler --limit 50 --output data/raw/itviec_run.jsonl --pages-per-keyword 3 --delay-min 2 --delay-max 4 --timeout 30 --retries 1
python -m scrapers.topdev_crawler --limit 50 --output data/raw/topdev_run.jsonl --pages-per-keyword 3 --delay-min 2 --delay-max 4 --timeout 30 --retries 1
python -m scrapers.topcv_crawler --limit 50 --output data/raw/topcv_run.jsonl --pages-per-keyword 3 --delay-min 2 --delay-max 4 --timeout 30 --retries 1
```

Parse raw records:

```bash
python -m parsers.itviec_parser --input data/raw/itviec_run.jsonl --jsonl-output data/processed/itviec_run_clean.jsonl --csv-output data/processed/itviec_run_clean.csv
python -m parsers.topdev_parser --input data/raw/topdev_run.jsonl --jsonl-output data/processed/topdev_run_clean.jsonl --csv-output data/processed/topdev_run_clean.csv
python -m parsers.topcv_parser --input data/raw/topcv_run.jsonl --jsonl-output data/processed/topcv_run_clean.jsonl --csv-output data/processed/topcv_run_clean.csv
```

Build reports:

```bash
python -m parsers.trend_reports
```

Crawler constraints:

```text
- Respect robots.txt
- Crawl sequentially with low delays
- Do not bypass captcha, Cloudflare, login, or anti-bot systems
- Do not crawl LinkedIn or Google Jobs directly
- Do not scrape recruiter personal contact details
```
