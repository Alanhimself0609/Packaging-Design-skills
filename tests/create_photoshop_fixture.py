from __future__ import annotations

import argparse
from pathlib import Path

from fixture_factory import build_fixture


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(build_fixture(args.output.resolve()))


if __name__ == "__main__":
    main()
