"""Hello-world smoke-test job for the reporting_seeder package.

This job exists to support Kubernetes and CI smoke checks. It intentionally
avoids external dependencies (database access, AWS) and simply logs a message.
"""

from __future__ import annotations

import argparse
import logging
from typing import List


logger = logging.getLogger(__name__)

DESCRIPTION = "Hello world smoke-test job"


def entrypoint(argv: List[str]) -> int:
    """Run the hello-world job.

    Args:
        argv: CLI arguments passed after the job name.

    Returns:
        0 on success.
    """
    parser = argparse.ArgumentParser(prog="reporting-seeder run hello_world")
    parser.add_argument("--message", default="hello world", help="Message to log")
    args = parser.parse_args(argv)

    logger.info("reporting_seeder hello_world: %s", args.message)
    return 0


JOB = (entrypoint, DESCRIPTION)
