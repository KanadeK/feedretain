"""Run actual installed entry points on original local RSS fixtures."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(python):
    console = Path(python).with_name("feedretain.exe" if sys.platform == "win32" else "feedretain")
    subprocess.run([str(console), "--version"], check=True)
    baseline = ROOT / "examples/baseline.xml"
    digest = hashlib.sha256(baseline.read_bytes()).hexdigest()
    for fixture, code, policy in (
        ("retained.xml", 0, None),
        ("churned.xml", 1, None),
        ("cdn-move.xml", 1, None),
        ("cdn-move.xml", 0, ROOT / "examples/allow-cdn-move.json"),
    ):
        args = [
            python,
            "-m",
            "feedretain",
            str(baseline),
            str(ROOT / "examples" / fixture),
            "--json",
        ]
        if policy:
            args.extend(["--policy", str(policy)])
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode != code:
            raise RuntimeError(f"Wrong exit for {fixture}: {result.stderr}")
        report = json.loads(result.stdout)
        if "episode-001" in result.stdout or "media.example.invalid" in result.stdout:
            raise RuntimeError("Value-free output contract failed")
        print(f"{fixture}: exit {code}, {report['status']}")
    if hashlib.sha256(baseline.read_bytes()).hexdigest() != digest:
        raise RuntimeError("Input was modified")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else sys.executable)
