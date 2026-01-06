# observability

Platform monitoring and health signals.

## Responsibilities

- S3 metrics
- Database metrics
- Database monitoring checks
- Freshness / latency monitors

## Jobs and CLI

This package exposes a minimal CLI that discovers jobs under `observability.jobs`.
The CLI entrypoint lives at `observability.cli.main` and supports `list`, `run` and `help` subcommands.

Add jobs under `packages/observability/src/observability/jobs` as modules that expose a `JOB` variable:

```python
# packages/observability/src/observability/jobs/my_check.py
from typing import List

def entrypoint(argv: List[str]) -> int:
    print('running my check', argv)
    return 0

JOB = (entrypoint, 'Run observability check')
```

Use the console script (when installed) or run the module directly for local testing. This pattern keeps discovery and orchestration consistent across packages.
