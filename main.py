FROM python:3.11-slim

LABEL maintainer="DrillWatch Engineering"
LABEL description="FastAPI Backend — DrillWatch PdM System"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN useradd -m -u 1001 drillwatch
USER drillwatch

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
