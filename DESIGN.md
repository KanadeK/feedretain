# Requirements and acceptance

User: a podcast publisher reviewing a hosting import. Workflow: save old/new RSS,
compare locally, investigate exact item locations, optionally record reviewed
changes bound to those exact files, then rerun before changing feed routing.

Architecture: a bounded ElementTree builder rejects all DTD declarations and
limits depth/element count; RSS core items become immutable episode records.
Dictionary lookup matches exact GUIDs in linear expected time. URL counters
provide conservative churn hints, never identity merges. A strict JSON policy
matches `(code, old item position, new item position)` and both input hashes.

Acceptance requires:

1. Retained GUIDs survive reorder/additions and equivalent date timezone changes.
2. Missing episodes and changes to every protected field cause real failures.
3. Duplicate identities and malformed or hostile inputs fail closed with no values.
4. Policy changes allow only named issues on exact files; stale/unused entries fail.
5. Input files remain unchanged, and signed media URLs/titles/GUIDs are not printed.
6. Distribution build and clean installed console/module flows pass.
7. Remote CI, commit mapping and the sole-contributor requirement pass before release.

Limits: no automatic semantic ID remapping, whole-feed standards validation,
HTTP operations or claims about subscriber behavior. Field selection is explicit
so the project remains small and testable. All fixtures are original synthetic data.
