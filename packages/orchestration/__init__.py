"""Airflow DAG Publisher

This package provides utilities for generating and publishing Airflow DAG files
to S3, enabling independent package deployments without rebuilding the Airflow
control plane.

Key Components:
- DAG templates using KubernetesPodOperator
- S3 publisher with validation and guardrails
- CLI for CI/CD integration
"""

__version__ = "0.1.0"
