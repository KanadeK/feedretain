import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import pytest

from feedretain import core
from feedretain.cli import main
from feedretain.core import InputError, audit, compare, parse_feed, parse_policy, read_bounded

ROOT = Path(__file__).resolve().parents[1]


def item(
    guid="synthetic-private-guid",
    title="Private title",
    date="Mon, 19 Oct 2026 10:00:00 +0000",
    url="https://example.invalid/audio.mp3?token=synthetic-secret",
    length="100",
    mime="audio/mpeg",
    permalink="false",
):
    return (
        f"<item><guid isPermaLink={quoteattr(permalink)}>{escape(guid)}</guid>"
        f"<title>{escape(title)}</title><pubDate>{escape(date)}</pubDate>"
        f"<enclosure url={quoteattr(url)} length={quoteattr(length)} type={quoteattr(mime)} />"
        "</item>"
    )


def rss(*items):
    return ('<rss version="2.0"><channel>' + "".join(items) + "</channel></rss>").encode()


def parsed(**kwargs):
    return parse_feed(rss(item(**kwargs)))


def policy_for(before, after, approvals):
    return json.dumps(
        {
            "schema_version": 1,
            "baseline_sha256": before.sha256,
            "candidate_sha256": after.sha256,
            "allow": approvals,
        }
    ).encode()


def test_full_retention_reorder_additions_and_timezone():
    before = parse_feed((ROOT / "examples/baseline.xml").read_bytes())
    after = parse_feed((ROOT / "examples/retained.xml").read_bytes())
    result = compare(before, after)
    assert result["status"] == "passed"
    assert result["retained_episodes"] == 2
    assert result["new_items"] == [1]
    assert result["issues"] == []


def test_churn_hint_is_not_an_identity_match():
    before = parsed()
    after = parsed(guid="new-guid")
    result = compare(before, after)
    assert result["status"] == "failed"
    assert result["issues"] == [
        {"code": "missing_episode", "before_item": 1, "after_item": None, "allowed": False}
    ]
    assert result["hints"] == [{"code": "possible_guid_change", "before_item": 1, "after_item": 1}]
    assert result["retained_episodes"] == 0


def test_ambiguous_enclosure_is_not_guessed():
    before = parse_feed(rss(item(guid="a"), item(guid="b")))
    after = parsed(guid="new")
    assert compare(before, after)["hints"] == []
    before = parsed()
    after = parse_feed(rss(item(guid="x"), item(guid="y")))
    assert compare(before, after)["hints"] == []


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"title": "changed"}, "title_changed"),
        ({"date": "Mon, 19 Oct 2026 11:00:00 +0000"}, "pubdate_changed"),
        ({"url": "https://cdn.example.invalid/audio.mp3"}, "enclosure_url_changed"),
        ({"length": "101"}, "enclosure_length_changed"),
        ({"mime": "audio/ogg"}, "enclosure_type_changed"),
        ({"permalink": "true"}, "guid_permalink_changed"),
    ],
)
def test_every_protected_field_fails_independently(kwargs, code):
    report = compare(parsed(), parsed(**kwargs))
    assert report["status"] == "failed"
    assert [i["code"] for i in report["issues"]] == [code]


def test_mime_case_and_utc_instant_are_semantic():
    report = compare(parsed(), parsed(mime="AUDIO/MPEG", date="Mon, 19 Oct 2026 12:00:00 +0200"))
    assert report["status"] == "passed"


def test_guid_is_exact_and_not_silently_trimmed():
    assert compare(parsed(), parsed(guid=" synthetic-private-guid "))["status"] == "failed"


def test_exact_review_policy_allows_only_one_change():
    before, after = parsed(), parsed(url="https://cdn.example.invalid/new.mp3")
    approval = {
        "code": "enclosure_url_changed",
        "before_item": 1,
        "after_item": 1,
        "reason": "Reviewed CDN move",
    }
    policy = policy_for(before, after, [approval])
    result = compare(before, after, policy=policy)
    assert result["status"] == "passed"
    assert result["issues"][0]["allowed"] is True
    assert result["policy_sha256"] == hashlib.sha256(policy).hexdigest()
    changed_again = parsed(url="https://other.example.invalid/new.mp3")
    with pytest.raises(InputError, match="hash_mismatch"):
        compare(before, changed_again, policy=policy)


