# Blog.md Case Study Plan

## Goal

Create `blog.md` at the repo root as a Vietnamese technical case study for recruiters/interviewers. The blog should explain the current project story: crawling public Vietnam IT job postings, parsing them into clean datasets, and using pandas to explore data quality and early market signals. It should be written as a living article that can be updated after later cleaning/reporting steps.

## Decisions

- Target file: `blog.md` in the repo root.
- Language and tone: Vietnamese case study, portfolio-friendly, clear enough for recruiters, with technical keywords kept in English where natural.
- Project label: `data pipeline prototype`, not a full production system.
- Data sources to mention: `ITviec`, `TopDev`, `TopCV`.
- Do not mention `TopIT` as an implemented source; it is not present in the current repo.
- Include current EDA numbers as a dated/current snapshot, and say they will change as more crawling/cleaning is done.
- Include responsible crawling/ethics: robots.txt, sequential crawl, low delay, no captcha/login/anti-bot bypass, no personal recruiter/contact scraping.

## Repo Facts To Use

- README describes the pipeline as a Python prototype for public Vietnam IT job postings and trend-ready datasets.
- Crawler scope is ITviec, TopDev, and TopCV.
- `scrapers.fetching` tries Scrapling first via `scrapling.fetchers.Fetcher`, then falls back to `urllib`.
- Raw records are JSONL and include HTML, JSON-LD, visible text, HTTP status, fetcher, and timestamps.
- Parsers produce clean JSONL/CSV with salary, skills, experience, and trend fields.
- Trend reports can aggregate weekly demand, salary, experience, and source-quality CSVs.
- Existing notebook: `notebooks/01_data_inventory_eda.ipynb` loads all clean CSVs and explores schema, dtypes, missingness, duplicates, salary coverage, TopDev salary limitation, and skill demand.

## Current Snapshot To Include Carefully

Use wording like “ở snapshot hiện tại trong repo” rather than permanent claims.

- Clean CSV files loaded: 8.
- Rows loaded: 1,662.
- Unique URLs: 1,433.
- Duplicate URL rows: 421.
- Rows after URL dedupe: 1,433.
- All loaded rows currently have `parse_status == "ok"`.
- Deduped source coverage:
- ITviec: 750 rows, numeric salary rate 27.6%, skills fill 100%, experience fill 87.73%.
- TopCV: 583 rows, numeric salary rate 52.32%, skills fill 77.87%, experience fill 84.91%.
- TopDev: 100 rows, numeric salary rate 0%, skills fill 100%, experience fill 83%.
- TopDev salary is currently hidden behind `Login to view salary`, so numeric salary coverage of 0% should be framed as source behavior, not a parser failure.
- Current salary audit found 8 suspicious numeric salary rows.

## Proposed Blog Structure

1. Title
   Suggested title: `Vietnam IT Job Market Intelligence: từ crawl dữ liệu tuyển dụng đến phân tích bằng pandas`

2. Opening
   Explain the motivation: instead of guessing what the IT job market wants, collect public job postings and turn them into data for analysis. Position this as a portfolio project that demonstrates data engineering, scraping discipline, parsing, and exploratory data analysis.

3. Problem Statement
   Describe the questions the project is preparing to answer:
   - Which skills appear most often?
   - Which sources expose salary data?
   - How complete are title, company, location, skills, experience, and description fields?
   - What data-quality issues appear before deeper analysis?

4. Data Pipeline Overview
   Describe the current flow:
   - Crawl public job detail pages from ITviec, TopDev, TopCV.
   - Store raw JSONL for reproducibility.
   - Parse raw records into clean JSONL/CSV.
   - Use pandas notebook for inventory and EDA.
   - Later steps will clean data further and update trend reports.

5. Why Scrapling
   Explain that Scrapling is used as the first fetcher because it gives a convenient Python interface for fetching page content. Mention the fallback to `urllib` so the system remains simple and inspectable. Avoid claiming anti-bot bypass.

6. Responsible Crawling
   Include a short section explaining constraints:
   - Respect robots.txt.
   - Crawl sequentially with delay and limits.
   - Do not bypass captcha, Cloudflare, login, or anti-bot systems.
   - Do not scrape personal recruiter/contact data.
   - Keep raw data for parser iteration without repeatedly hitting source sites.

7. Raw To Clean Data
   Explain why raw JSONL stores HTML/JSON-LD/visible text/status/fetcher/timestamp, then parsers create a shared schema. Mention fields such as source, URL, job ID, title, company, location, salary, skills, experience, description, posted date, city, seniority, work mode, employment type, and salary period.

8. Pandas EDA: What Has Been Done
   Explain that the notebook currently:
   - Loads all clean CSVs.
   - Converts numeric salary/experience columns.
   - Parses date columns.
   - Checks schema and dtype consistency.
   - Measures null/fill rates.
   - Audits duplicate URLs.
   - Separates numeric salary rows from hidden/negotiable salary labels.
   - Explodes skills for early demand exploration.

9. Current Findings Snapshot
   Include the snapshot numbers above. Keep the interpretation careful:
   - TopCV currently exposes more numeric salary rows than ITviec in this snapshot.
   - TopDev is still useful for demand/skills/experience even without numeric salary.
   - Duplicate URLs exist because multiple sample/full/salary runs are loaded together.
   - Hidden salary labels are expected source behavior.

10. What This Shows To Recruiters
   Frame the skills demonstrated:
   - Building crawler boundaries and respecting constraints.
   - Separating crawler and parser responsibilities.
   - Keeping raw data reproducible.
   - Normalizing data into a shared schema.
   - Using pandas to reason about data quality before analysis.
   - Communicating limitations honestly.

11. Next Steps
   Keep this as a living-blog section:
   - Add notebook-only cleaning views: canonical dedupe, salary classification, skill normalization, location/work-mode analysis, issue log.
   - Regenerate trend reports after cleaning decisions are stable.
   - Add more data sources only if they meet crawl constraints.
   - Potential future production hardening: scheduling, storage layer, CI checks, monitoring, and dashboarding.

12. Closing
   End with a concise statement: this project is not just about scraping jobs; it is about turning messy public web data into an auditable dataset that can support market intelligence.

## Writing Guidelines

- Keep it honest and specific. Do not overstate production readiness.
- Avoid writing like a generic tutorial. Make it read like a project story.
- Use short sections and concrete examples.
- Mention file/path names sparingly, only when they help credibility.
- Use code snippets only if they clarify the pipeline; do not make the article too code-heavy.
- Include an “update later” note near the current snapshot or next-steps section.

## Implementation Tasks

1. Create `blog.md` at the repo root.
2. Write the blog using the proposed structure above.
3. Use the exact source list `ITviec`, `TopDev`, `TopCV`.
4. Include the current snapshot numbers with cautious wording.
5. Include a responsible crawling section.
6. Include a next-steps section that references future pandas cleaning work.
7. Do not modify source code, notebooks, raw data, processed data, reports, or existing plan files while writing the blog.

## Validation

- Confirm `blog.md` exists at repo root.
- Confirm the article does not mention `TopIT` as an implemented source.
- Confirm the article calls the project a `data pipeline prototype`, not a full production system.
- Confirm the article includes Scrapling accurately: first fetcher with fallback, not anti-bot bypass.
- Confirm the current snapshot numbers match the latest EDA summary if data has not changed; if data has changed, rerun the notebook or refresh the snapshot before publishing.
- Confirm no crawler/parser/notebook/data/report files were changed.

## Open Questions

- None.
