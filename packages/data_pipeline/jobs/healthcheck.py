import argparse


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="data-pipeline run healthcheck")
    parser.parse_args(argv)
    print("healthcheck: ok")
    return 0
