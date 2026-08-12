"""Small non-Kit target used to validate the Phase 6EX outer sampler."""

from __future__ import annotations

import argparse
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=float, required=True)
    args = parser.parse_args()
    payload = bytearray(1024 * 1024)
    deadline = time.monotonic() + args.duration_seconds
    while time.monotonic() < deadline:
        payload[0] = (payload[0] + 1) % 256
        time.sleep(0.02)


if __name__ == "__main__":
    main()
