# Vietnam IT Job Market Intelligence

Prototype crawler for collecting IT job descriptions from Vietnam job boards.

Current scope:

```text
- Crawl 30-50 ITviec job descriptions with Scrapling
- Store full raw HTML in JSONL
- Parse a clean JSONL/CSV dataset for analysis
```

See the detailed plan:

```text
docs/itviec_scrapling_crawl_plan.md
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Crawl a small sample:

```bash
python -m scrapers.itviec_crawler --limit 50 --output data/raw/itviec_sample_50.jsonl
```

Parse raw records:

```bash
python -m parsers.itviec_parser --input data/raw/itviec_sample_50.jsonl --jsonl-output data/processed/itviec_sample_50_clean.jsonl --csv-output data/processed/itviec_sample_50_clean.csv
```
