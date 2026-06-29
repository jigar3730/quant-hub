FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    cron \
    procps \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN ln -snf /usr/share/zoneinfo/America/New_York /etc/localtime && \
    echo "America/New_York" > /etc/timezone

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY data/universes.json data/universes.json
COPY data/universes/ data/universes/

RUN uv pip install --system -e .[dev,viz]

COPY docker/crontab /etc/cron.d/quant-hub
COPY docker/entrypoint.sh /entrypoint.sh
COPY scripts/weekly-full-coverage.sh scripts/weekly-full-coverage /app/scripts/

RUN chmod 0644 /etc/cron.d/quant-hub && \
    echo "" >> /etc/cron.d/quant-hub && \
    chmod +x /entrypoint.sh /app/scripts/weekly-full-coverage.sh /app/scripts/weekly-full-coverage

RUN mkdir -p /app/data/output /app/data/cache /app/logs

ENV TZ=America/New_York

VOLUME ["/app/data", "/app/logs"]

USER root

ENTRYPOINT ["/entrypoint.sh"]
