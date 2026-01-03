"""Sort PocketTube database utility script.

This script sorts channels alphabetically in the PocketTube database file.
Runs without generating logs.
"""

# Standard library
import os
import sys
from pathlib import Path

# Disable logging BEFORE importing yrt modules
os.environ['YRT_NO_LOGGING'] = '1'

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Local (imported after setting YRT_NO_LOGGING)
from yrt.youtube import create_service_local, sort_db  # noqa: E402


def main() -> None:
    """Run database sorting."""
    print("PocketTube Database Sorter")
    print("=" * 40)

    service = create_service_local(log=False)
    sort_db(service=service, log=False)


if __name__ == '__main__':
    main()
