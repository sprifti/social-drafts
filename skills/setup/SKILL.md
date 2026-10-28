---
name: setup
description: Set up or update the social-drafts profile, which covers the user's startup, audience, voice, website sitemap and scheduler (Postiz or Publer). Use on first use of social-drafts, when the draft skill finds no profile, or when the user wants to change their voice, site, sections or settings.
allowed-tools:
  - Bash(python3 ${CLAUDE_SKILL_DIR}/../draft/scripts/find_new.py *)
---

# Set up social drafts

Setup writes two files to the profile folder (default `~/.config/social-drafts/`, or `$SOCIAL_DRAFTS_HOME`):

- `profile.md`: the startup, the person posting, and their voice. Every draft follows it.
- `config.json`: the site, the sitemaps and sections to watch, feeds, timezone, scheduler and platforms. The scripts read it.

The scripts are in `${CLAUDE_SKILL_DIR}/../draft/scripts/`. API keys never go in these files; they stay in the user's shell environment.

## 1. Check what exists

Run `python3 ${CLAUDE_SKILL_DIR}/../draft/scripts/find_new.py --status`.

If the profile and config already exist, read both and show a short summary of each (a few lines). Ask what to change, edit only that, and stop.

## 2. Get the website

Ask for the startup's website in one short question, unless the user already gave it.

## 3. Learn from the site before asking anything else

- Run `find_new.py --probe <url>`. It returns the sitemaps it found, the site's sections with page counts (for example `/blog/`: 123), RSS/Atom feeds, and the homepage title and description.
- Fetch the homepage, plus `/pricing` and `/about` if they exist. Note what the product does in one line, who it's for, the main features, the pricing model, and any stage hints (solo founder, team size, customers).
- Read the 2 most recent posts in the main content section for topics and tone.

If the probe can't reach the site from this machine, fetch `<site>/sitemap.xml` with WebFetch instead and work out the sections from it.

## 4. Ask the rest

Ask these in one AskUserQuestion call:

1. **Sections to watch** (header "Sections", `multiSelect: true`): the content sections from the probe (blog, changelog, updates, guides, news and the like; skip pages such as pricing or legal), up to 4, with page counts in the descriptions.
2. **Who's posting** (header "Voice"): "Me, as the founder (I)" or "The company (we)".
3. **Scheduler** (header "Scheduler"): Postiz, Publer, or "Not sure yet".
4. **Platforms** (header "Platforms"): "X and LinkedIn", "X only", or "LinkedIn only".

Then ask in one plain message, saying that every item is optional:

- their name and X handle
- 2 to 5 posts they wrote and liked, pasted as written (the best guide to their voice)
- words, phrases or characters they never want to see, and whether em dashes are fine
- the path to the product's git repository, if they want shipped features drafted from commits

Detect the timezone instead of asking: `readlink /etc/localtime` on macOS, or `cat /etc/timezone` on Linux. Take the part after `zoneinfo/`, for example `Europe/Lisbon`. Show it in the summary so the user can correct it.

## 5. Write the profile

Fill in `${CLAUDE_SKILL_DIR}/profile.template.md`. Use what the site says and the user's own words. Keep it short and factual, and never invent numbers, customers or claims. If the user pasted example posts, derive the voice rules from them (sentence length, use of numbers, humor, emojis, how posts open) and keep the posts in the profile.

Show the full profile and ask "Anything to change?" Apply any edits, then write:

- `profile.md` in the profile folder
- `config.json` in the same folder, shaped like `${CLAUDE_SKILL_DIR}/config.template.json`. Set `sections` from their answer, `sitemaps` and `feeds` from the probe, `provider` as `postiz`, `publer` or `null`, `platforms` from their answer, `allow_em_dashes` from their answer (default `false`), and `feature_repo` as an absolute path or `null`.

Create the folder if it doesn't exist.

## 6. Finish

Tell the user, briefly:

- Which environment variables to add to their shell profile (`~/.zshrc` or `~/.bashrc`):
  - Postiz: `POSTIZ_API_KEY` (Postiz Settings, Developers, Public API)
  - Publer: `PUBLER_API_KEY` (Settings, Access & Login, API Keys, with scopes workspaces, accounts, posts) and `PUBLER_WORKSPACE_ID`. Publer's API needs its Business plan.
- That `/social-drafts:draft` finds new posts and asks which ones to write about. On the first run, posts from the last 14 days count as new.
- That they can edit `profile.md` any time, or run `/social-drafts:setup` again.
