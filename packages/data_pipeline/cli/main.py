import argparse
import sys
from typing import Iterable

from data_pipeline.jobs.registry import get_registry


def _list_jobs() -> int:
    registry = get_registry()
    for name in sorted(registry.keys()):
        print(name)
    return 0


def _run_job(name: str, argv: Iterable[str]) -> int:
    registry = get_registry()
    job = registry.get(name)
    if job is None:
        available = ", ".join(sorted(registry.keys()))
        print(f"Unknown job '{name}'. Available jobs: {available}", file=sys.stderr)
        return 1
    return job.entrypoint(list(argv))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="data-pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List available jobs")

    run_parser = subparsers.add_parser("run", help="Run a named job")
    run_parser.add_argument("job_name", help="Job to run")
    run_parser.add_argument("job_args", nargs=argparse.REMAINDER)

    help_parser = subparsers.add_parser("help", help="Show job-specific help")
    help_parser.add_argument("job_name", help="Job to show help for")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "list":
        sys.exit(_list_jobs())

    if args.command == "run":
        job_args = args.job_args
        if job_args and job_args[0] == "--":
            job_args = job_args[1:]
        sys.exit(_run_job(args.job_name, job_args))

    if args.command == "help":
        sys.exit(_run_job(args.job_name, ["--help"]))

    parser.print_usage()
    sys.exit(2)


if __name__ == "__main__":
    main()
