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

## Adjacent Project: vn-it-job-collector Plan
- This section applies only to `G:\project\vn-it-job-collector`, a separate Git repository. Do not apply its architecture or commands to this prototype.
- Objective: responsibly collect public job postings for a focused Web/App Software Development salary dataset before considering descriptive statistics or Linear Regression.
- Sources: ITviec, TopCV, and VietnamWorks. Use Scrapling's standard HTTP `Fetcher` only, respect robots rules, crawl sequentially with low delays, and store data locally as JSONL/CSV.
- Never add stealth fetchers, proxy rotation, CAPTCHA/Cloudflare bypasses, logins, recruiter/contact collection, LinkedIn, or Google Jobs crawling.
- VietnamWorks robots were verified at `https://www.vietnamworks.com/robots.txt`; its public IT listing is `https://www.vietnamworks.com/viec-lam?g=5`, and accepted details match `...-<job_id>-jv`.

### Scope
- Include only Web/App Software Development roles: Backend, Frontend, Fullstack, Software, Web, Mobile/Android/iOS, and Application Developer/Engineer roles.
- Include language/framework-specialized roles only when a developer/engineer semantic is explicit: Java/Spring, .NET/C#/ASP.NET, PHP/Laravel, Python/Django/FastAPI/Flask, JavaScript/TypeScript/Node.js/NestJS/Express, React/Next.js, Vue/Nuxt, Angular, Go/Golang, Ruby/Rails, Kotlin, Swift, Flutter/Dart, React Native, WordPress, and Shopify.
- Vietnamese role equivalents are in scope when they explicitly mean developer/engineer, including accented and unaccented forms of `lập trình viên` and explicit software-development phrases.
- Seniority terms do not determine scope: Senior, Junior, and Lead roles remain only when the title also carries accepted developer/engineer semantics.
- Exclude QA/QC/Tester/Automation Test, DevOps/SRE/Infrastructure, system/network/support/helpdesk, Data/AI/ML-only, BA/Product/Project Manager, Sales/Consultant/Designer, Embedded/Firmware, Game, ERP/Odoo, PLC, IoT hardware, and pure Manager/Architect roles.
- Hard exclusions always take precedence over positive role terms. Therefore QA Automation Engineer, Data Engineer, Embedded Software Engineer, and DevOps Engineer must be rejected.

### Required Scope Filter Design
- Add a versioned, editable `config/software_dev_scope.yaml`, loaded with `yaml.safe_load`; add a bounded direct PyYAML dependency because Python 3.10 has no standard YAML parser.
- Validate the configuration and required scope version at load time. Store stable rule IDs rather than raw regexes in outputs.
- Normalize title case, Vietnamese accents and `đ`, whitespace, punctuation, and technology variants such as `.NET`, C#, Node.js, and full-stack.
- Matching precedence: hard exclusion; explicit accepted family role; language/framework plus required role marker; reject missing or ambiguous titles.
- Return and persist `scope_status`, `job_family`, `matched_patterns`, `rejection_reason`, and `title_scope_version`.
- Use site categories and search pages only for broad discovery. Update ITviec defaults to Software Development terms and remove `devops`, `data`, and `tester` from default discovery keywords.

### Crawl Flow and Evidence Rules
- Replace URL-only discovery with a title-aware `ListingCandidate` contract containing at least canonical URL and listing title. Engine-level discovery context must also retain listing URL, keyword, and page.
- Enhance HTML extraction and source adapters to collect visible anchor text and structured list-item names where available; update ITviec, TopCV, VietnamWorks fixtures and adapters together.
- Prefilter canonical, non-duplicate listing candidates by title before requesting a detail page. Candidates rejected at this phase must be audited but never detail-fetched.
- Detail page title is authoritative: extract JSON-LD `JobPosting.title` first, then H1. Listing and detail titles do not need to be equal; retain the job if the authoritative detail title is in scope.
- If the detail title is missing or out of scope, audit the rejection and do not append HTML, visible text, JSON-LD, or any other raw-detail evidence to JSONL. The response may exist only transiently in memory for validation.
- For accepted records, preserve listing title, authoritative detail title, and all scope metadata in raw JSONL; retain scope metadata through processed JSONL/CSV even when parsing reports `missing_jobposting_jsonld`.
- Write `data/reports/<run_id>_scope_skips.csv` with exactly these minimum columns: `run_id`, `source`, `url`, `listing_url`, `listing_title`, `detail_title`, `phase`, `scope_status`, `job_family`, `matched_patterns`, `rejection_reason`, `title_scope_version`, `occurred_at`. Never put HTML or visible text in this file.
- Define `--limit` as a strict maximum number of detail-page HTTP fetch attempts, including retries. Listing and robots requests are separately bounded by `--pages-per-keyword` and normal robots caching. Track `discovered_urls`, `scope_qualified`, `detail_requests`, and `saved_records` separately.

### Robots Hardening
- Robots handling must fail closed for fetch errors, missing status, non-2xx status, HTML-like payloads, malformed/non-robots content, or a response without a valid `User-agent:` directive.
- Extend the fetch response contract with optional content type so the policy can reject HTML masquerading as a successful robots response.
- Do not consider a HTTP 200 response sufficient evidence that robots rules are valid.

### Salary Data Before Modelling
- Do not build Linear Regression or show P10-P90 from the current data contract.
- Add a dedicated salary-normalization milestone after scope filtering: preserve `salary_raw`; extract numeric minimum/maximum, currency, period, and parse status; retain negotiable/unknown salary labels without inventing numeric values.
- Use JSON-LD `baseSalary` where present, then carefully validated source-specific visible salary fields. Do not infer currency, period, or ranges from ambiguous text.
- Replace the misleading `numeric_salary_records` metric, which currently only checks for a non-empty `salary_raw`, with separate counts for salary present, numeric, range, negotiable, known currency, known period, and comparable salaries.
- Compute descriptive salary ranges only from comparable observations. Treat VND monthly salary as its own comparable set; do not convert currencies without an explicit, documented exchange-rate policy.
- Only evaluate a model after coverage and missingness are measured by `job_family`, seniority, location, and salary representation.

### Implementation Order and Tests
1. Add and validate the scope configuration and pure title matcher.
2. Convert discovery to title-aware candidates and update all source fixtures.
3. Integrate listing prefilter, detail verification, scope skip reporting, strict detail fetch budget, and raw-record metadata.
4. Harden robots response validation and add tests for valid text, HTML HTTP 200, malformed content, and denied paths.
5. Propagate scope fields through the parser, clean schema, and documentation.
6. Add salary normalization and quality metrics as a separate milestone; defer modelling.
- Test title conflicts: QA Automation Engineer, Data Engineer, Embedded Software Engineer, DevOps Engineer, accented/unaccented Vietnamese titles, framework-only titles without a role marker, missing titles, and listing/detail title differences.
- Test crawler behavior: a fake fetcher must prove listing-prefilter rejects never request detail URLs; detail rejects never create raw records; accepted records preserve scope metadata in raw and processed outputs; `--limit` never exceeds the configured detail HTTP-request budget.
