# Airflow Control Plane Dockerfile
# 
# This image contains Apache Airflow plus the airflow_control_plane package
# for automatic DAG generation and synchronization.

FROM apache/airflow:2.8.0-python3.10

USER root

# Install system dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Copy packages directory
COPY packages /app/packages

# Set Python path to include packages
ENV PYTHONPATH=/app/packages

# Install etl_core and airflow_control_plane
RUN pip install --no-cache-dir \
    /app/packages/etl_core \
    /app/packages/airflow_control_plane

# Set working directory
WORKDIR /app

# Default command runs the DAG sync
CMD ["airflow-control-plane", "sync", "--dags-dir", "/opt/airflow/dags"]
