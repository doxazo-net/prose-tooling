import sys
from pathlib import Path

# Make the client module (bin/prose_check.py) importable in tests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))
