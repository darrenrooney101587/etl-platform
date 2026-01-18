#!/usr/bin/env bash
# Validation script for Airflow DAG distribution implementation
set -euo pipefail

echo "========================================="
echo "Airflow DAG Distribution - Validation"
echo "========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/../.."

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓${NC} $1"
}

fail() {
    echo -e "${RED}✗${NC} $1"
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check 1: Infrastructure files
echo "Checking infrastructure files..."
required_infra_files=(
    "infra/airflow/README.md"
    "infra/airflow/terraform/main.tf"
    "infra/airflow/terraform/variables.tf"
    "infra/airflow/terraform/outputs.tf"
    "infra/airflow/terraform/providers.tf"
    "infra/airflow/k8s/airflow-values.yaml"
    "infra/airflow/k8s/airflow-configmap.yaml"
    "infra/airflow/k8s/namespaces.yaml"
    "infra/airflow/scripts/manage.sh"
    "infra/airflow/scripts/deploy_airflow.sh"
    "infra/airflow/scripts/setup_localstack.sh"
)

for file in "${required_infra_files[@]}"; do
    if [ -f "${ROOT_DIR}/${file}" ]; then
        pass "Found: ${file}"
    else
        fail "Missing: ${file}"
    fi
done
echo ""

# Check 2: DAG publisher package
echo "Checking orchestration package..."
required_publisher_files=(
    "packages/orchestration/README.md"
    "packages/orchestration/pyproject.toml"
    "packages/orchestration/__init__.py"
    "packages/orchestration/publisher.py"
    "packages/orchestration/validators.py"
    "packages/orchestration/generator.py"
    "packages/orchestration/cli/main.py"
    "packages/orchestration/templates/kubernetes_pod_dag.py.j2"
    "packages/orchestration/tests/test_publisher.py"
    "packages/orchestration/tests/test_validators.py"
)

for file in "${required_publisher_files[@]}"; do
    if [ -f "${ROOT_DIR}/${file}" ]; then
        pass "Found: ${file}"
    else
        fail "Missing: ${file}"
    fi
done
echo ""

# Check 3: Example DAGs
echo "Checking example DAG files..."
if [ -f "${ROOT_DIR}/packages/data_pipeline/airflow_dags/data_pipeline_example_job.py" ]; then
    pass "Found: data_pipeline example DAG"
else
    fail "Missing: data_pipeline example DAG"
fi

if [ -f "${ROOT_DIR}/packages/reporting_seeder/airflow_dags/reporting_seeder_refresh_all.py" ]; then
    pass "Found: reporting_seeder example DAG"
else
    fail "Missing: reporting_seeder example DAG"
fi
echo ""

# Check 4: Documentation
echo "Checking documentation..."
required_docs=(
    "docs/airflow/README.md"
    "docs/airflow/DEPLOYMENT.md"
    "docs/airflow/OPERATIONS.md"
    "docs/airflow/QUICKSTART.md"
    "docs/airflow/IMPLEMENTATION_SUMMARY.md"
)

for file in "${required_docs[@]}"; do
    if [ -f "${ROOT_DIR}/${file}" ]; then
        pass "Found: ${file}"
    else
        fail "Missing: ${file}"
    fi
done
echo ""

# Check 5: CI template
echo "Checking CI/CD integration..."
if [ -f "${ROOT_DIR}/.gitlab/ci/dag-publish-template.yml" ]; then
    pass "Found: GitLab CI template"
else
    fail "Missing: GitLab CI template"
fi
echo ""

# Check 6: Python syntax
echo "Validating Python syntax..."
python_files=(
    "packages/orchestration/publisher.py"
    "packages/orchestration/validators.py"
    "packages/orchestration/generator.py"
    "packages/orchestration/cli/main.py"
    "packages/data_pipeline/airflow_dags/data_pipeline_example_job.py"
    "packages/reporting_seeder/airflow_dags/reporting_seeder_refresh_all.py"
)

for file in "${python_files[@]}"; do
    if python -m py_compile "${ROOT_DIR}/${file}" 2>/dev/null; then
        pass "Valid syntax: ${file}"
    else
        fail "Syntax error: ${file}"
    fi
done
echo ""

# Check 7: Shell script syntax
echo "Validating shell scripts..."
shell_scripts=(
    "infra/airflow/scripts/manage.sh"
    "infra/airflow/scripts/deploy_airflow.sh"
    "infra/airflow/scripts/setup_localstack.sh"
)

for file in "${shell_scripts[@]}"; do
    if bash -n "${ROOT_DIR}/${file}" 2>/dev/null; then
        pass "Valid syntax: ${file}"
    else
        fail "Syntax error: ${file}"
    fi
done
echo ""

# Check 8: Scripts are executable
echo "Checking script permissions..."
for file in "${shell_scripts[@]}"; do
    if [ -x "${ROOT_DIR}/${file}" ]; then
        pass "Executable: ${file}"
    else
        warn "Not executable: ${file}"
    fi
done
echo ""

# Summary
echo "========================================="
echo "Validation complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Review documentation in docs/airflow/"
echo "  2. Deploy infrastructure following DEPLOYMENT.md"
echo "  3. Test with example DAGs from data_pipeline"
echo ""
