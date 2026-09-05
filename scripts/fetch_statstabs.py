#!/usr/bin/env python3
"""
Fetch all of one author's Bluesky posts, keep #statstab entries, and build
data/statstabs.json for the static website.

No Bluesky credentials are required: app.bsky.feed.getAuthorFeed is public.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HANDLE = os.getenv("BSKY_HANDLE", "mzloteanu.bsky.social")
HASHTAG = os.getenv("STATSTAB_HASHTAG", "statstab").lstrip("#")
START_DATE = os.getenv("STATSTAB_START_DATE", "2024-01-01")
OUT = Path(os.getenv("STATSTAB_OUTPUT", "data/statstabs.json"))

API = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
PAGE_LIMIT = 100
UA = "statstab-archive/1.0 (+https://github.com/)"

STATSTAB_RE = re.compile(rf"(?i)(?<!\w)#{re.escape(HASHTAG)}\b")
NUMBER_RE = re.compile(rf"(?i)#{re.escape(HASHTAG)}\s*#?\s*(\d+)\b")
TAG_RE = re.compile(r"(?<!\w)#([\w-]+)", re.UNICODE)
URL_RE = re.compile(r"https?://[^\s<>()]+")


def fetch_json(url: str, retries: int = 3) -> dict:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to fetch Bluesky feed: {last}") from last


def facet_links(record: dict) -> list[str]:
    links: list[str] = []
    for facet in record.get("facets", []) or []:
        for feature in facet.get("features", []) or []:
            if feature.get("$type") == "app.bsky.richtext.facet#link":
                uri = feature.get("uri")
                if uri:
                    links.append(uri)
    return links


def embed_links(embed: dict | None) -> list[str]:
    if not embed:
        return []
    links: list[str] = []
    external = embed.get("external")
    if isinstance(external, dict) and external.get("uri"):
        links.append(external["uri"])

    # Record-with-media and similar nested structures.
    media = embed.get("media")
    if isinstance(media, dict):
        ext = media.get("external")
        if isinstance(ext, dict) and ext.get("uri"):
            links.append(ext["uri"])
    return links


def unique(seq):
    seen = set()
    out = []
    for item in seq:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def parse_title_and_thoughts(text: str) -> tuple[str, str]:
    cleaned = STATSTAB_RE.sub("", text, count=1)
    cleaned = re.sub(r"^\s*#?\s*\d+\s*", "", cleaned, count=1)
    cleaned = cleaned.strip()

    parts = re.split(r"(?i)\bThoughts\s*:\s*", cleaned, maxsplit=1)
    title = parts[0].strip()
    thoughts = parts[1].strip() if len(parts) == 2 else ""

    # Keep heading compact even when a post was formatted across lines.
    title = re.sub(r"\s+", " ", title)
    return title, thoughts


def make_post_url(uri: str, handle: str) -> str:
    # at://did:plc:.../app.bsky.feed.post/<rkey>
    rkey = uri.rstrip("/").split("/")[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def entry_to_record(entry: dict) -> dict | None:
    # Reposts have a reason field; the archive should contain Mircea's own posts.
    if entry.get("reason"):
        return None

    post = entry.get("post") or {}
    author = post.get("author") or {}
    if author.get("handle", "").lower() != HANDLE.lower():
        return None

    record = post.get("record") or {}
    text = record.get("text") or ""
    if not STATSTAB_RE.search(text):
        return None

    created = record.get("createdAt") or post.get("indexedAt")
    if not created:
        return None

    number_m = NUMBER_RE.search(text)
    if not number_m:
        return None
    number = int(number_m.group(1))

    tags = []
    for tag in TAG_RE.findall(text):
        if tag.lower() == HASHTAG.lower() or tag.isdigit():
            continue
        tags.append(tag)

    title, thoughts = parse_title_and_thoughts(text)

    # Pull reliable link targets from Bluesky facets/embeds, then fall back to text.
    links = unique(
        facet_links(record)
        + embed_links(post.get("embed"))
        + URL_RE.findall(text)
    )
    links = [u.rstrip(".,;:!?)]}") for u in links]
    links = [u for u in links if "bsky.app/" not in u]

    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
    uri = post.get("uri") or ""

    return {
        "number": number,
        "title": title,
        "thoughts": thoughts,
        "text": text,
        "created_at": created,
        "year": dt.year,
        "tags": unique(tags),
        "external_links": unique(links),
        "post_url": make_post_url(uri, author.get("handle", HANDLE)),
        "author": {
            "display_name": author.get("displayName") or "Mircea Zloteanu",
            "handle": author.get("handle") or HANDLE,
            "profile_url": f"https://bsky.app/profile/{author.get('handle') or HANDLE}",
        },
        "uri": uri,
    }


def main() -> int:
    cutoff = datetime.fromisoformat(START_DATE).replace(tzinfo=timezone.utc)
    cursor = None
    collected: list[dict] = []
    seen_uris: set[str] = set()
    page = 0

    while True:
        params = {
            "actor": HANDLE,
            "limit": PAGE_LIMIT,
            "filter": "posts_with_replies",
            "includePins": "false",
        }
        if cursor:
            params["cursor"] = cursor

        url = API + "?" + urllib.parse.urlencode(params)
        data = fetch_json(url)
        feed = data.get("feed", [])
        page += 1

        if not feed:
            break

        oldest = None
        for entry in feed:
            post = (entry.get("post") or {})
            record = post.get("record") or {}
            created = record.get("createdAt") or post.get("indexedAt")
            if created:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                oldest = min(oldest, dt) if oldest else dt

            parsed = entry_to_record(entry)
            if parsed and parsed["uri"] not in seen_uris:
                seen_uris.add(parsed["uri"])
                collected.append(parsed)

        print(f"page {page}: {len(feed)} feed items, {len(collected)} #statstab posts total")

        cursor = data.get("cursor")
        if not cursor:
            break

        # #statstab started in 2024; avoid crawling an account's entire history forever.
        if oldest and oldest < cutoff:
            break

        time.sleep(0.12)

    collected.sort(
        key=lambda p: (p["number"] is not None, p["number"] or 0, p["created_at"]),
        reverse=True,
    )

    if not collected:
        raise RuntimeError(
            "No #statstab posts were found. Existing data file was left untouched."
        )

    payload = {
        "source": "bluesky",
        "handle": HANDLE,
        "hashtag": f"#{HASHTAG}",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "count": len(collected),
        "posts": collected,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUT)
    print(f"Wrote {len(collected)} posts to {OUT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
