---
name: draft
description: Turn a startup's new blog posts, changelog entries or shipped features into X and LinkedIn post drafts in Postiz or Publer, written in the founder's own voice. Use when the user runs /social-drafts:draft, asks to draft social posts for what's new, or shares a blog URL, a post file, a PR, commits or a feature description. With no source given, it finds the posts that haven't been drafted yet and asks which to use. Only ever creates drafts, never publishes.
allowed-tools:
  - Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/push_drafts.py *)
  - Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/find_new.py)
  - Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/find_new.py *)
---

# Social drafts

Turns the user's startup news (blog posts, product updates, new features) into ready-to-edit drafts for X and LinkedIn, saved in Postiz or Publer. Drafts only: nothing is scheduled or published from this skill. The user reviews and schedules them in their tool.

Scripts are in `${CLAUDE_SKILL_DIR}/scripts/`.

## 0. Load the profile

Run `python3 ${CLAUDE_SKILL_DIR}/scripts/find_new.py --status`.

- If the profile or config doesn't exist, run setup first: follow `${CLAUDE_SKILL_DIR}/../setup/SKILL.md`, then come back here.
- Otherwise read `profile.md` in full. It describes the startup, who is posting and their voice. Where it disagrees with a default in this file, the profile wins.
- Keep the `settings` from the status output in mind: `site`, `platforms`, `utm`, `allow_em_dashes`, `provider`, `feature_repo`.

## 1. Get the source

### No source given: find what's new

This is the normal case (`/social-drafts:draft` on its own, or "draft posts for what's new").

1. Run `python3 ${CLAUDE_SKILL_DIR}/scripts/find_new.py`. It reads the site's sitemap and feeds, compares them with the posts that already have drafts, and prints JSON:
   - `new`: posts with no drafts yet, newest first, with `url`, `title`, `published`
   - `features_since` and `feature_repo`: for checking shipped features in git
   - `last_per_day`: the posts-per-day setting used last time, if any
   - on the first run only: `first_run: true`, `pages_checked`, `dates_found`
2. These are candidates, not decisions: the user picks which ones to post about (see "Ask before writing").
3. If `feature_repo` is set, also look for shipped features:
   `git -C "<feature_repo>" log --since="<features_since>" --no-merges --date=short --pretty=format:'%h %ad %s'`
   Keep only changes a user of the product would notice (a new integration, metric, screen, report, AI ability). Skip refactors, fixes, chores, dependency bumps and internal tooling. Group commits that belong to one feature. If a commit message is too vague to write about, read `git -C "<feature_repo>" show --stat <hash>`. Skip a feature that already has its own post in `new`. Each feature you keep becomes one more candidate.
4. If there's nothing new and no features, say so in one line and stop.
5. First run with `dates_found` of 0: the pages don't expose publish dates, so everything was treated as already posted. Fetch the index page of the main section (for example `<site>/blog`) and use the posts dated in the last two weeks as the candidates.

### A source given

