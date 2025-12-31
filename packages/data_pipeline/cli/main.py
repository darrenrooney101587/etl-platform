import argparse
import sys

from data_pipeline.runners import health, ingest, transforms


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="data-pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    transform_parser = subparsers.add_parser("run-transform", help="Run a transform feed")
    transform_parser.add_argument("--feed", required=True, help="Feed identifier")
    transform_parser.set_defaults(handler=lambda args: transforms.run(args.feed))

    ingest_parser = subparsers.add_parser("ingest", help="Run an ingest source")
    ingest_parser.add_argument("--source", required=True, help="Source identifier")
    ingest_parser.set_defaults(handler=lambda args: ingest.run(args.source))

    health_parser = subparsers.add_parser("healthcheck", help="Run health checks")
    health_parser.set_defaults(handler=lambda args: health.run())

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    exit_code = args.handler(args)
    sys.exit(exit_code)
