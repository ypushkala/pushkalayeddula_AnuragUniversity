# API image. Data and models are generated at build time from the fixed seed, so the
# container starts in seconds and every build gives the same numbers.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY prativimb ./prativimb
COPY assets ./assets
RUN pip install --no-cache-dir -e .
COPY scripts ./scripts
COPY reports ./reports
RUN python -m prativimb.pipeline all

ENV PRATIVIMB_SPEED=10
EXPOSE 8000
CMD ["uvicorn", "prativimb.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
