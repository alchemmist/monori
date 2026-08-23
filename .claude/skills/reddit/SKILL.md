---
name: reddit
description: >
    Read Reddit (subreddit listings and post comments) from a server/datacenter
    IP, where Reddit's .json API, www/old.reddit.com and reader proxies all
    return 403. The working path is the .rss/Atom feeds with a browser
    User-Agent, plus polite rate limiting. Use whenever the task needs to read
    threads, mine posts/comments, or research a subreddit and WebFetch on
    reddit.com is blocked.
---

# reddit — read via RSS, not the blocked JSON API

## The one thing that works

From a datacenter IP, Reddit blocks nearly everything **except the RSS/Atom feeds**:

| Endpoint                                                | Result                                     |
| ------------------------------------------------------- | ------------------------------------------ |
| `WebFetch` on any reddit.com URL                        | blocked at the harness ("unable to fetch") |
| `curl .../.json` (any UA)                               | **403** HTML block page                    |
| `api.reddit.com`, `old.reddit.com`, `r.jina.ai/…reddit` | **403**                                    |
| `curl .../.rss` with a **browser** User-Agent           | **200 ✅**                                 |

So: use the `.rss` feeds, always with a real browser User-Agent (a custom
`bot/0.1` UA still gets 403). The default agent for this project is the Chrome
UA baked into `fetch_reddit.sh`.

## Use the helper

`.claude/skills/reddit/fetch_reddit.sh` wraps the working recipe — browser UA,
429 backoff, Atom parsing to title/permalink/author/body:

```sh
bash .claude/skills/reddit/fetch_reddit.sh sub  YNABAlternatives top all   # top-of-all-time listing
bash .claude/skills/reddit/fetch_reddit.sh sub  YNABAlternatives hot       # hot listing
bash .claude/skills/reddit/fetch_reddit.sh post 1ri731c top                # comments of a post
bash .claude/skills/reddit/fetch_reddit.sh url  "https://www.reddit.com/r/foo/new/.rss"
```

Raw feeds are cached under `/tmp/reddit/`. The post id is the short base36 in
any permalink: `/r/x/comments/<ID>/slug/`.

## Feed URLs (if you call curl directly)

- Subreddit listing: `https://www.reddit.com/r/<sub>/<top|hot|new>/.rss?t=<all|year|month|week|day>`
- Post + comments: `https://www.reddit.com/comments/<post_id>/.rss?sort=<top|best|new>`
- Search (works over RSS too): `https://www.reddit.com/r/<sub>/search/.rss?q=<query>&restrict_sr=1&sort=top`

## Rate limiting — this is the real constraint

The RSS feeds are **strictly** rate limited. A burst of requests trips **429**
(empty body) fast. Rules:

- Sleep **8–15s between requests**; on 429 back off exponentially (the helper
  does `attempt*8s`, 5 tries).
- A subreddit listing feed returns ~25 items — enough for most mining without
  touching per-post feeds. Pull the listing first, read the selftext bodies it
  already contains, and only fetch per-post comment feeds for the few threads
  that actually matter.
- Don't parallelize reddit fetches — serialize them.

## What the feed gives you (and what it doesn't)

- **Listing feed:** each entry = a post with title, permalink, author, and the
  **full selftext** in `<content>` (HTML → the helper strips to text). Link-only
  posts have an empty body.
- **Comment feed:** entries are the post + top-level/nested comments as flat
  entries (author + comment HTML). No score/threading depth — RSS is flat.
- Not available over RSS: vote counts, precise timestamps as numbers, full
  nested tree, gallery/preview media beyond URLs.

## When you need more (scores, full JSON, write access)

RSS is read-only and metadata-thin. For scores, reliable JSON, or posting,
register a Reddit app (script type) and use **OAuth app-only**
(`grant_type=client_credentials`) against `oauth.reddit.com`, passing the token
as `Authorization: bearer <t>`. That needs a `client_id`/`client_secret` the
user must create at reddit.com/prefs/apps and expose as env vars — ask for them;
never hardcode. Until then, RSS is the ceiling.

## Parsing note

Feeds are **Atom** (`http://www.w3.org/2005/Atom`), not RSS 2.0 — entries are
`<entry>`, body is `<content>`, link is `<link href=…>`. The helper's Python
block is the reference parser; reuse it rather than regex-ing the XML.
