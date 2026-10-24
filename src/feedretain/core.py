"""Local RSS 2.0 podcast identity and archive-retention contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from . import __version__

MAX_FEED_BYTES = 8 * 1024 * 1024
MAX_POLICY_BYTES = 1024 * 1024
MAX_ITEMS = 10_000
MIME = re.compile(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+")
FIELDS = (
    "title",
    "pubdate",
    "enclosure_url",
    "enclosure_length",
    "enclosure_type",
    "guid_permalink",
)
ALLOWED_CODES = {f"{field}_changed" for field in FIELDS} | {"missing_episode"}


class InputError(ValueError):
    """A value-free input diagnostic, safe to display without feed content."""


class LimitedBuilder(ET.TreeBuilder):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.nodes = 0

    def start(self, tag, attrs):
        self.depth += 1
        self.nodes += 1
        if self.depth > 64 or self.nodes > 200_000:
            raise InputError("xml_structure_limit")
        return super().start(tag, attrs)

    def end(self, tag):
        self.depth -= 1
        return super().end(tag)

    def doctype(self, name, pubid, system):
        raise InputError("dtd_forbidden")


@dataclass(frozen=True)
class Episode:
    number: int
    guid: str
    title: str
    pubdate: str
    enclosure_url: str
    enclosure_length: int
    enclosure_type: str
    guid_permalink: bool


@dataclass(frozen=True)
class Feed:
    sha256: str
    episodes: tuple[Episode, ...]


def read_bounded(path: Path, limit: int) -> bytes:
    if not path.is_file():
        raise InputError("input_must_be_a_regular_file")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise InputError("input_byte_limit")
    return data


def _text(item, tag, number):
    elements = item.findall(tag)
    if len(elements) != 1 or len(elements[0]) or not (elements[0].text or "").strip():
        raise InputError(f"item_{number}: expected_one_plain_{tag}")
    return elements[0].text


def parse_feed(data: bytes) -> Feed:
    if not data or len(data) > MAX_FEED_BYTES:
        raise InputError("feed_byte_limit_or_empty")
    try:
        root = ET.fromstring(data, parser=ET.XMLParser(target=LimitedBuilder()))
    except (ET.ParseError, ValueError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("malformed_xml") from None
    channels = root.findall("channel")
    if root.tag != "rss" or root.get("version") != "2.0" or len(channels) != 1:
        raise InputError("expected_rss_2_with_one_channel")
    items = channels[0].findall("item")
    if not 1 <= len(items) <= MAX_ITEMS:
        raise InputError("expected_1_to_10000_episodes")
    episodes = []
    seen = set()
    for number, item in enumerate(items, 1):
        guid = _text(item, "guid", number)
        if len(guid) > 4096:
            raise InputError(f"item_{number}: guid_length_limit")
        if guid in seen:
            raise InputError(f"item_{number}: duplicate_guid")
        seen.add(guid)
        permalink = item.find("guid").get("isPermaLink", "true")
        if permalink not in {"true", "false"}:
            raise InputError(f"item_{number}: invalid_guid_isPermaLink")
        date = _text(item, "pubDate", number).strip()
        try:
            instant = parsedate_to_datetime(date)
            if instant.tzinfo is None:
                raise ValueError
            pubdate = instant.astimezone(UTC).isoformat()
        except (TypeError, ValueError, OverflowError):
            raise InputError(f"item_{number}: invalid_timezone_aware_pubDate") from None
        enclosures = item.findall("enclosure")
        if len(enclosures) != 1 or len(enclosures[0]):
            raise InputError(f"item_{number}: expected_one_enclosure")
        enclosure = enclosures[0]
        url = enclosure.get("url", "")
        try:
            parsed = urlsplit(url)
            if (
                not url.isascii()
                or any(ord(c) <= 32 or ord(c) == 127 for c in url)
                or len(url) > 8192
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or "#" in url
                or "\\" in url
                or parsed.port == 0
            ):
                raise ValueError
            _ = parsed.port
        except ValueError:
            raise InputError(f"item_{number}: invalid_enclosure_url") from None
        length = enclosure.get("length", "")
        mime = enclosure.get("type", "")
        if not re.fullmatch(r"[0-9]{1,19}", length) or int(length) > 2**63 - 1:
            raise InputError(f"item_{number}: invalid_enclosure_length")
        if not MIME.fullmatch(mime):
            raise InputError(f"item_{number}: invalid_enclosure_type")
        episodes.append(
            Episode(
                number,
                guid,
                _text(item, "title", number).strip(),
                pubdate,
                url,
                int(length),
                mime.lower(),
                permalink == "true",
            )
        )
    return Feed(hashlib.sha256(data).hexdigest(), tuple(episodes))


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate_policy_key")
        result[key] = value
    return result


def parse_policy(data: bytes, before: Feed, after: Feed) -> set[tuple]:
    if not data or len(data) > MAX_POLICY_BYTES:
        raise InputError("policy_byte_limit_or_empty")
    try:
        policy = json.loads(data, object_pairs_hook=_unique_keys)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("malformed_policy_json") from None
    keys = {"schema_version", "baseline_sha256", "candidate_sha256", "allow"}
    if not isinstance(policy, dict) or set(policy) != keys:
        raise InputError("unexpected_policy_keys")
    if type(policy["schema_version"]) is not int or policy["schema_version"] != 1:
        raise InputError("unsupported_policy_version")
    if policy["baseline_sha256"] != before.sha256 or policy["candidate_sha256"] != after.sha256:
        raise InputError("policy_input_hash_mismatch")
    allows = policy["allow"]
    if not isinstance(allows, list) or len(allows) > 20_000:
        raise InputError("policy_allow_limit_or_type")
    keys = {"code", "before_item", "after_item", "reason"}
    approved = set()
    for entry in allows:
        if not isinstance(entry, dict) or set(entry) != keys:
            raise InputError("unexpected_policy_entry_keys")
        code, old, new, reason = (entry[k] for k in ("code", "before_item", "after_item", "reason"))
        if (
            not isinstance(code, str)
            or code not in ALLOWED_CODES
            or type(old) is not int
            or old < 1
            or not (new is None or type(new) is int and new >= 1)
            or not isinstance(reason, str)
            or not 1 <= len(reason.strip()) <= 200
        ):
            raise InputError("invalid_policy_entry")
        key = (code, old, new)
        if key in approved:
            raise InputError("duplicate_policy_entry")
        approved.add(key)
    return approved


def compare(before: Feed, after: Feed, *, policy: bytes | None = None) -> dict:
    approved = parse_policy(policy, before, after) if policy is not None else set()
    remaining = set(approved)
    candidate = {episode.guid: episode for episode in after.episodes}
    baseline_guids = {episode.guid for episode in before.episodes}
    new = [episode for episode in after.episodes if episode.guid not in baseline_guids]
    old_urls = Counter(episode.enclosure_url for episode in before.episodes)
    new_urls = Counter(episode.enclosure_url for episode in after.episodes)
    new_by_url = {episode.enclosure_url: episode for episode in new}
    issues, hints = [], []

    def issue(code, old, current):
        key = (code, old.number, current.number if current else None)
        is_allowed = key in approved
        remaining.discard(key)
        issues.append(
            {"code": code, "before_item": key[1], "after_item": key[2], "allowed": is_allowed}
        )

    for old in before.episodes:
        current = candidate.get(old.guid)
        if current is None:
            issue("missing_episode", old, None)
            possible = new_by_url.get(old.enclosure_url)
            if possible and old_urls[old.enclosure_url] == new_urls[old.enclosure_url] == 1:
                hints.append(
                    {
                        "code": "possible_guid_change",
                        "before_item": old.number,
                        "after_item": possible.number,
                    }
                )
        else:
            for field in FIELDS:
                if getattr(old, field) != getattr(current, field):
                    issue(f"{field}_changed", old, current)
    if remaining:
        raise InputError("policy_contains_unused_approval")
    return {
        "schema_version": 1,
        "tool_version": __version__,
        "status": "failed" if any(not issue["allowed"] for issue in issues) else "passed",
        "baseline_sha256": before.sha256,
        "candidate_sha256": after.sha256,
        "baseline_episodes": len(before.episodes),
        "candidate_episodes": len(after.episodes),
        "retained_episodes": len(before.episodes)
        - sum(i["code"] == "missing_episode" for i in issues),
        "new_items": [episode.number for episode in new],
        "issues": issues,
        "hints": hints,
        "policy_sha256": hashlib.sha256(policy).hexdigest() if policy is not None else None,
    }


def audit(baseline: Path, candidate: Path, *, policy: Path | None = None) -> dict:
    feeds = []
    for label, path in (("baseline", baseline), ("candidate", candidate)):
        try:
            feeds.append(parse_feed(read_bounded(path, MAX_FEED_BYTES)))
        except InputError as exc:
            raise InputError(label + ": " + str(exc)) from None
    policy_data = read_bounded(policy, MAX_POLICY_BYTES) if policy else None
    return compare(*feeds, policy=policy_data)