def test_explicit_archive_prune_and_unused_approvals():
    before = parse_feed(rss(item(guid="a"), item(guid="b")))
    after = parsed(guid="b")
    approval = {
        "code": "missing_episode",
        "before_item": 1,
        "after_item": None,
        "reason": "Intentional removal reviewed against exact feed files",
    }
    assert (
        compare(before, after, policy=policy_for(before, after, [approval]))["status"] == "passed"
    )
    approval["before_item"] = 2
    with pytest.raises(InputError, match="unused"):
        compare(before, after, policy=policy_for(before, after, [approval]))


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not XML",
        b"<rss>",
        b'<rss version="1.0"><channel/></rss>',
        b'<rss version="2.0"><channel/><channel/></rss>',
        b'<feed xmlns="http://www.w3.org/2005/Atom"/>',
        rss(),
        rss(item(), item()),
        rss(item()).replace(b'isPermaLink="false"', b'isPermaLink="wrong"'),
        rss(item()).replace(b"<guid ", b"<x-guid ").replace(b"</guid>", b"</x-guid>"),
        rss(item()).replace(b"Private title", b"<b>Private</b>"),
        rss(item()).replace(b"<title>", b"<title></title><title>"),
        rss(item()).replace(b"<enclosure", b"<enclosure/><enclosure"),
        rss(item()).replace(b"<enclosure", b"<other").replace(b" />", b" />"),
    ],
)
def test_bad_feeds_fail_closed(data):
    with pytest.raises(InputError):
        parse_feed(data)


@pytest.mark.parametrize(
    "changes",
    [
        {"guid": "x" * 4097},
        {"guid": "   "},
        {"title": ""},
        {"date": "bad"},
        {"date": "Mon, 19 Oct 2026 10:00:00"},
        {"date": "Mon, 19 Oct 2026 10:00:60 +0000"},
        {"url": "file:///private"},
        {"url": "https://user:secret@example.invalid/a"},
        {"url": "http://x:999999/a"},
        {"url": "https://x/a#fragment"},
        {"url": "https://x/a\nb"},
        {"url": "https://x/中文"},
        {"url": "http://x:0"},
        {"url": "http://x\\a"},
        {"length": "-1"},
        {"length": "1.5"},
        {"length": "9999999999999999999"},
        {"mime": "audio"},
    ],
)
def test_bad_episode_fields_are_value_free(changes):
    with pytest.raises(InputError) as error:
        parsed(**changes)
    assert "synthetic-secret" not in str(error.value)
    assert "Private title" not in str(error.value)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_dtd_entities_are_rejected_before_expansion(encoding):
    data = (
        '<?xml version="1.0" encoding="' + encoding + '"?>'
        '<!DOCTYPE rss [<!ENTITY leak SYSTEM "file:///never-read">]>'
        '<rss version="2.0"><channel>&leak;</channel></rss>'
    ).encode(encoding)
    with pytest.raises(InputError, match="dtd_forbidden"):
        parse_feed(data)


def test_structure_size_and_item_limits(monkeypatch):
    with pytest.raises(InputError, match="structure_limit"):
        parse_feed(b"<a>" * 65 + b"</a>" * 65)
    builder = core.LimitedBuilder()
    builder.nodes = 200_000
    with pytest.raises(InputError, match="structure_limit"):
        builder.start("x", {})
    monkeypatch.setattr(core, "MAX_FEED_BYTES", 10)
    with pytest.raises(InputError, match="byte_limit"):
        parsed()
    monkeypatch.setattr(core, "MAX_FEED_BYTES", 8 * 1024 * 1024)
    monkeypatch.setattr(core, "MAX_ITEMS", 1)
    with pytest.raises(InputError, match="episodes"):
        parse_feed(rss(item(guid="a"), item(guid="b")))


