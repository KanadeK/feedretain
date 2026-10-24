# v0.1.0 validation

Local validation environment: Windows, CPython 3.13.16, 2026-10-24.

- 71 tests exercise the core flow, every protected field, exception policies,
  duplicates, timezone equivalence, bounded reads, parser limits and value-free
  CLI diagnostics. DTD rejection is exercised for UTF-8 and UTF-16 inputs.
- Branch-aware total coverage: 99%; core module: 100%.
- Ruff lint and formatting pass. The release gate builds wheel and sdist,
  creates an independent virtual environment and invokes installed console and
  module entry points from outside the checkout.
- Clean-install smoke cases: preserved feed passes; GUID churn fails; an
  unreviewed CDN change fails; its exact-input approved policy passes.
- Input hashes are checked before/after the smoke flow to verify preservation.

Self-review verified linear GUID matching, ambiguity handling, safe XML
declarations, deterministic reports, policy hash binding and unused approvals.
It also ensured source distributions include the actual XML/JSON examples.
The tool does not claim whole-feed validation or live migration verification.

There are zero runtime dependencies. Shared pinned development tooling was
checked with pip-audit on this date: no known advisories were reported for the
twelve explicitly enumerated tool/runtime packages. This is a point-in-time
advisory check, not proof of the absence of defects.

CI runs the same release gate on Linux 3.11/3.13 and Windows/macOS 3.13; consult
the workflow on the release commit for actual remote results.
