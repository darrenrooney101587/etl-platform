"""Hello-world smoke-test job for the pipeline_processing package.

This job exists to support Kubernetes and CI smoke checks. It intentionally
avoids external dependencies (S3, DB, AWS) and simply logs a message.
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
    parser = argparse.ArgumentParser(prog="file-processing run hello_world")
    parser.add_argument("--message", default="hello world", help="Message to log")
    args = parser.parse_args(argv)

    logger.info("pipeline_processing hello_world: %s", args.message)
    return 0


JOB = (entrypoint, DESCRIPTION)