- **A URL** (a blog post, changelog entry, help doc or newsletter post): fetch it and pull out the title, the main argument, concrete numbers or examples, and the canonical URL.
- **A local file** (an MDX or Markdown post in the site's repo): read it. Build the public URL from the frontmatter or slug; ask if it isn't clear.
- **A feature**: a PR, a commit range (`git log`, `git diff`), or a plain description. Work out what changed for the user, not how it was implemented.

If the source is thin (a one-line feature), ask one question first: what problem it solves, or who asked for it.

### Ask before writing

Before writing anything, ask in one AskUserQuestion call. Skip any question the user's message already answered (for example "2 a day", or the URLs themselves), and skip a platform question when `platforms` doesn't include that platform.

1. **Which posts?** (header "Posts", `multiSelect: true`). Only in find-what's-new mode. One option per candidate, newest first: the label is a short version of the title (a few words), the description is the date and the URL path (or "feature from git, <date>"). A question holds at most 4 options, so with more than 4 candidates, first print the full numbered list in the chat, offer the 4 newest as options, and say in the question that the user can pick others by typing their numbers under "Other".
2. **How many X posts per day?** (header "X per day"): options 1, 2, 3, 4. Add "(last time)" to the label matching `last_per_day.x`, if there is one.
3. **How many LinkedIn posts per day?** (header "LinkedIn"): options 1, 2, 3, and "None this time". Add "(last time)" to the label matching `last_per_day.linkedin`.

What the answers mean:

- Write drafts only for the posts the user picked. The others stay in the list for next run. If they say to drop some ("skip the rest"), run `find_new.py --mark-done <url> ... --status-label skipped`.
- Posts per day sets how often drafts land in the calendar, not how many drafts each post gets. Pass the numbers to the push script as `--per-day-x N --per-day-linkedin N`. With "None this time", write no LinkedIn drafts.
- Times per day, in the configured timezone: X 1 = 10:00; 2 = 10:00, 16:00; 3 = 09:00, 13:00, 17:00; 4 = 09:00, 12:00, 15:00, 18:00. LinkedIn 1 = 09:00; 2 = 09:00, 15:00; 3 = 09:00, 13:00, 17:00.
- If there is no way to ask (a scheduled or unattended run), take the 3 newest candidates and the `last_per_day` setting (or 1 per day), and say so at the top of the report.

## 2. Find the angles

For each source, note one line each before writing:

- what it is and who it's for
- the single most interesting insight, number, or before/after
- why the user built or wrote it (the story behind it)
- the link

## 3. Write the drafts

Default set per source:

- **X**: 2 or 3 standalone posts, each a different angle (the insight, the story behind it, a concrete tip or number). For a long how-to post, one of them can be a thread of 3 to 6 parts.
- **LinkedIn**: 1 post.

When several sources go out in one run, use 2 X posts per source instead of 3 so the calendar doesn't fill with one topic. The user can ask for more or fewer; follow that.

Before writing, tell the user in one line how far the drafts will stretch, for example "8 X drafts at 2 a day = 4 days, Sat to Tue".

### Voice

Follow the profile's "Voice", "Never use" and "Example posts I like" sections first. Match the example posts' length, rhythm and openings, but never copy their sentences. When the profile is silent, use these defaults:

- Write as the person in "Who's posting", from the point of view it sets ("I" or "we"). Plain and specific: a founder talking, not a brand.
- Open with the hook: a number, a mistake, a surprising result, or a direct claim.
- Show the product with specifics (a number it computes, a question it answers, a screen, a before/after), not adjectives.
- Never invent facts, numbers, customers or quotes. Use only what the source or the profile says.
- Avoid hype: "excited to announce", "thrilled", "game-changer", "unlock", "supercharge", "revolutionize", "in today's fast-paced world", "let's dive in".
- Emojis sparingly (zero or one), never as bullet points.
- Unless `allow_em_dashes` is true, never use em dashes (—): use a period, comma, colon or parentheses, and don't swap in en dashes either. The push script rejects drafts that contain one.

### X rules

- Each part is at most 280 characters (any URL counts as 23).
- One link per post at most. In a thread, put the link in the last part.
- No hashtags, or one if it's a real community tag.

### LinkedIn rules

- 120 to 220 words. The first line has to work on its own before "see more" (under about 140 characters).
- Short paragraphs of 1 or 2 sentences, a blank line between them.
- Plain text only: LinkedIn doesn't render markdown, so no `**bold**`.
- End with a question or a clear next step. Up to 3 hashtags at the very end, or none.
- Put the link in `first_comment` (Postiz posts it as the first comment). For Publer, the script appends it to the end of the post.

### Links

If `utm` is true, tag links to the user's own site (the domain in `site`) so their analytics attribute the visits:
`?utm_source=x&utm_medium=social&utm_campaign=<post-slug>` (use `utm_source=linkedin` for LinkedIn). Leave links to other sites as they are. For a feature without a page, link to the most relevant page (the feature, integration or help page) or leave the link out.

## 4. Save drafts.json

Write all drafts from this run to one `drafts.json` in the working directory (see `${CLAUDE_SKILL_DIR}/drafts.example.json`). Give every draft a `source`: the post's canonical URL (without UTM tags), or `feature:<short-name>` for a git feature.

```json
{
  "drafts": [
    { "source": "https://example.com/blog/post-slug", "platform": "x", "parts": ["Hook post with the link https://example.com/blog/post-slug?utm_source=x&utm_medium=social&utm_campaign=post-slug"] },
    { "source": "https://example.com/blog/post-slug", "platform": "x", "parts": ["Thread part 1", "Part 2", "Part 3 with the link"] },
    { "source": "https://example.com/blog/post-slug", "platform": "linkedin", "parts": ["The LinkedIn post"], "first_comment": "Full post: https://example.com/blog/post-slug?utm_source=linkedin&utm_medium=social&utm_campaign=post-slug" }
  ]
}
```

A top-level `"source"` works too when every draft has the same one.

Leave `date` out unless the user asks for a specific day (ISO 8601 with offset, for example `2026-10-26T10:00:00+02:00`). Without it, the script fills each platform's daily time slots (from the posts-per-day answer) in the order the drafts appear in the file. It starts tomorrow, or right after the last slot it used in an earlier run, whichever is later, so runs queue up instead of overlapping. Order the drafts so the topics alternate (post A, post B, post A...).

Show the user the full text of each draft in the chat as you push them.

## 5. Push to the scheduler

Use the scheduler the user names ("Postiz" or "Publer"), else the `provider` setting, else ask.

**Always create drafts.** Never use type `schedule` or `now` and never publish, even if asked in passing: scheduling and publishing happen inside Postiz or Publer.

### Postiz

Run the script, with the per-day numbers the user chose:
`python3 ${CLAUDE_SKILL_DIR}/scripts/push_drafts.py --provider postiz --file drafts.json --per-day-x 2 --per-day-linkedin 1`

Needs `POSTIZ_API_KEY` in the environment (Postiz Settings, Developers, Public API). Optional: `POSTIZ_BASE_URL` for a self-hosted instance, `POSTIZ_X_ID` and `POSTIZ_LINKEDIN_ID` to skip the channel lookup. Postiz allows 30 API calls per hour; one run uses 1 lookup plus 1 call per distinct draft time.

If the script can't reach the API from this environment but Postiz MCP tools are available (`integrationList`, `schedulePostTool`), use those instead: list the channels, pick the X and LinkedIn ones, and call `schedulePostTool` with the draft type. Extra values after the first become thread replies on X and comments on LinkedIn, so pass `first_comment` as the second value on LinkedIn. Then record the sources yourself with `find_new.py --mark-done <url> ...`.

### Publer

`python3 ${CLAUDE_SKILL_DIR}/scripts/push_drafts.py --provider publer --file drafts.json --per-day-x 2 --per-day-linkedin 1`

Needs `PUBLER_API_KEY` (scopes: workspaces, accounts, posts) and `PUBLER_WORKSPACE_ID`. Optional: `PUBLER_X_ID` and `PUBLER_LINKEDIN_ID`. Publer's API is only on its Business plan.

Publer's API has no documented way to create X threads, so for Publer write each X draft as a single post. If a draft has several parts anyway, the script joins them into one draft and the user can use "Split into a thread" in Publer's editor.

If a key is missing, tell the user the variable name, where to get the key, and to add it to `~/.zshrc` or `~/.bashrc`. Never ask them to paste an API key into the chat.

### After a push

- The push script records each URL `source` as drafted, so it never comes up again, and remembers the last time slot and the posts-per-day setting per platform.
- If you checked git features this run, run `python3 ${CLAUDE_SKILL_DIR}/scripts/find_new.py --checked` after the push so the next run only looks at newer commits.

### Script options

- `--dry-run` prints the payloads without calling the API or updating the state file. Use it when the user asks for a dry run, and on their first real use.
- `--per-day-x N` (1 to 5) and `--per-day-linkedin N` (1 to 3) set the daily slots. Left out, they default to the last setting used, else 1.
- `--list-accounts` prints the connected channels and their IDs (for Publer without a workspace ID, it prints the workspaces).
- The script refuses to push a draft that has an X part over 280 characters, empty text, or (unless `allow_em_dashes` is true) an em dash. Fix the draft rather than passing `--force`. If the user's X account has Premium long posts, `--allow-long-x` skips the length check.
- `find_new.py --status` shows the profile folder, settings and state. Every setting in `config.json` can be overridden with an environment variable (see `scripts/shared.py`).
- If a request is blocked by the environment (a sandbox network allowlist), say so plainly and suggest running Claude Code on the user's own machine.

## 6. Report back

One line per draft: platform, the first few words, and the draft date and time. Then say where they are (Postiz calendar as drafts, or Publer's Drafts), and how many candidates the user didn't pick are still waiting for a later run, if any.
