# ITviec Scrapling Crawl Plan

## Objective

Crawl a first sample of 30-50 ITviec job descriptions and save full raw HTML in JSONL so the parser can be improved without re-crawling the website.

Primary output:

```text
data/raw/itviec_sample_50.jsonl
```

Secondary outputs:

```text
data/processed/itviec_sample_50_clean.jsonl
data/processed/itviec_sample_50_clean.csv
```

## Scope

Source:

```text
ITviec
```

Sample size:

```text
30-50 job detail pages
```

This crawler must not:

```text
- bypass captcha, Cloudflare, or anti-bot systems
- log in or use a personal account
- crawl LinkedIn or Google Jobs directly
- crawl too fast
- scrape personal recruiter/contact information
```

## Architecture

Use two separate layers.

### Crawler Layer

Responsibilities:

```text
- discover job detail URLs from ITviec search pages
- crawl job detail pages
- save full raw HTML
- extract JSON-LD blocks when present
- save visible text when available
- append one raw record per line to JSONL
```

The crawler should not normalize salary, skills, title, company, or years of experience.

### Parser Layer

Responsibilities:

```text
- read raw JSONL records
- parse title, company, location, salary, description
- extract skills using a simple skill dictionary
- extract years of experience using regex
- export clean JSONL and CSV
```

## Raw JSONL Schema

Each line in `data/raw/itviec_sample_50.jsonl` should follow this shape:

```json
{
  "source": "itviec",
  "url": "https://itviec.com/it-jobs/...",
  "job_id": "itviec_...",
  "html": "<html>...</html>",
  "json_ld": [],
  "visible_text": "...",
  "http_status": 200,
  "scraped_at": "2026-06-30T10:00:00Z"
}
```

Full HTML is intentionally stored even though the JSONL file is larger. This makes parser iteration safer and avoids re-crawling after selector changes.

## Clean JSONL Schema

Each line in `data/processed/itviec_sample_50_clean.jsonl` should follow this shape:

```json
{
  "source": "itviec",
  "url": "https://itviec.com/it-jobs/...",
  "job_id": "itviec_...",
  "title": "Senior Backend Engineer",
  "company": "ABC Tech",
  "location": "Ho Chi Minh",
  "salary_raw": "$2000 - $3500",
  "salary_min": 2000,
  "salary_max": 3500,
  "salary_currency": "USD",
  "skills": ["Python", "Django", "AWS"],
  "experience_raw": "3+ years",
  "experience_min": 3,
  "experience_max": null,
  "description": "...",
  "scraped_at": "2026-06-30T10:00:00Z"
}
```

## Crawl Flow

### 1. Discover Job URLs

Use keyword search pages to collect job detail URLs.

Initial keyword seeds:

```text
python
java
frontend
backend
react
nodejs
devops
data
tester
```

For each keyword:

```text
- crawl the first few result pages
- extract links that look like ITviec job detail URLs
- normalize to absolute URLs
- deduplicate URLs
- stop after reaching the target limit
```

### 2. Crawl Job Details

For each discovered URL:

```text
- request the job detail page
- stop if captcha/block content is detected
- save full HTML
- extract JSON-LD script blocks
- extract visible text
- append the raw record immediately to JSONL
```

### 3. Rate Limit And Retry

Default safe settings:

```text
delay: 2-4 seconds between detail requests
concurrency: 1
retry: maximum 2 retries for transient network errors
timeout: 30 seconds
```

## Validation Checklist

After crawling 30-50 records, manually inspect at least 10 records.

Checklist:

```text
- URL points to a job detail page
- title can be parsed
- company can be parsed
- location can be parsed when displayed
- salary_raw matches website text when displayed
- description is not empty
- raw HTML is present
- duplicate count is low
- JSONL is readable by Python/pandas
```

## Success Criteria

The first sample is successful if:

```text
- at least 30 valid JD records are crawled
- at least 90% of records have title
- at least 90% of records have company
- at least 80% of records have location
- no captcha or block page is bypassed
- raw JSONL and clean JSONL/CSV are generated
```

## Scaling Plan

### 30-50 JD

Use JSONL only:

```text
data/raw/itviec_sample_50.jsonl
data/processed/itviec_sample_50_clean.jsonl
```

### 500-1000 JD

Add SQLite:

```text
data/raw/*.jsonl
data/processed/*.jsonl
data/jobs.sqlite
```

Add these fields:

```text
dedupe_key
content_hash
crawl_run_id
parse_status
```

### 5000+ JD

Use PostgreSQL plus raw JSONL backup:

```text
jobs
companies
job_skills
crawl_runs
raw_pages
```

Use incremental crawling, content hashing, and source-specific freshness checks.
