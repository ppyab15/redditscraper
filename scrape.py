#!/usr/bin/env python3
"""Read-only Reddit scraper for personal research, using the official API via PRAW.

Examples:
  python scrape.py topic                      # run all wart searches in topics/warts.json
  python scrape.py search --subreddits Warts,AskDocs --query "duct tape wart" --limit 20
  python scrape.py thread --url https://www.reddit.com/r/AskDocs/comments/abc123/some_title/

Credentials are read from .env next to this file (see .env.example).
Output goes to data/<timestamp>_<mode>/ : posts.jsonl, comments.jsonl, corpus.csv.
"""
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
SEEN_FILE = DATA_DIR / "seen_ids.txt"
REQUIRED_ENV = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]
CSV_FIELDS = ["kind", "subreddit", "post_id", "id", "parent_id", "depth", "title",
              "url", "created_utc", "score", "num_comments", "text", "author"]


def iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def connect():
    try:
        from dotenv import load_dotenv
        import praw
    except ImportError:
        sys.exit("Missing packages. Run: pip install -r requirements.txt")
    load_dotenv(HERE / ".env")
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        sys.exit(f"Missing credentials in {HERE / '.env'}: {', '.join(missing)}\n"
                 "Copy .env.example to .env and fill it in once Reddit approves your app.")
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ["REDDIT_USER_AGENT"],
        ratelimit_seconds=300,
    )
    reddit.read_only = True
    return reddit


def post_record(s, keep_authors):
    author = s.author.name if s.author else None
    text = s.selftext or ""
    if text in ("[deleted]", "[removed]"):
        text = ""
    return {
        "kind": "post", "subreddit": s.subreddit.display_name, "post_id": s.id,
        "id": s.id, "parent_id": "", "depth": 0, "title": s.title,
        "url": f"https://www.reddit.com{s.permalink}", "created_utc": iso(s.created_utc),
        "score": s.score, "num_comments": s.num_comments, "text": text,
        "author": author if keep_authors else "",
    }


def comment_records(s, keep_authors, max_more):
    s.comment_sort = "top"
    s.comments.replace_more(limit=max_more)
    for c in s.comments.list():
        author = c.author.name if c.author else None
        if c.body in ("[deleted]", "[removed]", ""):
            continue
        yield {
            "kind": "comment", "subreddit": s.subreddit.display_name, "post_id": s.id,
            "id": c.id, "parent_id": c.parent_id, "depth": c.depth, "title": "",
            "url": f"https://www.reddit.com{c.permalink}", "created_utc": iso(c.created_utc),
            "score": c.score, "num_comments": "", "text": c.body,
            "author": author if keep_authors else "",
        }


def load_seen():
    return set(SEEN_FILE.read_text().split()) if SEEN_FILE.exists() else set()


def run(submissions, args, label):
    seen = load_seen() if not args.allow_duplicates else set()
    base = DATA_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{label}"
    out, n = base, 1
    while out.exists():
        n += 1
        out = base.with_name(f"{base.name}_{n}")
    out.mkdir(parents=True)
    new_ids, n_posts, n_comments = [], 0, 0
    with open(out / "posts.jsonl", "w") as fp, open(out / "comments.jsonl", "w") as fc, \
            open(out / "corpus.csv", "w", newline="") as fcsv:
        fields = CSV_FIELDS if args.keep_authors else [f for f in CSV_FIELDS if f != "author"]
        writer = csv.DictWriter(fcsv, fieldnames=fields)
        writer.writeheader()

        def emit(rec, fh):
            if not args.keep_authors:
                rec.pop("author", None)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            writer.writerow(rec)
            new_ids.append(rec["id"])

        for s in submissions:
            if s.id in seen:
                print(f"  skip (already saved): {s.title[:70]}")
                continue
            seen.add(s.id)
            emit(post_record(s, args.keep_authors), fp)
            n_posts += 1
            print(f"[{n_posts}] r/{s.subreddit.display_name}: {s.title[:70]}")
            if args.comments:
                for rec in comment_records(s, args.keep_authors, args.max_more):
                    if rec["id"] in seen:
                        continue
                    seen.add(rec["id"])
                    emit(rec, fc)
                    n_comments += 1
            time.sleep(args.delay)
    if new_ids and not args.allow_duplicates:
        with open(SEEN_FILE, "a") as f:
            f.write("\n".join(new_ids) + "\n")
    if not new_ids:
        for f in out.iterdir():
            f.unlink()
        out.rmdir()
        print("\nNothing new to save (everything was already scraped; use --allow-duplicates to re-save).")
        return
    print(f"\nSaved {n_posts} posts and {n_comments} comments to {out}")


def search_submissions(reddit, args):
    subs = "+".join(x.strip() for x in args.subreddits.split(",") if x.strip())
    return reddit.subreddit(subs).search(
        args.query, sort=args.sort, time_filter=args.time, limit=args.limit)


def topic_submissions(reddit, args):
    """Run every query in a topic file (e.g. topics/warts.json) across its subreddits."""
    cfg = json.loads(Path(args.file).read_text())
    subs = "+".join(cfg["subreddits"])
    for q in cfg["queries"]:
        print(f"\n=== query: {q}  (r/{subs})")
        yield from reddit.subreddit(subs).search(
            q, sort=args.sort, time_filter=args.time, limit=args.limit)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--comments", action=argparse.BooleanOptionalAction, default=True,
                        help="also fetch comment trees (default: on)")
    common.add_argument("--max-more", type=int, default=8,
                        help="how many 'load more comments' expansions per thread (0 = none, -1 = all)")
    common.add_argument("--keep-authors", action="store_true", help="store usernames (off by default)")
    common.add_argument("--allow-duplicates", action="store_true",
                        help="ignore data/seen_ids.txt and re-save items already scraped")
    common.add_argument("--delay", type=float, default=1.0, help="seconds to pause between threads")
    sp = p.add_subparsers(dest="mode", required=True)

    s = sp.add_parser("search", parents=[common], help="search one or more subreddits")
    s.add_argument("--subreddits", required=True, help="comma-separated, e.g. Warts,AskDocs ('all' for sitewide)")
    s.add_argument("--query", required=True, help='Reddit search syntax, e.g. "duct tape AND wart"')
    s.add_argument("--sort", default="relevance", choices=["relevance", "new", "top", "hot", "comments"])
    s.add_argument("--time", default="all", choices=["all", "year", "month", "week", "day", "hour"])
    s.add_argument("--limit", type=int, default=25, help="max posts (Reddit caps search around 250-1000)")

    t = sp.add_parser("thread", parents=[common], help="fetch specific thread(s) by URL")
    t.add_argument("--url", required=True, action="append", help="thread URL (repeat for several)")

    tp = sp.add_parser("topic", parents=[common], help="run all searches listed in a topic file")
    tp.add_argument("--file", default=str(HERE / "topics" / "warts.json"), help="topic JSON (default: topics/warts.json)")
    tp.add_argument("--sort", default="relevance", choices=["relevance", "new", "top", "hot", "comments"])
    tp.add_argument("--time", default="all", choices=["all", "year", "month", "week", "day", "hour"])
    tp.add_argument("--limit", type=int, default=50, help="max posts per query")

    args = p.parse_args()
    if args.max_more < 0:
        args.max_more = None
    reddit = connect()
    if args.mode == "search":
        run(search_submissions(reddit, args), args, "search")
    elif args.mode == "topic":
        run(topic_submissions(reddit, args), args, Path(args.file).stem)
    else:
        run((reddit.submission(url=u) for u in args.url), args, "thread")


if __name__ == "__main__":
    main()
