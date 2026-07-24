# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8501

WORKDIR /app

# Install dependencies before application code so dependency layers can be cached.
COPY requirements.runtime.txt ./
RUN pip install --no-cache-dir -r requirements.runtime.txt

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY --chown=app:app modeling ./modeling
COPY --chown=app:app parsers ./parsers
COPY --chown=app:app scrapers ./scrapers
COPY --chown=app:app streamlit_salary_regression_opencode.py ./
# The dashboard needs a small, versioned model bundle to be usable on first start.
COPY --chown=app:app data/modeling/salary_regression/safe_baseline ./data/modeling/salary_regression/safe_baseline

RUN mkdir -p data/raw data/processed data/reports data/analysis \
    && chown -R app:app /app/data

USER app

EXPOSE 8501

CMD ["sh", "-c", "streamlit run streamlit_salary_regression_opencode.py --server.address=0.0.0.0 --server.port=${PORT:-8501}"]
