from packages.etl_core.cli import main_for_package


def main() -> None:
    raise SystemExit(main_for_package("etl-observe", "observability"))


if __name__ == "__main__":
    main()
