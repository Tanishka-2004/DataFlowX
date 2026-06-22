FROM apache/airflow:2.8.1-python3.10

USER root

# Install required system packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    && apt-get autoremove -yqq --purge \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Copy requirements and install
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# Create necessary directories
RUN mkdir -p /opt/airflow/data_lake/bronze \
    && mkdir -p /opt/airflow/data_lake/silver \
    && mkdir -p /opt/airflow/data_lake/gold \
    && mkdir -p /opt/airflow/logs

ENV PYTHONPATH="/opt/airflow/project:${PYTHONPATH}"
WORKDIR /opt/airflow/project
