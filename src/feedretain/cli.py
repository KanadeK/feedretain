"""CLI for local podcast feed continuity checks."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import InputError, audit


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gate a local RSS podcast hosting migration")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--policy", type=Path, help="exact-input, per-change approvals")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        result = audit(args.baseline, args.candidate, policy=args.policy)
    except (InputError, OSError) as exc:
        detail = str(exc) if isinstance(exc, InputError) else "cannot_read_input"
        print("Input error: " + detail, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for issue in result["issues"]:
            marker = "ALLOWED" if issue["allowed"] else "FAIL"
            print(
                f"{marker}: {issue['code']} baseline item {issue['before_item']} "
                f"→ candidate item {issue['after_item']}"
            )
        for hint in result["hints"]:
            print(
                f"HINT: possible_guid_change baseline item {hint['before_item']} "
                f"→ candidate item {hint['after_item']} (not automatically matched)"
            )
        print(
            f"{result['status'].upper()}: {result['retained_episodes']}/"
            f"{result['baseline_episodes']} historical GUIDs retained; "
            f"{len(result['new_items'])} new identities"
        )
    return 0 if result["status"] == "passed" else 1
