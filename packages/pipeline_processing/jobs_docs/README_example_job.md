# example_job

A small example job that demonstrates the `JOB` contract and the recommended job structure.

This file is useful as a template for adding new jobs under `packages/pipeline_processing/jobs`.

## Behavior

- Parses CLI arguments (simple example inputs)
- Calls a small, testable `_run(...)` function that performs deterministic, side-effect-free logic
- Returns a process exit code (0 on success)

## Example invocation

```bash
cd packages/pipeline_processing
PYTHONPATH=../.. poetry run python -m pipeline_processing.cli.main run example_job -- --some-flag
```

## Implementation guidance

- Keep the `JOB = (entrypoint, description)` tuple at the module top-level.
- Avoid heavy work at import time. Initialize resources inside `entrypoint` or `_run`.
- Add unit tests using `unittest.TestCase` that call `entrypoint` with a fake argv list.
