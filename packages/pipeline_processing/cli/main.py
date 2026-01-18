from packages.etl_core.cli import main_for_package


def main() -> None:
    raise SystemExit(main_for_package("pipeline-processing", "pipeline_processing"))


if __name__ == "__main__":
    main()
