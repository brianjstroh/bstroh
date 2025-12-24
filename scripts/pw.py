#!/usr/bin/env python3
"""Set passwords for multiple sites at once."""

import sys
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from set_site_password import set_password  # noqa: E402

# List of sites to update
SITES = []


def main() -> None:
  """Set password for all sites."""
  if len(sys.argv) != 2:
    print("Usage: python scripts/pw.py <password>")
    print("       uv run python scripts/pw.py <password>")
    print()
    print("This will set the same password for all sites.")
    sys.exit(1)

  password = sys.argv[1]

  print(f"Setting password for {len(SITES)} sites...")
  print()

  failed = []
  for site in SITES:
    try:
      set_password(site, password)
    except Exception as e:
      print(f"✗ Failed: {site} - {e}")
      failed.append(site)

  print()
  print(f"Done! {len(SITES) - len(failed)}/{len(SITES)} sites updated")

  if failed:
    print()
    print("Failed sites:")
    for site in failed:
      print(f"  - {site}")
    sys.exit(1)


if __name__ == "__main__":
  main()
