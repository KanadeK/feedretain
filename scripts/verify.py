"""Run the release gate and exercise the built wheel outside the source tree."""

import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=ROOT, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True)


def main():
    run(sys.executable, "-m", "ruff", "check", ".")
    run(sys.executable, "-m", "ruff", "format", "--check", ".")
    run(sys.executable, "-m", "coverage", "run", "-m", "pytest", "-q")
    run(sys.executable, "-m", "coverage", "report", "--fail-under=90")
    run(sys.executable, "-m", "build")
    wheels = list((ROOT / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Expected exactly one wheel in dist; remove old builds first")
    with tempfile.TemporaryDirectory(prefix="clean-wheel-") as temp:
        folder = Path(temp)
        venv.create(folder / "env", with_pip=True)
        python = folder / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        clean_env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        run(str(python), "-m", "pip", "install", str(wheels[0]), cwd=folder, env=clean_env)
        run(sys.executable, str(ROOT / "scripts/smoke.py"), str(python), cwd=folder, env=clean_env)
    print("Release gate passed, including isolated wheel installation and core flow.")


if __name__ == "__main__":
    main()
