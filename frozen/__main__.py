"""Validate every shipped frozen library: ``python -m traj2rules.frozen``."""

from .loader import _main

if __name__ == "__main__":
    raise SystemExit(_main())
