"""CLI entrypoint for reporting_seeder jobs."""
from packages.etl_core.cli import main_for_package


def main() -> None:
    """Invoke the shared package CLI dispatcher for reporting_seeder."""
    raise SystemExit(main_for_package("reporting-seeder", "reporting_seeder"))


if __name__ == "__main__":
    main()
