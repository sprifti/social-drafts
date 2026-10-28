#!/usr/bin/env python3
"""Push X and LinkedIn post drafts to Postiz or Publer.

Drafts only: this script never schedules or publishes anything.
Standard library only, Python 3.9+.

Usage:
  python3 push_drafts.py --provider postiz --file drafts.json [--dry-run]
  python3 push_drafts.py --provider publer --file drafts.json [--dry-run]
  python3 push_drafts.py --provider postiz --list-accounts

Environment (API keys stay in your shell, never in config files):
  Postiz: POSTIZ_API_KEY, optional POSTIZ_BASE_URL, POSTIZ_X_ID, POSTIZ_LINKEDIN_ID,
          POSTIZ_LINKEDIN_TYPE (linkedin or linkedin-page, used with POSTIZ_LINKEDIN_ID)
  Publer: PUBLER_API_KEY, PUBLER_WORKSPACE_ID, optional PUBLER_BASE_URL,
          PUBLER_X_ID, PUBLER_LINKEDIN_ID

Timezone, default provider and the em dash rule come from config.json
(see shared.py). After a real push, each draft's "source" URL is recorded
in the state file (so it isn't drafted again) and the last time slot per
platform is saved, so the next run's default times continue after it.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

try:
    import find_new as tracker  # same folder; keeps the drafted-URL state
    import shared
except ImportError:
    tracker = None
    shared = None

POSTIZ_DEFAULT_BASE = "https://api.postiz.com/public/v1"
PUBLER_DEFAULT_BASE = "https://app.publer.com/api/v1"
USER_AGENT = "social-drafts/1.0"
X_LIMIT = 280
X_URL_LENGTH = 23
URL_RE = re.compile(r"https?://\S+")
EM_DASH = "\u2014"
# Local posting times for each "posts per day" setting.
SLOT_HOURS = {
    "x": {1: [10], 2: [10, 16], 3: [9, 13, 17], 4: [9, 12, 15, 18], 5: [9, 11, 13, 16, 18]},
    "linkedin": {1: [9], 2: [9, 15], 3: [9, 13, 17]},
}
PLATFORM_ALIASES = {"x": "x", "twitter": "x", "linkedin": "linkedin"}


class ApiError(Exception):
    pass


class ConfigError(Exception):
    pass


# ---------- helpers ----------

def env(name, required=True):
    value = os.environ.get(name, "").strip()
    if required and not value:
        raise ConfigError(f"Missing environment variable {name}.")
    return value


def http(method, url, headers, body=None, timeout=30):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:600]
        raise ApiError(f"{method} {url} returned HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise ApiError(
            f"{method} {url} could not connect ({e.reason}). If this is running in a "
            "sandbox, its network may block this host: run it on your own machine instead."
        )


def x_length(text):
    """Approximate X length: every URL counts as 23 characters."""
    return len(URL_RE.sub("x" * X_URL_LENGTH, text))


def config_setting(name, fallback=None):
    if shared is None:
        return fallback
    value = shared.setting(name)
    return fallback if value is None else value


def local_tz():
    name = (config_setting("timezone") or "").strip()
    if name:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name)
        except Exception:
            print(f"warning: unknown timezone {name!r}, using local time", file=sys.stderr)
    return datetime.now().astimezone().tzinfo


def parse_date(value):
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz())
    return dt


def preview(text, n=60):
    flat = " ".join(text.split())
    return flat if len(flat) <= n else flat[: n - 3] + "..."


# ---------- drafts ----------

def load_drafts(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    items = doc.get("drafts") if isinstance(doc, dict) else doc
    default_source = str(doc.get("source") or "").strip() if isinstance(doc, dict) else ""
    if not isinstance(items, list) or not items:
        raise ConfigError("drafts.json needs a non-empty 'drafts' list.")
    drafts = []
    for i, item in enumerate(items, 1):
        platform = PLATFORM_ALIASES.get(str(item.get("platform", "")).lower())
        if not platform:
            raise ConfigError(f"Draft {i}: platform must be 'x' or 'linkedin'.")
        parts = item.get("parts")
        if isinstance(parts, str):
            parts = [parts]
        if not isinstance(parts, list) or not parts:
            raise ConfigError(f"Draft {i}: 'parts' must be a non-empty list of strings.")
        drafts.append({
            "n": i,
            "platform": platform,
            "parts": [str(p).strip() for p in parts],
            "first_comment": str(item.get("first_comment") or "").strip(),
            "date": parse_date(item["date"]) if item.get("date") else None,
            "source": str(item.get("source") or default_source).strip(),
        })
    return drafts


def validate(drafts, allow_long_x):
    errors = []
    block_em_dash = not config_setting("allow_em_dashes", False)
    for d in drafts:
        texts = d["parts"] + ([d["first_comment"]] if d["first_comment"] else [])
        for j, text in enumerate(texts, 1):
            label = f"Draft {d['n']} ({d['platform']}) part {j}"
            if not text:
                errors.append(f"{label} is empty.")
            if block_em_dash and EM_DASH in text:
                errors.append(f"{label} contains an em dash.")
        if d["platform"] == "x" and not allow_long_x:
            for j, text in enumerate(d["parts"], 1):
                length = x_length(text)
                if length > X_LIMIT:
                    errors.append(
                        f"Draft {d['n']} (x) part {j} is {length} characters (limit {X_LIMIT})."
                    )
    return errors


def last_slot_time(value):
    """Stored last slot as a datetime; a bare YYYY-MM-DD means the end of that day."""
    if not value:
        return None
    try:
        if len(value) == 10:
            day = date.fromisoformat(value)
            return datetime(day.year, day.month, day.day, 23, 59, tzinfo=local_tz())
        return parse_date(value)
    except ValueError:
        return None


def assign_dates(drafts, last_slots=None, per_day=None):
    """Fill undated drafts into each platform's daily time slots, in file order,
    starting tomorrow or right after the last slot used in an earlier run."""
    tz = local_tz()
    tomorrow = (datetime.now(tz) + timedelta(days=1)).date()
    for platform in ("x", "linkedin"):
        pending = [d for d in drafts if d["platform"] == platform and d["date"] is None]
        if not pending:
            continue
        hours = SLOT_HOURS[platform][(per_day or {}).get(platform, 1)]
        after = last_slot_time((last_slots or {}).get(platform))
        day = max(tomorrow, after.astimezone(tz).date()) if after else tomorrow
        while pending:
            for hour in hours:
                slot = datetime(day.year, day.month, day.day, hour, 0, tzinfo=tz)
                if pending and not (after and slot <= after):
                    pending.pop(0)["date"] = slot
            day += timedelta(days=1)


def record_run(drafts, per_day):
    """Remember drafted sources, the last slot per platform and the per-day setting."""
    slots = {}
    for d in drafts:
        value = d["date"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if value > slots.get(d["platform"], ""):
            slots[d["platform"]] = value
    try:
        tracker.set_last_slots(slots, per_day)
        marked = tracker.mark_done(sorted({d["source"] for d in drafts if d["source"]}))
        if marked:
            print(f"Marked {marked} source URL(s) as drafted, so they won't come up again.")
    except OSError as e:
        print(f"warning: drafts were created but the state file wasn't updated ({e})", file=sys.stderr)


# ---------- Postiz ----------

def postiz_base():
    return (os.environ.get("POSTIZ_BASE_URL", "").strip() or POSTIZ_DEFAULT_BASE).rstrip("/")


def postiz_headers():
    return {"Authorization": env("POSTIZ_API_KEY")}


def postiz_channels():
    data = http("GET", f"{postiz_base()}/integrations", postiz_headers()) or []
    return [c for c in data if not c.get("disabled")]


def postiz_channel_ids(drafts, dry_run):
    """Return {platform: (integration_id, identifier)} for the platforms in use."""
    needed = {d["platform"] for d in drafts}
    found = {}
    if "x" in needed and env("POSTIZ_X_ID", required=False):
        found["x"] = (env("POSTIZ_X_ID"), "x")
    if "linkedin" in needed and env("POSTIZ_LINKEDIN_ID", required=False):
        kind = env("POSTIZ_LINKEDIN_TYPE", required=False) or "linkedin"
        found["linkedin"] = (env("POSTIZ_LINKEDIN_ID"), kind)
    missing = needed - found.keys()
    if not missing:
        return found
    if dry_run:
        for p in missing:
            found[p] = (f"<{p}-channel-id>", "x" if p == "x" else "linkedin")
        return found
    channels = postiz_channels()
    for p in missing:
        order = ["x"] if p == "x" else ["linkedin", "linkedin-page"]
        match = next(
            (c for ident in order for c in channels if c.get("identifier") == ident), None
        )
        if not match:
            raise ConfigError(f"No connected {p} channel found in Postiz.")
        found[p] = (match["id"], match["identifier"])
    return found


def postiz_settings(identifier):
    if identifier == "x":
        return {"__type": "x", "who_can_reply_post": "everyone"}
    return {"__type": identifier, "post_as_images_carousel": False}


def postiz_payloads(drafts, ids):
    groups = {}
    for d in drafts:
        date_utc = d["date"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        integration_id, identifier = ids[d["platform"]]
        values = d["parts"] + ([d["first_comment"]] if d["first_comment"] else [])
        groups.setdefault(date_utc, []).append({
            "integration": {"id": integration_id},
            "value": [{"content": text, "image": []} for text in values],
            "settings": postiz_settings(identifier),
        })
    return [
        {"type": "draft", "date": date, "shortLink": False, "tags": [], "posts": posts}
        for date, posts in sorted(groups.items())
    ]


def push_postiz(drafts, dry_run):
    ids = postiz_channel_ids(drafts, dry_run)
    payloads = postiz_payloads(drafts, ids)
    for payload in payloads:
        assert payload["type"] == "draft"
        if dry_run:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            continue
        result = http("POST", f"{postiz_base()}/posts", postiz_headers(), payload)
        print(f"Postiz: created {len(payload['posts'])} draft(s) dated {payload['date']}: {json.dumps(result)}")


def list_postiz():
    for c in postiz_channels():
        handle = f" (@{c['profile']})" if c.get("profile") else ""
        print(f"{c.get('identifier', '?'):<16} {c.get('id')}  {c.get('name', '')}{handle}")


# ---------- Publer ----------

def publer_base():
    return (os.environ.get("PUBLER_BASE_URL", "").strip() or PUBLER_DEFAULT_BASE).rstrip("/")


def publer_headers(with_workspace=True):
    headers = {"Authorization": f"Bearer-API {env('PUBLER_API_KEY')}"}
    if with_workspace:
        headers["Publer-Workspace-Id"] = env("PUBLER_WORKSPACE_ID")
    return headers


def publer_accounts():
    data = http("GET", f"{publer_base()}/accounts", publer_headers())
    accounts = data.get("accounts", []) if isinstance(data, dict) else (data or [])
    return accounts


def publer_account_ids(drafts, dry_run):
    needed = {d["platform"] for d in drafts}
    found = {}
    if "x" in needed and env("PUBLER_X_ID", required=False):
        found["x"] = env("PUBLER_X_ID")
    if "linkedin" in needed and env("PUBLER_LINKEDIN_ID", required=False):
        found["linkedin"] = env("PUBLER_LINKEDIN_ID")
    missing = needed - found.keys()
    if not missing:
        return found
    if dry_run:
        for p in missing:
            found[p] = f"<{p}-account-id>"
        return found
    accounts = publer_accounts()
    for p in missing:
        provider = "twitter" if p == "x" else "linkedin"
        candidates = [a for a in accounts if a.get("provider") == provider]
        candidates.sort(key=lambda a: a.get("status") != "active")
        if not candidates:
            raise ConfigError(f"No connected {p} account found in Publer.")
        found[p] = candidates[0]["id"]
    return found


def publer_payload(drafts, ids):
    posts = []
    for d in drafts:
        if d["platform"] == "x":
            if len(d["parts"]) > 1:
                print(
                    f"note: draft {d['n']} has {len(d['parts'])} parts; Publer gets them joined "
                    "into one draft. Use 'Split into a thread' in Publer's editor.",
                    file=sys.stderr,
                )
            network, text = "twitter", "\n\n".join(d["parts"])
        else:
            text = "\n\n".join(d["parts"] + ([d["first_comment"]] if d["first_comment"] else []))
            network = "linkedin"
        posts.append({
            "networks": {network: {"type": "status", "text": text}},
            "accounts": [{"id": ids[d["platform"]], "scheduled_at": d["date"].isoformat(timespec="minutes")}],
        })
    return {"bulk": {"state": "draft", "posts": posts}}


def push_publer(drafts, dry_run):
    ids = publer_account_ids(drafts, dry_run)
    payload = publer_payload(drafts, ids)
    assert payload["bulk"]["state"] == "draft"
    if dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    result = http("POST", f"{publer_base()}/posts/schedule", publer_headers(), payload) or {}
    job_id = result.get("job_id")
    if not job_id:
        raise ApiError(f"Publer returned no job id: {json.dumps(result)}")
    for _ in range(15):
        status = http("GET", f"{publer_base()}/job_status/{job_id}", publer_headers()) or {}
        state = str(status.get("status", "")).lower()
        if state in ("complete", "completed", "failed"):
            failures = (status.get("payload") or {}).get("failures") or []
            if failures:
                print(f"Publer: job {state} with failures: {json.dumps(failures, ensure_ascii=False)}")
                raise ApiError("Some Publer drafts were not created.")
            print(f"Publer: created {len(payload['bulk']['posts'])} draft(s) (job {job_id}).")
            return
        time.sleep(2)
    print(f"Publer: job {job_id} still processing; check Drafts in Publer.")


def list_publer():
    if not env("PUBLER_WORKSPACE_ID", required=False):
        data = http("GET", f"{publer_base()}/workspaces", publer_headers(with_workspace=False)) or []
        print("Workspaces (set PUBLER_WORKSPACE_ID to one of these):")
        for w in data:
            print(f"  {w.get('id')}  {w.get('name', '')}")
        return
    for a in publer_accounts():
        print(f"{a.get('provider', '?'):<10} {a.get('id')}  {a.get('name', '')} [{a.get('status', '')}]")


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser(description="Create X and LinkedIn drafts in Postiz or Publer.")
    parser.add_argument("--provider", choices=["postiz", "publer"],
                        help="default: provider in config.json or DEFAULT_SOCIAL_PROVIDER")
    parser.add_argument("--file", default="drafts.json")
    parser.add_argument("--dry-run", action="store_true", help="print payloads, call nothing")
    parser.add_argument("--list-accounts", action="store_true", help="print connected channels")
    parser.add_argument("--allow-long-x", action="store_true", help="skip the 280-character X check")
    parser.add_argument("--force", action="store_true", help="push even if validation fails")
    parser.add_argument("--per-day-x", type=int, metavar="N",
                        help="X drafts per day, 1 to 5 (default: last used, else 1)")
    parser.add_argument("--per-day-linkedin", type=int, metavar="N",
                        help="LinkedIn drafts per day, 1 to 3 (default: last used, else 1)")
    parser.add_argument("--no-track", action="store_true",
                        help="don't read or update the drafted-URL state file")
    args = parser.parse_args()
    track = tracker is not None and not args.no_track

    try:
        args.provider = args.provider or (config_setting("provider") or "").lower() or None
    except (OSError, ValueError) as e:
        parser.error(f"could not read config.json: {e}")
    if args.provider not in ("postiz", "publer"):
        parser.error("choose --provider postiz or --provider publer (or set provider in config.json)")

    try:
        if args.list_accounts:
            (list_postiz if args.provider == "postiz" else list_publer)()
            return 0

        drafts = load_drafts(args.file)
        errors = validate(drafts, args.allow_long_x)
        if errors:
            print("Fix these before pushing:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            if not args.force:
                return 1
        saved = tracker.get_per_day() if track else {}
        per_day = {
            "x": args.per_day_x or saved.get("x") or 1,
            "linkedin": args.per_day_linkedin or saved.get("linkedin") or 1,
        }
        for platform, n in per_day.items():
            if n not in SLOT_HOURS[platform]:
                raise ConfigError(f"{platform} posts per day must be 1 to {max(SLOT_HOURS[platform])}.")
        assign_dates(drafts, tracker.get_last_slots() if track else None, per_day)

        (push_postiz if args.provider == "postiz" else push_publer)(drafts, args.dry_run)

        print("\nDrafts:" if not args.dry_run else "\nWould create drafts:")
        for d in drafts:
            extra = f" (+{len(d['parts']) - 1} parts)" if len(d["parts"]) > 1 else ""
            print(f"  {d['platform']:<9} {d['date'].strftime('%a %d %b %H:%M')}  {preview(d['parts'][0])}{extra}")
        if track and not args.dry_run:
            record_run(drafts, per_day)
        return 0
    except (ConfigError, ApiError, ValueError, json.JSONDecodeError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
