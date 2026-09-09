#!/usr/bin/env python3
"""Repository-local wrapper for the dependency doctor."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proof2stim.doctor import main

if __name__ == "__main__":
    raise SystemExit(main())
