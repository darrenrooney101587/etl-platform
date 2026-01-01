"""CLI entrypoint for the file_processing module.

This module provides a minimal placeholder `main()` used when the
`file-processing` console script is invoked. It prints a simple help
message and exits with code 0. This is intentionally minimal and
suitable for EKS Job ENTRYPOINT defaults.
"""
from __future__ import annotations

import sys
from typing import List


def main(argv: List[str] | None = None) -> int:
    """Minimal CLI main that prints help and exits 0.

    Args:
        argv: List of command line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code integer (0 on success).
    """
    if argv is None:
        argv = sys.argv[1:]

    # If user asked for help or provided no args, print a short help message
    if not argv or "-h" in argv or "--help" in argv:
        print("file-processing: placeholder CLI. Usage: file-processing [--help]")
        return 0

    # For any other args just echo them and exit 0 (keeps placeholder behavior)
    print("file-processing: received args:", " ".join(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
