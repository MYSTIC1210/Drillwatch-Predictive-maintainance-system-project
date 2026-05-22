FROM python:3.11-slim

LABEL maintainer="DrillWatch Engineering"
LABEL description="Anomaly Detector & RUL Consumer — DrillWatch PdM System"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY consumer.py anomaly_detector.py rul_model.py ./

RUN useradd -m -u 1001 drillwatch
USER drillwatch

CMD ["python", "-u", "consumer.py"]
