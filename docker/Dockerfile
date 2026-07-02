FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    cron \
    procps \
    tzdata \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -snf /usr/share/zoneinfo/America/New_York /etc/localtime && \
    echo "America/New_York" > /etc/timezone

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/app/scripts:/root/.local/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
COPY data/universes.json data/universes.json
COPY data/universes/ data/universes/

RUN uv pip install --system -e .[dev,viz,ml]

COPY docker/crontab /etc/cron.d/quant-hub
COPY docker/entrypoint.sh /entrypoint.sh
COPY scripts/weekly-full-coverage.sh scripts/weekly-full-coverage /app/scripts/
COPY scripts/ml-phase-swing-sp500-index.sh /app/scripts/

RUN chmod 0644 /etc/cron.d/quant-hub && \
    echo "" >> /etc/cron.d/quant-hub && \
    chmod +x /entrypoint.sh /app/scripts/weekly-full-coverage.sh /app/scripts/weekly-full-coverage /app/scripts/ml-phase-swing-sp500-index.sh

RUN mkdir -p /app/data/output /app/data/cache /app/logs

ENV TZ=America/New_York

VOLUME ["/app/data", "/app/logs"]

USER root

ENTRYPOINT ["/entrypoint.sh"]
