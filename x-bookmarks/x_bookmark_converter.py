"""X.com Bookmarks to Obsidian converter.

Imports JSON exports from the twitter-web-exporter Chrome extension
and creates Obsidian notes with standardized frontmatter.

Usage:
    python x_bookmark_converter.py import bookmarks.json
    python x_bookmark_converter.py stats
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path
from typing import Optional

# ── Shared utilities ────────────────────────────────────────
sys.path.insert(0, r"C:\Users\thisi\.claude\skills")

from shared.frontmatter_utils import (
    build_frontmatter,
    is_already_ingested,
    record_ingestion,
    safe_filename,
    VAULT_DIR,
    get_db,
)
from shared.ticker_detector import detect_ticker_symbols

# ── Constants ───────────────────────────────────────────────

OUTPUT_DIR = VAULT_DIR / "X Bookmarks"
SOURCE_PLATFORM = "x"
NOTE_TYPE = "x"

# Twitter date format: "Wed Oct 10 20:19:24 +0000 2025"
TWITTER_DATE_FORMAT = "%a %b %d %H:%M:%S %z %Y"


# ── Parsing ─────────────────────────────────────────────────


def _parse_twitter_date(date_str: str) -> Optional[datetime]:
    """Parse Twitter's date format into a datetime object.

    Handles multiple formats since twitter-web-exporter may vary.
    """
    if not date_str:
        return None

    # Try standard Twitter API format
    for fmt in [
        TWITTER_DATE_FORMAT,
        "%Y-%m-%dT%H:%M:%S.%fZ",  # ISO 8601
        "%Y-%m-%dT%H:%M:%SZ",  # ISO 8601 without ms
        "%Y-%m-%d %H:%M:%S",  # Simple datetime
        "%Y-%m-%d",  # Date only
    ]:
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _extract_tweet(raw: dict) -> Optional[dict]:
    """Normalize a raw tweet object into a standard dict.

    Handles multiple JSON structures from twitter-web-exporter:
    - Direct tweet object (standard Twitter API shape)
    - Nested under 'tweet' or 'data' keys
    - Legacy fields vs modern fields
    """
    # Unwrap nested structures
    if "tweet" in raw and isinstance(raw["tweet"], dict):
        tweet_data = raw["tweet"]
    elif "data" in raw and isinstance(raw["data"], dict):
        tweet_data = raw["data"]
    elif "legacy" in raw and isinstance(raw["legacy"], dict):
        # GraphQL API shape: core.user_results + legacy
        tweet_data = raw["legacy"]
    else:
        tweet_data = raw

    # Extract tweet ID
    tweet_id = str(
        tweet_data.get("id_str")
        or tweet_data.get("id")
        or raw.get("id_str")
        or raw.get("id")
        or raw.get("rest_id")
        or ""
    )
    if not tweet_id:
        return None

    # Extract text content
    full_text = (
        tweet_data.get("full_text")
        or tweet_data.get("text")
        or raw.get("full_text")
        or raw.get("text")
        or ""
    )

    # Extract user info — multiple possible structures
    user = (
        tweet_data.get("user")
        or raw.get("user")
        or raw.get("core", {}).get("user_results", {}).get("result", {}).get("legacy")
        or {}
    )
    screen_name = user.get("screen_name") or user.get("username") or ""
    display_name = user.get("name") or user.get("display_name") or screen_name

    # Extract date
    created_at_str = tweet_data.get("created_at") or raw.get("created_at") or ""
    created_at = _parse_twitter_date(created_at_str)

    # Extract entities (URLs, media)
    entities = tweet_data.get("entities") or raw.get("entities") or {}
    extended_entities = (
        tweet_data.get("extended_entities") or raw.get("extended_entities") or {}
    )

    # Extract URLs from entities
    urls = []
    for url_entity in entities.get("urls", []):
        expanded = url_entity.get("expanded_url") or url_entity.get("url") or ""
        if expanded:
            urls.append(expanded)

    # Extract media
    media_list = extended_entities.get("media") or entities.get("media") or []
    media_urls = []
    for m in media_list:
        media_url = m.get("media_url_https") or m.get("media_url") or ""
        media_type = m.get("type", "photo")
        if media_url:
            media_urls.append({"url": media_url, "type": media_type})
        # Video variants
        video_info = m.get("video_info", {})
        for variant in video_info.get("variants", []):
            if variant.get("content_type") == "video/mp4":
                media_urls.append({"url": variant["url"], "type": "video"})
                break  # Take best quality (usually first mp4)

    # Extract engagement counts
    favorite_count = tweet_data.get("favorite_count") or raw.get("favorite_count") or 0
    retweet_count = tweet_data.get("retweet_count") or raw.get("retweet_count") or 0

    # Reply chain info
    in_reply_to_status_id = str(
        tweet_data.get("in_reply_to_status_id_str")
        or tweet_data.get("in_reply_to_status_id")
        or raw.get("in_reply_to_status_id_str")
        or raw.get("in_reply_to_status_id")
        or ""
    )
    in_reply_to_user = (
        tweet_data.get("in_reply_to_screen_name")
        or raw.get("in_reply_to_screen_name")
        or ""
    )

    # Quoted tweet
    quoted_status = tweet_data.get("quoted_status") or raw.get("quoted_status")
    quoted_tweet = None
    if quoted_status and isinstance(quoted_status, dict):
        quoted_tweet = _extract_tweet(quoted_status)

    return {
        "id": tweet_id,
        "full_text": full_text,
        "screen_name": screen_name,
        "display_name": display_name,
        "created_at": created_at,
        "urls": urls,
        "media": media_urls,
        "favorite_count": int(favorite_count) if favorite_count else 0,
        "retweet_count": int(retweet_count) if retweet_count else 0,
        "in_reply_to_status_id": in_reply_to_status_id,
        "in_reply_to_user": in_reply_to_user,
        "quoted_tweet": quoted_tweet,
    }


def parse_export(json_path: Path) -> list[dict]:
    """Parse a twitter-web-exporter JSON file into normalized tweet dicts.

    Handles:
    - Array of tweets at top level
    - Object with a 'data', 'tweets', or 'bookmarks' key containing array
    - Newline-delimited JSON (one tweet per line)
    """
    json_path = Path(json_path)
    if not json_path.exists():
        print(f"ERROR: File not found: {json_path}")
        return []

    content = json_path.read_text(encoding="utf-8")
    raw_items = []

    # Try standard JSON first
    try:
        data = json.loads(content)
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            # Try common wrapper keys
            for key in ["data", "tweets", "bookmarks", "results", "items"]:
                if key in data and isinstance(data[key], list):
                    raw_items = data[key]
                    break
            if not raw_items:
                # Maybe it's a single tweet
                raw_items = [data]
    except json.JSONDecodeError:
        # Try newline-delimited JSON
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                raw_items.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not raw_items:
        print(f"ERROR: Could not parse any tweets from {json_path}")
        return []

    tweets = []
    for raw in raw_items:
        tweet = _extract_tweet(raw)
        if tweet:
            tweets.append(tweet)

    print(f"Parsed {len(tweets)} tweets from {json_path.name}")
    return tweets


# ── Thread Detection ────────────────────────────────────────


def detect_threads(tweets: list[dict]) -> list[list[dict]]:
    """Group tweets into threads.

    A thread is defined as multiple tweets from the same author where each
    tweet is a reply to the previous one. Standalone tweets become
    single-item lists.

    Returns:
        List of lists. Each inner list is a thread (1+ tweets),
        sorted chronologically (oldest first within thread).
    """
    # Build lookup by tweet ID
    tweet_map = {t["id"]: t for t in tweets}

    # Build reply chains: child_id -> parent_id
    # Only consider self-replies (same author replying to themselves) as threads
    visited = set()
    threads = []

    # Find thread roots: tweets that are not in-reply-to another tweet in our set
    # by the same author
    def _get_chain(tweet_id: str) -> list[dict]:
        """Walk up the reply chain to find the root, then collect all descendants."""
        chain_ids = []
        current_id = tweet_id
        while current_id in tweet_map:
            if current_id in visited:
                break
            chain_ids.append(current_id)
            visited.add(current_id)
            parent_id = tweet_map[current_id].get("in_reply_to_status_id", "")
            # Only follow if parent is same author and exists in our set
            if (
                parent_id
                and parent_id in tweet_map
                and tweet_map[parent_id]["screen_name"]
                == tweet_map[current_id]["screen_name"]
            ):
                current_id = parent_id
            else:
                break
        return chain_ids

    # Build a forward map: parent_id -> [child_ids] (same author only)
    children_map: dict[str, list[str]] = defaultdict(list)
    for t in tweets:
        parent_id = t.get("in_reply_to_status_id", "")
        if (
            parent_id
            and parent_id in tweet_map
            and tweet_map[parent_id]["screen_name"] == t["screen_name"]
        ):
            children_map[parent_id].append(t["id"])

    # Find root tweets (not a self-reply to another tweet in our set)
    roots = []
    for t in tweets:
        parent_id = t.get("in_reply_to_status_id", "")
        is_self_reply_to_known = (
            parent_id
            and parent_id in tweet_map
            and tweet_map[parent_id]["screen_name"] == t["screen_name"]
        )
        if not is_self_reply_to_known:
            roots.append(t["id"])

    # BFS from each root to collect full thread
    for root_id in roots:
        if root_id in visited:
            continue
        thread_ids = []
        queue = [root_id]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            if current not in tweet_map:
                continue
            visited.add(current)
            thread_ids.append(current)
            for child_id in children_map.get(current, []):
                queue.append(child_id)

        if thread_ids:
            thread_tweets = [tweet_map[tid] for tid in thread_ids]
            # Sort chronologically (oldest first)
            thread_tweets.sort(
                key=lambda t: (
                    t["created_at"] or datetime.min.replace(tzinfo=None)
                    if t["created_at"] and t["created_at"].tzinfo is None
                    else t["created_at"].replace(tzinfo=None)
                    if t["created_at"]
                    else datetime.min
                )
            )
            threads.append(thread_tweets)

    # Pick up any orphan tweets not visited
    for t in tweets:
        if t["id"] not in visited:
            threads.append([t])

    return threads


# ── Markdown Formatting ─────────────────────────────────────


def _tweet_url(screen_name: str, tweet_id: str) -> str:
    """Build the X.com URL for a tweet."""
    if screen_name and tweet_id:
        return f"https://x.com/{screen_name}/status/{tweet_id}"
    return ""


def _clean_text(text: str) -> str:
    """Clean tweet text for markdown output.

    - Remove t.co URLs that are just shortened versions of expanded URLs
    - Preserve line breaks
    """
    # Remove trailing t.co URLs (they are replaced by expanded URLs in entities)
    text = re.sub(r"\s*https://t\.co/\w+\s*$", "", text)
    # Remove inline t.co URLs
    text = re.sub(r"https://t\.co/\w+", "", text)
    return text.strip()


def format_tweet_markdown(tweet: dict) -> str:
    """Format a single tweet as markdown content (without frontmatter).

    Returns markdown string for the tweet body.
    """
    lines = []

    # Author line
    display = tweet.get("display_name", "")
    handle = tweet.get("screen_name", "")
    url = _tweet_url(handle, tweet["id"])
    date_str = ""
    if tweet.get("created_at"):
        date_str = tweet["created_at"].strftime("%Y-%m-%d %H:%M")

    lines.append(f"**{display}** ([@{handle}]({url})) - {date_str}")
    lines.append("")

    # Tweet text
    text = _clean_text(tweet.get("full_text", ""))
    if text:
        lines.append(text)
        lines.append("")

    # Expanded URLs
    for expanded_url in tweet.get("urls", []):
        # Skip x.com/twitter.com URLs (self-references)
        if "x.com" in expanded_url or "twitter.com" in expanded_url:
            continue
        lines.append(f"- [{expanded_url}]({expanded_url})")
    if tweet.get("urls"):
        lines.append("")

    # Media
    for media in tweet.get("media", []):
        media_url = media.get("url", "")
        media_type = media.get("type", "photo")
        if media_type == "video":
            lines.append(f"[Video]({media_url})")
        else:
            lines.append(f"![image]({media_url})")
    if tweet.get("media"):
        lines.append("")

    # Quoted tweet
    if tweet.get("quoted_tweet"):
        qt = tweet["quoted_tweet"]
        qt_handle = qt.get("screen_name", "")
        qt_display = qt.get("display_name", "")
        qt_url = _tweet_url(qt_handle, qt["id"])
        qt_text = _clean_text(qt.get("full_text", ""))
        lines.append(f"> **{qt_display}** ([@{qt_handle}]({qt_url})):")
        for qt_line in qt_text.split("\n"):
            lines.append(f"> {qt_line}")
        lines.append("")

    # Engagement
    fav = tweet.get("favorite_count", 0)
    rt = tweet.get("retweet_count", 0)
    if fav or rt:
        lines.append(f"*Likes: {fav} | Retweets: {rt}*")
        lines.append("")

    return "\n".join(lines)


def format_thread_markdown(thread: list[dict]) -> str:
    """Format a thread (multiple tweets) as merged markdown content.

    Tweets are shown in chronological order with separators.
    """
    lines = []
    for i, tweet in enumerate(thread):
        if i > 0:
            lines.append("---")
            lines.append("")
        lines.append(format_tweet_markdown(tweet))

    return "\n".join(lines)


# ── Save to Obsidian ────────────────────────────────────────


def save_to_obsidian(item: dict | list[dict]) -> Optional[Path]:
    """Save a tweet or thread to Obsidian as a markdown note.

    Args:
        item: A single tweet dict, or a list of tweet dicts (thread).

    Returns:
        Path to the saved file, or None if skipped (duplicate).
    """
    # Normalize to thread (list of tweets)
    if isinstance(item, dict):
        thread = [item]
    else:
        thread = item

    if not thread:
        return None

    # Use the first tweet as the primary tweet for metadata
    primary = thread[0]
    tweet_id = primary["id"]
    is_thread = len(thread) > 1

    # Dedup check — use the first tweet's ID as the stable identifier
    if is_already_ingested(SOURCE_PLATFORM, tweet_id):
        return None

    # Also check all tweet IDs in the thread
    for t in thread[1:]:
        if is_already_ingested(SOURCE_PLATFORM, t["id"]):
            # Part of this thread was already imported — skip
            return None

    # Collect all text for ticker detection
    all_text = " ".join(t.get("full_text", "") for t in thread)
    tickers = detect_ticker_symbols(all_text)

    # Build frontmatter
    published_date = primary.get("created_at")
    pub_date = published_date.date() if published_date else None
    screen_name = primary.get("screen_name", "unknown")
    source_url = _tweet_url(screen_name, tweet_id)

    # Aggregate engagement for threads
    total_fav = sum(t.get("favorite_count", 0) for t in thread)
    total_rt = sum(t.get("retweet_count", 0) for t in thread)

    frontmatter = build_frontmatter(
        id=f"x_{tweet_id}",
        type=NOTE_TYPE,
        source_platform=SOURCE_PLATFORM,
        author=screen_name,
        source_url=source_url,
        published_at=pub_date,
        tickers=tickers,
        tags=["x-bookmark"],
        extra={
            "favorite_count": total_fav,
            "retweet_count": total_rt,
            "is_thread": is_thread,
            "tweet_count": len(thread),
        },
    )

    # Build markdown body
    if is_thread:
        body = format_thread_markdown(thread)
    else:
        body = format_tweet_markdown(primary)

    full_content = frontmatter + "\n\n" + body

    # Build filename: YYYY-MM-DD - {author} - {first_20_chars}.md
    date_prefix = pub_date.isoformat() if pub_date else date.today().isoformat()
    text_preview = _clean_text(primary.get("full_text", ""))[:20].strip()
    if not text_preview:
        text_preview = f"tweet-{tweet_id[:8]}"
    filename = safe_filename(f"{date_prefix} - {screen_name} - {text_preview}") + ".md"

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Write file
    out_path = OUTPUT_DIR / filename

    # Handle filename collisions
    counter = 1
    while out_path.exists():
        base = safe_filename(
            f"{date_prefix} - {screen_name} - {text_preview} ({counter})"
        )
        out_path = OUTPUT_DIR / (base + ".md")
        counter += 1

    out_path.write_text(full_content, encoding="utf-8")

    # Record ingestion for all tweets in the thread
    for t in thread:
        record_ingestion(
            source_platform=SOURCE_PLATFORM,
            stable_id=t["id"],
            obsidian_path=str(out_path.relative_to(VAULT_DIR)),
            metadata=json.dumps({"screen_name": t["screen_name"]}, ensure_ascii=False),
        )

    return out_path


# ── Main Entry Points ───────────────────────────────────────


def import_bookmarks(json_path: Path) -> dict:
    """Import bookmarks from a twitter-web-exporter JSON file.

    Returns:
        Stats dict with keys: total_parsed, threads_detected, saved, skipped_dup, errors
    """
    json_path = Path(json_path)
    stats = {
        "total_parsed": 0,
        "threads_detected": 0,
        "single_tweets": 0,
        "saved": 0,
        "skipped_dup": 0,
        "errors": 0,
        "tickers_found": set(),
        "authors": set(),
        "saved_paths": [],
    }

    # Parse
    tweets = parse_export(json_path)
    stats["total_parsed"] = len(tweets)

    if not tweets:
        print("No tweets found to import.")
        return stats

    # Detect threads
    print("Detecting threads...")
    threads = detect_threads(tweets)
    multi_tweet_threads = [t for t in threads if len(t) > 1]
    stats["threads_detected"] = len(multi_tweet_threads)
    stats["single_tweets"] = len(threads) - len(multi_tweet_threads)
    print(
        f"Found {len(multi_tweet_threads)} threads and {stats['single_tweets']} standalone tweets"
    )

    # Save each thread/tweet
    for i, thread in enumerate(threads):
        primary = thread[0]
        screen_name = primary.get("screen_name", "?")
        preview = _clean_text(primary.get("full_text", ""))[:40]

        try:
            path = save_to_obsidian(thread)
            if path:
                stats["saved"] += 1
                stats["saved_paths"].append(str(path))
                stats["authors"].add(screen_name)
                # Collect tickers
                all_text = " ".join(t.get("full_text", "") for t in thread)
                tickers = detect_ticker_symbols(all_text)
                stats["tickers_found"].update(tickers)
                thread_label = (
                    f" (thread: {len(thread)} tweets)" if len(thread) > 1 else ""
                )
                print(
                    f"  [{i + 1}/{len(threads)}] Saved: @{screen_name} - {preview}...{thread_label}"
                )
            else:
                stats["skipped_dup"] += 1
                print(
                    f"  [{i + 1}/{len(threads)}] Skipped (duplicate): @{screen_name} - {preview}..."
                )
        except Exception as e:
            stats["errors"] += 1
            print(f"  [{i + 1}/{len(threads)}] ERROR: @{screen_name} - {e}")

    # Convert sets to lists for JSON serialization
    stats["tickers_found"] = sorted(stats["tickers_found"])
    stats["authors"] = sorted(stats["authors"])

    # Print summary
    print("\n" + "=" * 60)
    print("IMPORT SUMMARY")
    print("=" * 60)
    print(f"  Total tweets parsed:   {stats['total_parsed']}")
    print(f"  Threads detected:      {stats['threads_detected']}")
    print(f"  Standalone tweets:     {stats['single_tweets']}")
    print(f"  Notes saved:           {stats['saved']}")
    print(f"  Skipped (duplicates):  {stats['skipped_dup']}")
    print(f"  Errors:                {stats['errors']}")
    if stats["authors"]:
        print(f"  Authors:               {', '.join(stats['authors'][:10])}")
        if len(stats["authors"]) > 10:
            print(f"                         ... and {len(stats['authors']) - 10} more")
    if stats["tickers_found"]:
        print(f"  Tickers found:         {', '.join(stats['tickers_found'][:20])}")
    print(f"  Output directory:      {OUTPUT_DIR}")
    print("=" * 60)

    return stats


def show_stats() -> dict:
    """Show import statistics from the ingestion_state.db.

    Returns:
        Stats dict with total count, by-author breakdown, date range.
    """
    conn = get_db()
    try:
        # Total imported
        total = conn.execute(
            "SELECT COUNT(*) FROM ingestion_state WHERE source_platform = ?",
            (SOURCE_PLATFORM,),
        ).fetchone()[0]

        # By author (from metadata JSON)
        rows = conn.execute(
            "SELECT metadata FROM ingestion_state WHERE source_platform = ?",
            (SOURCE_PLATFORM,),
        ).fetchall()

        author_counts: dict[str, int] = defaultdict(int)
        for (metadata_str,) in rows:
            if metadata_str:
                try:
                    meta = json.loads(metadata_str)
                    author = meta.get("screen_name", "unknown")
                    author_counts[author] += 1
                except json.JSONDecodeError:
                    author_counts["unknown"] += 1

        # Date range
        date_range = conn.execute(
            "SELECT MIN(ingested_at), MAX(ingested_at) FROM ingestion_state WHERE source_platform = ?",
            (SOURCE_PLATFORM,),
        ).fetchone()

        # Count notes on disk
        notes_on_disk = 0
        if OUTPUT_DIR.exists():
            notes_on_disk = len(list(OUTPUT_DIR.glob("*.md")))

        stats = {
            "total_ingested": total,
            "notes_on_disk": notes_on_disk,
            "authors": dict(sorted(author_counts.items(), key=lambda x: -x[1])),
            "earliest_import": date_range[0] if date_range else None,
            "latest_import": date_range[1] if date_range else None,
            "output_dir": str(OUTPUT_DIR),
        }

        # Print report
        print("\n" + "=" * 60)
        print("X BOOKMARKS IMPORT STATISTICS")
        print("=" * 60)
        print(f"  Total tweets ingested: {total}")
        print(f"  Notes on disk:         {notes_on_disk}")
        if date_range and date_range[0]:
            print(f"  First import:          {date_range[0]}")
            print(f"  Latest import:         {date_range[1]}")
        print(f"  Output directory:      {OUTPUT_DIR}")

        if author_counts:
            print("\n  Top authors:")
            for author, count in sorted(author_counts.items(), key=lambda x: -x[1])[
                :15
            ]:
                print(f"    @{author}: {count} tweets")
            if len(author_counts) > 15:
                print(f"    ... and {len(author_counts) - 15} more authors")

        print("=" * 60)
        return stats

    finally:
        conn.close()


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="X.com Bookmarks to Obsidian converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python x_bookmark_converter.py import bookmarks.json
  python x_bookmark_converter.py stats
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # import subcommand
    import_parser = subparsers.add_parser(
        "import", help="Import bookmarks from JSON file"
    )
    import_parser.add_argument(
        "json_file", type=str, help="Path to the exported JSON file"
    )

    # stats subcommand
    subparsers.add_parser("stats", help="Show import statistics")

    args = parser.parse_args()

    if args.command == "import":
        json_path = Path(args.json_file)
        if not json_path.is_absolute():
            json_path = Path.cwd() / json_path
        result = import_bookmarks(json_path)
        sys.exit(0 if result["errors"] == 0 else 1)
    elif args.command == "stats":
        show_stats()
    else:
        parser.print_help()
        sys.exit(1)
