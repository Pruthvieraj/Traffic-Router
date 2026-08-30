"""Shared pytest setup: puts src/ and the project root on sys.path so tests
can `import qubo_tsp`, `import app`, etc. without needing the project
installed as a package."""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_PROJECT_ROOT, "src")

for path in (_PROJECT_ROOT, _SRC):
    if path not in sys.path:
        sys.path.insert(0, path)
