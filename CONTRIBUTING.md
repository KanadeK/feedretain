# Contributing

Open a minimal, redacted bug report with expected and observed behavior.
Discuss changes to the documented contract before extending the scope.
Use original synthetic fixtures; never upload private production inputs.

Create a virtual environment, install `python -m pip install -e ".[dev]"`,
then run `python scripts/verify.py`. Include regression tests that would fail
without a behavior fix. Keep network-dependent checks out of the tests.

CI checks and builds; it does not write to the repository. This repository's
current owner-only commit policy means external patches are reviewed as
suggestions rather than automatically merged. Third-party copyright and
license notices must always be retained where applicable.
