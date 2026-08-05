#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parent
TEST_MODULES = (
    "test_build_kanji_addon",
    "test_direct_release_contract",
    "test_direct_release_repository",
    "test_render_docs",
    "test_public_site",
    "test_usage_telemetry_client",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the public repository's portable synthetic tests."
    )
    parser.add_argument(
        "mode",
        choices=("fast",),
        nargs="?",
        default="fast",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sys.path.insert(0, str(TEST_ROOT))
    discovered = unittest.TestSuite(
        unittest.defaultTestLoader.loadTestsFromName(name)
        for name in TEST_MODULES
    )
    print(f"Running {discovered.countTestCases()} public tests", file=sys.stderr)
    result = unittest.TextTestRunner(
        verbosity=2 if args.verbose else 1
    ).run(discovered)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
