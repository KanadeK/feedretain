# feedretain

Catch broken podcast hosting migrations **before** changing your feed URL.
Compare two local RSS 2.0 feeds and require every historical episode GUID to
survive. Reordering and new episodes are allowed; identity loss and changes to
protected episode metadata fail the gate unless explicitly reviewed.

A feed can be valid XML yet give listeners duplicate episodes or lose an archive.
[Apple's migration guidance](https://podcasters.apple.com/support/837-change-the-rss-feed-url)
requires unchanged episode GUIDs. The
[IAB measurement guidelines](https://github.com/IABTechLab/Podcast-Technical-Measurement/blob/main/PTM-Guidelines_v2.3.md)
also describe how media URL changes can trigger repeated downloads. feedretain
turns those risks into a small offline migration check.

## Install and try it

Requires Python 3.11+. No runtime dependencies or network access while checking.

```sh
git clone https://github.com/KanadeK/feedretain.git
cd feedretain
python -m venv .venv
```

Activate using `.venv\Scripts\Activate.ps1` on PowerShell or
`. .venv/bin/activate` on Linux/macOS, then:

```sh
python -m pip install .
feedretain examples/baseline.xml examples/retained.xml
```

The result passes: both historical GUIDs remain, even though their order changed,
a new episode appeared and one timestamp uses an equivalent timezone offset.

An intentionally broken import exits `1` and identifies missing historical items:

```sh
feedretain examples/baseline.xml examples/churned.xml --json
```

Run the complete installed-CLI demonstration, which verifies both outcomes:

```sh
python scripts/smoke.py
```

A standalone wheel is also available without cloning:

```sh
python -m pip install https://github.com/KanadeK/feedretain/releases/download/v0.1.0/feedretain-0.1.0-py3-none-any.whl
```

## Check your migration

Save your old feed and prospective new feed as local files, then run:

```sh
feedretain old-feed.xml new-feed.xml --json > migration-report.json
```

| Protected property | Comparison |
|---|---|
| Episode identity | Exact GUID string, including its whitespace; no title matching |
| Historical coverage | Every old GUID must remain unless that item is explicitly waived |
| GUID interpretation | `isPermaLink`, including its default `true` value |
| Title | Plain XML text, with surrounding whitespace removed |
| Publication time | Parsed timezone-aware date, compared as a UTC instant |
| Enclosure URL | Exact HTTP(S) URL, including query parameters |
| Enclosure length and type | Integer length and case-insensitive MIME type |

Duplicate or missing GUIDs, missing required podcast fields, invalid dates and
malformed enclosures are input errors. Unlike general RSS, **this podcast gate**
requires one GUID, title, timezone-aware pubDate and enclosure per item.

If a missing old GUID and a new GUID have the same unique enclosure URL, the
report adds a `possible_guid_change` hint. This never establishes identity or
automatically pairs episodes. Ambiguous URLs produce no such hint.

The JSON report contains issue codes and **1-based item positions** in the two
input files. It omits GUID values, titles, enclosure URLs and local paths.
`baseline_sha256` and `candidate_sha256` identify the exact source bytes. Hashes
are correlation receipts, not anonymization of a guessable private feed.

Exit `0`: all changes passed or were explicitly allowed. Exit `1`: an unapproved
continuity change. Exit `2`: invalid input/policy or a file access error. No feed
is rewritten and no URL from a feed is fetched.

## Allow a deliberate change precisely

For a reviewed CDN move:

```sh
feedretain examples/baseline.xml examples/cdn-move.xml
feedretain examples/baseline.xml examples/cdn-move.xml --policy examples/allow-cdn-move.json
```

The first command exits `1`; the second exits `0`. The supplied policy names
`enclosure_url_changed`, baseline item `1`, candidate item `1`, and a reason.
It also binds to the SHA-256 hashes of **both complete feed files**.

To create your own policy, copy [the example](examples/allow-cdn-move.json), set
both hashes from your JSON report and list exactly the observed changes you have
reviewed. Supported codes are `missing_episode`, `title_changed`,
`pubdate_changed`, `guid_permalink_changed`, `enclosure_url_changed`,
`enclosure_length_changed`, and `enclosure_type_changed`. A missing episode uses
`after_item: null`. Reasons must be nonempty and at most 200 characters.

Unknown keys/codes, duplicate entries, mismatched hashes and unused approvals
are errors. There is no blanket ignore switch. A pass with allowed changes is
not a claim that all historical episodes were preserved: inspect the retained
count and each `allowed` issue. The tool cannot verify who reviewed a policy.

## Limits and privacy

- Local RSS 2.0 podcast core only, with unqualified `rss`, `channel` and item
  elements. Atom, RSS 1.0, extension-specific metadata, chapters, descriptions,
  artwork and full platform validation are outside v0.1.0.
- It checks identity and selected metadata, not media bytes, HTTP redirects,
  download accessibility, platform state or whether subscribers migrated.
- Each feed is at most 8 MiB and 10,000 episodes. XML depth is at most 64, with
  at most 200,000 elements. DTDs are forbidden, including UTF-16 documents, so
  declared entities cannot be expanded. Policy input is at most 1 MiB.
- `pubDate` uses Python's email date parser and must include a timezone. It is
  not a comprehensive RSS date-syntax validator. Keep XML inputs stable while
  comparing; receipts refer to the bytes actually read.
- Issue positions, counts and file hashes can reveal information. Case values
  and feed contents stay local, but review reports before sharing them.

## Development and cleanup

```sh
python -m pip install -e ".[dev]"
python scripts/verify.py
```

The gate runs Ruff, unit/integration/CLI tests, branch-aware coverage with a 90%
minimum, builds wheel and sdist, then installs the wheel in a clean environment
and runs the core flow outside the source tree. CI runs on Linux, Windows and
macOS. [VALIDATION.md](VALIDATION.md) records actual local release results.

Uninstall with `python -m pip uninstall feedretain`. After deactivation, remove
the `.venv` you created if no longer needed. The tool creates no persistent
working files. Reports redirected to files are yours to retain or delete.
Development build/test caches can be removed from the checkout.

## Related tools

[podcast-feed-maker](https://github.com/atelier-socle/podcast-feed-maker) provides
a broader Swift feed generation/parsing/auditing library, including FeedDiff.
[feedvalidator](https://github.com/rubys/feedvalidator) checks feed validity.
feedretain focuses on a small cross-platform CLI retention gate, exact-input
exceptions, conservative churn hints and reports without feed values. It does
not claim to replace those tools or prove platform acceptance.

## 中文说明

feedretain 在更换播客托管服务前，对比两份本地 RSS 2.0 文件，检查旧节目的 GUID
是否保留，以及标题、发布时间、媒体 URL、长度、类型是否改变。新增和重排节目允许
通过；时区不同但表示同一时刻也能通过。不会联网获取媒体或修改原文件。输出仅含
问题代码和条目位置，例外规则必须绑定两份原文件的哈希。完整演示见
`python scripts/smoke.py`。它不能替代迁移后的重定向和播放器实测。

MIT. See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and
[DESIGN.md](DESIGN.md).
