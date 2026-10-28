"""Shared settings and state for the social-drafts scripts.

Everything lives in one folder, SOCIAL_DRAFTS_HOME (default
~/.config/social-drafts):

  profile.md   who you are, your startup and your voice (read by Claude)
  config.json  site, sitemaps, sections, feeds, timezone, provider (read by scripts)
  state.json   which URLs already have drafts, last draft slots (written by scripts)

Each setting can be overridden by an environment variable.
Standard library only, Python 3.9+.
"""

import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

USER_AGENT = "social-drafts/1.0 (+https://github.com/topics/claude-code-plugin)"

# setting name -> (environment variable, default)
SETTINGS = {
    "site": ("SOCIAL_SITE", None),
    "sitemaps": ("SOCIAL_SITEMAPS", []),
    "sections": ("SOCIAL_SECTIONS", ["/blog/", "/changelog/"]),
    "feeds": ("SOCIAL_FEEDS", []),
    "feature_repo": ("SOCIAL_FEATURE_REPO", None),
    "timezone": ("SOCIAL_TZ", None),
    "provider": ("DEFAULT_SOCIAL_PROVIDER", None),
    "platforms": ("SOCIAL_PLATFORMS", ["x", "linkedin"]),
    "utm": ("SOCIAL_UTM", True),
    "allow_em_dashes": ("SOCIAL_ALLOW_EM_DASHES", False),
}
LIST_SETTINGS = {"sitemaps", "sections", "feeds", "platforms"}
BOOL_SETTINGS = {"utm", "allow_em_dashes"}


class FetchError(Exception):
    pass


# ---------- paths ----------

def home():
    custom = os.environ.get("SOCIAL_DRAFTS_HOME", "").strip()
    return os.path.expanduser(custom or "~/.config/social-drafts")


def config_path():
    return os.path.join(home(), "config.json")


def profile_path():
    return os.path.join(home(), "profile.md")


def state_path():
    custom = os.environ.get("SOCIAL_DRAFTS_STATE", "").strip()
    return os.path.expanduser(custom) if custom else os.path.join(home(), "state.json")


# ---------- config ----------

def load_config():
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}


def setting(name, config=None):
    env_name, default = SETTINGS[name]
    raw = os.environ.get(env_name)
    if raw is not None and raw.strip() != "":
        raw = raw.strip()
        if name in LIST_SETTINGS:
            return [part.strip() for part in raw.split(",") if part.strip()]
        if name in BOOL_SETTINGS:
            return raw.lower() in ("1", "true", "yes", "on")
        return raw
    config = load_config() if config is None else config
    value = config.get(name, default)
    if name in LIST_SETTINGS and isinstance(value, str):
        value = [part.strip() for part in value.split(",") if part.strip()]
    return value


def all_settings():
    config = load_config()
    return {name: setting(name, config) for name in SETTINGS}


# ---------- state ----------

def load_state():
    try:
        with open(state_path(), encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        state = {}
    state.setdefault("version", 1)
    state.setdefault("seen", {})
    state.setdefault("checked_at", None)
    state.setdefault("last_slot", {})
    return state


def write_json(path, data):
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def save_state(state):
    write_json(state_path(), state)


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def normalize(url):
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def mark_done(urls, status="drafted"):
    """Record URLs as handled so they are never reported as new again."""
    keys = {normalize(u) for u in urls if isinstance(u, str) and u.startswith(("http://", "https://"))}
    if not keys:
        return 0
    state = load_state()
    stamp = iso(now_utc())
    for key in keys:
        state["seen"][key] = {"status": status, "at": stamp}
    save_state(state)
    return len(keys)


def get_last_slots():
    return dict(load_state().get("last_slot") or {})


def get_per_day():
    return dict(load_state().get("per_day") or {})


def set_last_slots(slots, per_day=None):
    """slots: {platform: UTC ISO time of the last draft}. Keeps the later of
    old and new, and stores the posts-per-day setting that was used."""
    state = load_state()
    current = state.setdefault("last_slot", {})
    for platform, value in slots.items():
        old = current.get(platform)
        old_cmp = old + "T23:59:59Z" if old and len(old) == 10 else old
        if not old_cmp or value > old_cmp:
            current[platform] = value
    if per_day:
        state["per_day"] = dict(per_day)
    save_state(state)


# ---------- fetching and dates ----------

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise FetchError(f"{url} returned HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise FetchError(f"could not fetch {url} ({reason})")


def parse_date(value):
    """Parse ISO 8601, RFC 822 (RSS) or a leading YYYY-MM-DD into UTC."""
    if not value:
        return None
    value = value.strip()
    try:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            import email.utils
            dt = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            match = re.match(r"(\d{4}-\d{2}-\d{2})", value)
            if not match:
                return None
            dt = datetime.fromisoformat(match.group(1))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
