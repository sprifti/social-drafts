# Social Drafts

A Claude Code plugin for founders who ship more than they post.

It finds the blog posts, changelog entries and features you've published since last time, asks which ones you want to talk about, and writes X and LinkedIn posts about them in your own voice. The posts land as **drafts** in [Postiz](https://postiz.com) or [Publer](https://publer.com), spread across the days ahead. You review, tweak and schedule them there. Nothing is ever published for you.

```
> /social-drafts:draft

  Found 3 new posts since Oct 16 and 1 feature from git.

  ? Which posts?            [x] Pricing page teardown   [x] Stripe Tax support (feature)
  ? How many X posts/day?   2 (last time)
  ? LinkedIn posts/day?     1

  4 X drafts at 2 a day = 2 days, Sat to Sun. Writing...

  x         Sat 24 Oct 10:00  I rewrote our pricing page 4 times this year...
  x         Sat 24 Oct 16:00  Stripe Tax is live. If you sell to the EU...
  linkedin  Sat 24 Oct 09:00  The pricing page is the most-read page on...
  ...
  6 drafts are in your Postiz calendar.
```

## What it does

- **Learns your startup once.** Setup reads your website, asks a few questions, and saves a short profile: what you build, who it's for, how you write, words you never use, and a few posts you liked. Every draft follows it.
- **Finds what's new.** It watches your sitemap (and RSS feeds, like a Substack) and remembers what already has drafts. With a git repo connected, it also spots user-facing features in your commits.
- **Asks before writing.** You pick the posts to cover and how many posts per day go out on each platform.
- **Writes like a founder, not a brand.** Hooks, real numbers, no hype words, X's 280-character limit and LinkedIn formatting handled. It never invents numbers or customers.
- **Queues instead of piling up.** Drafts fill set times per day, and each run continues after the last one.
- **Tags your links** with UTM parameters, so your analytics show which posts bring visitors.

## Install

You need [Claude Code](https://code.claude.com) and Python 3.9 or newer (already on macOS and most Linux machines).

In Claude Code:

```
/plugin install social-drafts --marketplace sprifti/social-drafts
```

Or from your shell:

```bash
claude plugin marketplace add sprifti/social-drafts
claude plugin install social-drafts@social-drafts
```

## Set up (once, about 3 minutes)

```
/social-drafts:setup
```

Give it your website. It reads your sitemap and homepage, then asks which sections to watch, whether you post as "I" or "we", your scheduler, and your platforms. Paste a few of your own posts if you want drafts that really sound like you.

Then add your scheduler's API key to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
# Postiz: Settings > Developers > Public API
export POSTIZ_API_KEY=...

# or Publer (Business plan): Settings > Access & Login > API Keys
# scopes: workspaces, accounts, posts
export PUBLER_API_KEY=...
export PUBLER_WORKSPACE_ID=...
```

Open a new terminal so the keys load.

## Use it

```
/social-drafts:draft
```

Run it whenever you've published something, or once a week. You can also hand it something specific:

```
/social-drafts:draft https://yoursite.com/blog/new-post
/social-drafts:draft the Stripe integration I merged today, 2 a day
/social-drafts:draft dry run
```

A dry run shows exactly what would be sent without touching your scheduler. Do one the first time.

## Where things live

Everything stays on your machine, in `~/.config/social-drafts/`:

| File | What it is |
|---|---|
| `profile.md` | Your startup and voice. Edit it any time; drafts follow it. |
| `config.json` | Site, sitemaps, sections to watch, feeds, timezone, scheduler, platforms. |
| `state.json` | Which posts already have drafts, and the last time slots used. |

API keys are read from your environment and never written to these files. To keep separate profiles for two products, set `SOCIAL_DRAFTS_HOME` to a different folder for each.

### config.json

```json
{
  "site": "https://yoursite.com",
  "sitemaps": ["https://yoursite.com/sitemap.xml"],
  "sections": ["/blog/", "/changelog/"],
  "feeds": ["https://you.substack.com/feed"],
  "feature_repo": "/Users/you/code/your-app",
  "timezone": "Europe/Lisbon",
  "provider": "postiz",
  "platforms": ["x", "linkedin"],
  "utm": true,
  "allow_em_dashes": false
}
```

Every key can be overridden by an environment variable: `SOCIAL_SITE`, `SOCIAL_SITEMAPS`, `SOCIAL_SECTIONS`, `SOCIAL_FEEDS` (comma-separated lists), `SOCIAL_FEATURE_REPO`, `SOCIAL_TZ`, `DEFAULT_SOCIAL_PROVIDER`, `SOCIAL_PLATFORMS`, `SOCIAL_UTM`, `SOCIAL_ALLOW_EM_DASHES`.

### Posting times

| Per day | X | LinkedIn |
|---|---|---|
| 1 | 10:00 | 09:00 |
| 2 | 10:00, 16:00 | 09:00, 15:00 |
| 3 | 09:00, 13:00, 17:00 | 09:00, 13:00, 17:00 |
| 4 | 09:00, 12:00, 15:00, 18:00 | |

Times are in the timezone from your config. Move any draft in your scheduler as you like.

## Good to know

- **Drafts only.** The plugin only ever creates drafts. Scheduling and publishing happen in Postiz or Publer, by you.
- **First run.** Posts from the last 14 days count as new; older ones are treated as already posted, so you don't get drafts for your whole archive.
- **Publer and X threads.** Publer's API has no documented way to create threads, so threads arrive as one draft. Use "Split into a thread" in Publer's editor.
- **Rate limits.** Postiz allows 30 API calls per hour. A typical run uses 3 to 10 (one per distinct draft time, plus one lookup).
- **Em dashes.** They're blocked by default because they make posts read as AI-written. Set `"allow_em_dashes": true` if you like them.
- **Claude Code on your own machine.** The scripts call your site and your scheduler's API directly, so run Claude Code locally. Cloud sandboxes usually block those requests.

## Uninstall

```bash
claude plugin uninstall social-drafts@social-drafts
rm -rf ~/.config/social-drafts   # removes your profile and history
```

## Credits

Made by [Serena](https://chartsy.app/blog/authors/serena-prifti), founder of [Chartsy](https://chartsy.app), subscription analytics for SaaS founders. I built this because I kept shipping and never posting about it.

MIT licensed. Issues and pull requests welcome.