@pytest.mark.parametrize(
    "data", [b"", b"{", b"[]", b"{}", b'{"a":1,"a":2}', b"\xff", b"[" * 1100 + b"]" * 1100]
)
def test_invalid_policy_json(data):
    with pytest.raises(InputError):
        parse_policy(data, parsed(), parsed())


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"allow": {}},
        {"allow": [None]},
        {"allow": [{}]},
        {"allow": [{"code": "everything", "before_item": 1, "after_item": 1, "reason": "x"}]},
        {"allow": [{"code": "title_changed", "before_item": True, "after_item": 1, "reason": "x"}]},
        {
            "allow": [
                {"code": "title_changed", "before_item": 1, "after_item": False, "reason": "x"}
            ]
        },
        {"allow": [{"code": "title_changed", "before_item": 1, "after_item": 1, "reason": " "}]},
    ],
)
def test_invalid_policy_structure(mutation):
    before, after = parsed(), parsed(title="new")
    policy = json.loads(policy_for(before, after, []))
    policy.update(mutation)
    with pytest.raises(InputError):
        compare(before, after, policy=json.dumps(policy).encode())


def test_policy_duplicate_entries_and_bounds(monkeypatch):
    before, after = parsed(), parsed(title="new")
    approval = {"code": "title_changed", "before_item": 1, "after_item": 1, "reason": "x"}
    with pytest.raises(InputError, match="duplicate_policy_entry"):
        parse_policy(policy_for(before, after, [approval, approval]), before, after)
    monkeypatch.setattr(core, "MAX_POLICY_BYTES", 10)
    with pytest.raises(InputError, match="policy_byte"):
        parse_policy(b" " * 11, before, after)


def test_no_input_mutation_and_cli_contract(tmp_path, capsys):
    before = tmp_path / "before.xml"
    after = tmp_path / "after.xml"
    before.write_bytes(rss(item()))
    after.write_bytes(rss(item(title="Changed private title")))
    digest = hashlib.sha256(before.read_bytes()).hexdigest()
    assert main([str(before), str(before), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["issues"] == []
    assert main([str(before), str(after)]) == 1
    output = capsys.readouterr().out
    assert "title_changed" in output and "private title" not in output
    assert main([str(before), str(after), "--json"]) == 1
    output = capsys.readouterr().out
    assert "synthetic-secret" not in output and "synthetic-private-guid" not in output
    assert main([str(tmp_path / "missing"), str(after)]) == 2
    assert "baseline" in capsys.readouterr().err
    assert hashlib.sha256(before.read_bytes()).hexdigest() == digest
    policy = tmp_path / "review.json"
    policy.write_bytes(
        policy_for(
            parse_feed(before.read_bytes()),
            parse_feed(after.read_bytes()),
            [
                {
                    "code": "title_changed",
                    "before_item": 1,
                    "after_item": 1,
                    "reason": "Reviewed correction",
                }
            ],
        )
    )
    assert audit(before, after, policy=policy)["status"] == "passed"
    assert main([str(before), str(after), "--policy", str(policy)]) == 0
    assert "ALLOWED" in capsys.readouterr().out


def test_cli_churn_hint(capsys):
    assert main([str(ROOT / "examples/baseline.xml"), str(ROOT / "examples/churned.xml")]) == 1
    assert "not automatically matched" in capsys.readouterr().out


def test_cli_io_error_is_redacted(monkeypatch, capsys):
    import feedretain.cli as cli

    def fail(*args, **kwargs):
        raise OSError("private-filename")

    monkeypatch.setattr(cli, "audit", fail)
    assert main(["old", "new"]) == 2
    assert "private-filename" not in capsys.readouterr().err


def test_bounded_read(tmp_path):
    path = tmp_path / "file"
    path.write_bytes(b"x" * 11)
    with pytest.raises(InputError, match="byte_limit"):
        read_bounded(path, 10)


def test_guid_permalink_default_is_preserved():
    data = rss(item()).replace(b' isPermaLink="false"', b"")
    assert parse_feed(data).episodes[0].guid_permalink is True


def test_checked_in_policy_example():
    result = audit(
        ROOT / "examples/baseline.xml",
        ROOT / "examples/cdn-move.xml",
        policy=ROOT / "examples/allow-cdn-move.json",
    )
    assert result["status"] == "passed"
    assert [i["code"] for i in result["issues"]] == ["enclosure_url_changed"]
