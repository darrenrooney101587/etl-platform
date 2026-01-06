"""CLI entrypoint for file_processing package.

Uses the centralized CLI builder from etl_core.
"""
import sys

from etl_core.cli import main_for_package


def main() -> None:
    """Main entry point for the file-processing CLI."""
    raise SystemExit(main_for_package("file-processing", "file_processing"))


if __name__ == "__main__":
    main()
