# v0.1.0

Initial offline RSS 2.0 podcast migration continuity gate.

- Exact GUID retention across reordering and new episodes.
- Protected title, UTC publication time, GUID interpretation and enclosure fields.
- Conservative unique-enclosure hints for possible GUID changes.
- Exact-input hash-bound, per-change exception policies; no blanket ignores.
- Bounded XML parsing with DTD rejection and value-free location reports.
- Zero runtime dependencies; Python 3.11+; wheel and sdist with SHA-256 checksums.

See VALIDATION.md for actual tests and the release commit's CI for platform results.
Limits: no Atom/RSS 1.0, extension-specific fields, media verification, live feed
redirect checking or guarantee of subscriber/platform behavior.
