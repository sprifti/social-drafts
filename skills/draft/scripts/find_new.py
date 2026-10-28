#!/usr/bin/env python3
"""Find posts on your site that don't have social drafts yet.

Reads your sitemap (and optional RSS/Atom feeds), compares it with the URLs
that already have drafts, and prints what's new as JSON. On the very first
run it looks up each page's publish date and treats anything older than
--since-days as already posted, so it doesn't draft your whole archive.

Usage:
  python3 find_new.py                     print new posts as JSON
  python3 find_new.py --status            show setup, settings and state
  python3 find_new.py --probe URL         inspect a site for setup (sitemaps, sections, feeds)
  python3 find_new.py --mark-done URL ... [--status-label skipped]
  python3 find_new.py --checked           git features checked up to now

Settings come from config.json in SOCIAL_DRAFTS_HOME (default
~/.config/social-drafts); see shared.py. Standard library only, Python 3.9+.
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from html import unescape
from urllib.parse import urljoin, urlsplit

import shared
from shared import FetchError, fetch, iso, normalize, now_utc, parse_date

# Re-exported for push_drafts.py
mark_done = shared.mark_done
get_last_slots = shared.get_last_slots
get_per_day = shared.get_per_day
set_last_slots = shared.set_last_slots

EXCLUDED_SEGMENTS = {"authors", "author", "tag", "tags", "category", "categories", "page", "feed", "rss"}
META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.I)
LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.I)
ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')')
DATE_META_KEYS = {"article:published_time", "datepublished", "date", "pubdate", "publish-date", "og:published_time"}
JSONLD_DATE_RE = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
TIME_TAG_RE = re.compile(r'<time\b[^>]*\bdatetime\s*=\s*["\']([^"\']+)["\']', re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


# ---------- parsing ----------

def local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def tag_attrs(tag):
    return {
        m.group(1).lower(): unescape(m.group(3) if m.group(3) is not None else m.group(4))
        for m in ATTR_RE.finditer(tag)
    }


def sitemap_urls(url, depth=0):
    root = ET.fromstring(fetch(url))
    locs = [
        (el.text or "").strip()
        for el in root.iter()
        if local_name(el.tag) == "loc" and (el.text or "").strip()
    ]
    if local_name(root.tag) == "sitemapindex" and depth < 2:
        out = []
        for child in locs:
            try:
                out.extend(sitemap_urls(child, depth + 1))
            except (FetchError, ET.ParseError) as e:
                print(f"warning: skipped {child}: {e}", file=sys.stderr)
        return out
    return locs


def feed_items(url):
    root = ET.fromstring(fetch(url))
    items = []
    for el in root.iter():
        if local_name(el.tag) not in ("item", "entry"):
            continue
        link, title, published = None, None, None
        for child in el:
            name = local_name(child.tag)
            if name == "link":
                link = link or (child.get("href") or (child.text or "")).strip() or None
            elif name == "title":
                title = (child.text or "").strip() or None
            elif name in ("pubdate", "published", "date") or (name == "updated" and not published):
                published = parse_date(child.text)
        if link:
            items.append({"url": link, "title": title, "published": published})
    return items


def section_of(url, sections):
    path = urlsplit(url).path
    for prefix in sections:
        base = prefix.rstrip("/")
        if not path.startswith(base + "/"):
            continue
        rest = [seg for seg in path[len(base):].split("/") if seg]
        if not rest or rest[0].lower() in EXCLUDED_SEGMENTS:
            return None
        return base.strip("/") or "root"
    return None


def page_info(url):
    """Return (published datetime or None, title or None) for one page."""
    try:
        html = fetch(url)
    except FetchError:
        return None, None
    published, title = None, None
    for tag in META_TAG_RE.findall(html):
        attrs = tag_attrs(tag)
        key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
        if key in DATE_META_KEYS and not published:
            published = parse_date(attrs.get("content"))
        if key == "og:title" and not title:
            title = (attrs.get("content") or "").strip() or None
    if not published:
        match = JSONLD_DATE_RE.search(html)
        published = parse_date(match.group(1)) if match else None
    if not published:
        match = TIME_TAG_RE.search(html)
        published = parse_date(match.group(1)) if match else None
    if not title:
        match = TITLE_RE.search(html)
        title = unescape(" ".join(match.group(1).split())) if match else None
    return published, title


# ---------- commands ----------

def find_new(since_days, max_age_days, workers):
    config = shared.load_config()
    sitemaps = shared.setting("sitemaps", config)
    feeds = shared.setting("feeds", config)
    sections = shared.setting("sections", config)
    if not sitemaps and not feeds:
        raise SetupError("No sitemap or feed is set up yet. Run /social-drafts:setup first.")

    state = shared.load_state()
    first_run = not state["seen"]
    candidates = {}
    for sitemap in sitemaps:
        for loc in sitemap_urls(sitemap):
            section = section_of(loc, sections)
            if section:
                candidates.setdefault(normalize(loc), {"url": loc, "section": section, "title": None, "published": None})
    for feed in feeds:
        for item in feed_items(feed):
            candidates[normalize(item["url"])] = {**item, "section": "feed"}

    new = {key: c for key, c in candidates.items() if key not in state["seen"]}
    lookups = [c for c in new.values() if c["published"] is None or c["title"] is None]
    if lookups:
        if len(lookups) > 20:
            print(f"Looking up publish dates for {len(lookups)} pages...", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for c, (published, title) in zip(lookups, pool.map(lambda c: page_info(c["url"]), lookups)):
                c["published"] = c["published"] or published
                c["title"] = c["title"] or title

    now = now_utc()
    cutoff = now - timedelta(days=since_days if first_run else max_age_days)
    fresh, old = [], []
    for key, c in new.items():
        too_old = c["published"] is not None and c["published"] < cutoff
        undated_first_run = first_run and c["published"] is None
        (old if too_old or undated_first_run else fresh).append((key, c))

    if old or first_run:
        stamp = iso(now)
        for key, _ in old:
            state["seen"][key] = {"status": "baseline", "at": stamp}
        if first_run and not state["seen"]:
            state["seen"]["__initialized__"] = {"status": "baseline", "at": stamp}
        shared.save_state(state)

    fresh.sort(key=lambda kc: kc[1]["published"] or now, reverse=True)
    checked_at = parse_date(state.get("checked_at")) or (now - timedelta(days=since_days))
    result = {
        "first_run": first_run,
        "new": [
            {"url": c["url"], "section": c["section"], "title": c["title"], "published": iso(c["published"])}
            for _, c in fresh
        ],
        "treated_as_already_posted": len(old),
        "features_since": iso(checked_at),
        "feature_repo": shared.setting("feature_repo", config),
        "last_per_day": state.get("per_day") or None,
    }
    if first_run:
        result["pages_checked"] = len(new)
        result["dates_found"] = sum(1 for c in new.values() if c["published"] is not None)
    return result


def probe(site, workers):
    """Look at a site the way setup needs: sitemaps, content sections, feeds."""
    if not site.startswith(("http://", "https://")):
        site = "https://" + site
    parts = urlsplit(site)
    base = f"{parts.scheme}://{parts.netloc}"
    result = {"site": base, "sitemaps": [], "sections": [], "feeds": [], "title": None, "description": None}

    sitemaps = []
    try:
        for line in fetch(base + "/robots.txt").splitlines():
            if line.lower().startswith("sitemap:"):
                sitemaps.append(line.split(":", 1)[1].strip())
    except FetchError:
        pass
    if not sitemaps:
        sitemaps = [base + "/sitemap.xml", base + "/sitemap_index.xml"]

    urls = []
    for sitemap in sitemaps:
        try:
            found = sitemap_urls(sitemap)
        except (FetchError, ET.ParseError):
            continue
        if found:
            result["sitemaps"].append(sitemap)
            urls.extend(found)

    counts, examples = Counter(), {}
    for url in urls:
        segments = [s for s in urlsplit(url).path.split("/") if s]
        if len(segments) >= 2 and segments[1].lower() not in EXCLUDED_SEGMENTS:
            prefix = f"/{segments[0]}/"
            counts[prefix] += 1
            examples.setdefault(prefix, []).append(url)
    result["sections"] = [
        {"prefix": prefix, "pages": n, "examples": examples[prefix][:2]}
        for prefix, n in counts.most_common(12)
    ]

    pages = [base + "/"] + [base + s["prefix"].rstrip("/") for s in result["sections"][:3]]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        htmls = list(pool.map(lambda u: safe_fetch(u), pages))
    feeds = []
    for page, html in zip(pages, htmls):
        if not html:
            continue
        for tag in LINK_TAG_RE.findall(html):
            attrs = tag_attrs(tag)
            kind = (attrs.get("type") or "").lower()
            if "alternate" in (attrs.get("rel") or "").lower() and ("rss" in kind or "atom" in kind) and attrs.get("href"):
                href = urljoin(page, attrs["href"])
                if href not in feeds:
                    feeds.append(href)
        if page == base + "/":
            match = TITLE_RE.search(html)
            result["title"] = unescape(" ".join(match.group(1).split())) if match else None
            for tag in META_TAG_RE.findall(html):
                attrs = tag_attrs(tag)
                if (attrs.get("name") or attrs.get("property") or "").lower() in ("description", "og:description"):
                    result["description"] = attrs.get("content")
                    break
    result["feeds"] = feeds
    return result


def safe_fetch(url):
    try:
        return fetch(url)
    except FetchError:
        return None


def status():
    state = shared.load_state()
    counts = Counter(entry.get("status") for key, entry in state["seen"].items() if not key.startswith("__"))
    return {
        "home": shared.home(),
        "profile": {"path": shared.profile_path(), "exists": os.path.exists(shared.profile_path())},
        "config": {"path": shared.config_path(), "exists": os.path.exists(shared.config_path())},
        "settings": shared.all_settings(),
        "state": {
            "path": shared.state_path(),
            "urls_tracked": dict(counts),
            "last_slot": state.get("last_slot"),
            "per_day": state.get("per_day"),
            "features_checked_at": state.get("checked_at"),
        },
    }


class SetupError(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description="List posts on your site that have no social drafts yet.")
    parser.add_argument("--status", action="store_true", help="show setup, settings and state")
    parser.add_argument("--probe", metavar="URL", help="inspect a site for setup")
    parser.add_argument("--mark-done", nargs="+", metavar="URL", help="record URLs as handled")
    parser.add_argument("--status-label", default="drafted", choices=["drafted", "skipped"],
                        help="label used with --mark-done")
    parser.add_argument("--checked", action="store_true", help="record that git features were checked up to now")
    parser.add_argument("--since-days", type=int, default=14, help="first run: how far back counts as new")
    parser.add_argument("--max-age-days", type=int, default=30,
                        help="later runs: newly seen URLs older than this are treated as moved, not new")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    try:
        if args.status:
            output = status()
        elif args.probe:
            output = probe(args.probe, args.workers)
        elif args.mark_done:
            count = shared.mark_done(args.mark_done, args.status_label)
            print(f"Marked {count} URL(s) as {args.status_label}.")
            return 0
        elif args.checked:
            state = shared.load_state()
            state["checked_at"] = iso(now_utc())
            shared.save_state(state)
            print(f"Features checked up to {state['checked_at']}.")
            return 0
        else:
            output = find_new(args.since_days, args.max_age_days, args.workers)
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    except SetupError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    except (FetchError, ET.ParseError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
