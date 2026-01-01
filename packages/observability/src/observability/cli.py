"""CLI entrypoint for the observability module.

Provides a minimal `main()` used by the `etl-observe` console script. It
prints a short help message and exits 0. This is intentionally minimal so
images expose a stable ENTRYPOINT for EKS Jobs.
"""
from __future__ import annotations

import sys
from typing import List


def main(argv: List[str] | None = None) -> int:
    """Minimal observability CLI main.

    Args:
        argv: Command line args (defaults to sys.argv[1:]).

    Returns:
        Exit code integer (0 on success).
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv or "-h" in argv or "--help" in argv:
        print("etl-observe: placeholder CLI. Usage: etl-observe [--help]")
        return 0

    print("etl-observe: received args:", " ".join(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
