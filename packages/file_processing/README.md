# file_processing

This package contains the file processing components for the ETL platform: the SNS listener, the S3 data quality job, processors, repositories, and tests.

## Jobs

This package contains the following jobs. See their individual READMEs for runtime details and usage.

- **[sns_listener](jobs/README_sns_listener.md)**: In-process HTTP server that listens for SNS notifications and triggers the data quality job.
- **[s3_data_quality_job](jobs/README_s3_data_quality_job.md)**: Processes a single S3 file to validate data quality.
- **[hello_world](jobs/README_hello_world.md)**: Simple smoke test job.

## Testing

This package uses `unittest.TestCase` for unit tests.

Run the package tests with:

```bash
python -m unittest discover packages/file_processing/tests -v
```

We include tests that cover the `CircuitBreaker` behavior and the S3 `NoSuchKey` handling in the processor.

## Local Docker development (recommended)

`file_processing` imports ORM models from `etl_database_schema`. To avoid pulling the schema package from GitLab/VPN during each Docker build, we use a sibling checkout staged into the Docker build context.

1) One-time: clone the schema repo next to this repo:
```bash
git clone git@gitlab.dev-benchmarkanalytics.com:etl/etl-database-schema.git ../etl-database-schema
```

2) Ensure you have a local env file:
```bash
cp packages/file_processing/.env.example packages/file_processing/.env
```

3) Build the local image (stages schema into `.local/etl-database-schema` and builds from repo root):
```bash
./packages/file_processing/scripts/build.sh
```

When `etl-database-schema` changes, run `git pull` in `../etl-database-schema` and rebuild:
```bash
cd ../etl-database-schema && git pull
cd -
./packages/file_processing/scripts/build.sh
```
