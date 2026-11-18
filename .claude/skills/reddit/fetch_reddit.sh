#!/usr/bin/env bash
# Fetch Reddit content via the RSS/Atom feeds — the only path that still works
# from datacenter IPs without OAuth. The .json API and www/old/reader proxies
# return 403; the .rss feeds return 200 with a browser User-Agent.
#
# Usage:
#   fetch_reddit.sh sub   <subreddit> [top|hot|new] [t=all]   # listing feed
#   fetch_reddit.sh post  <post_id>   [top|best|new]          # comments feed
#   fetch_reddit.sh url   <full .rss url>                     # raw feed
#
# Output: prints parsed entries (title / permalink / body text) to stdout and
# saves the raw feed under /tmp/reddit/. Honors Reddit's rate limit with backoff.
set -euo pipefail

UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
OUT=/tmp/reddit
mkdir -p "$OUT"

build_url() {
  case "$1" in
  sub)
    local sub="$2" sort="${3:-top}" t="${4:-all}"
    echo "https://www.reddit.com/r/${sub}/${sort}/.rss?t=${t}"
    ;;
  post)
    local id="$2" sort="${3:-top}"
    echo "https://www.reddit.com/comments/${id}/.rss?sort=${sort}"
    ;;
  url) echo "$2" ;;
  *)
    echo "unknown mode: $1" >&2
    exit 2
    ;;
  esac
}

url="$(build_url "$@")"
dest="$OUT/feed_$(echo "$url" | tr -c 'a-zA-Z0-9' '_' | tail -c 80).rss"

# Reddit RSS is strictly rate limited: retry 429/5xx with exponential backoff.
code=000
for attempt in 1 2 3 4 5; do
  code=$(curl -s -A "$UA" --max-time 30 -w "%{http_code}" "$url" -o "$dest" || echo 000)
  [ "$code" = "200" ] && [ -s "$dest" ] && break
  wait=$((attempt * 8))
  echo "attempt $attempt: http=$code — backing off ${wait}s" >&2
  sleep "$wait"
done
if [ "$code" != "200" ] || [ ! -s "$dest" ]; then
  echo "failed to fetch $url (last http=$code)" >&2
  exit 1
fi
echo "saved: $dest ($(wc -c <"$dest") bytes)" >&2

python3 - "$dest" <<'PY'
import sys, re, html, xml.etree.ElementTree as ET
ns = {'a': 'http://www.w3.org/2005/Atom'}
root = ET.parse(sys.argv[1]).getroot()
def clean(x): return re.sub(r'\s+', ' ', re.sub('<[^>]+>', ' ', html.unescape(x or ''))).strip()
entries = root.findall('.//a:entry', ns)
print(f"# {clean(root.findtext('a:title', default='', namespaces=ns))} — {len(entries)} entries\n")
for e in entries:
    title = clean(e.findtext('a:title', default='', namespaces=ns))
    link = (e.find('a:link', ns).get('href') if e.find('a:link', ns) is not None else '')
    author = clean(e.findtext('a:author/a:name', default='', namespaces=ns))
    body = clean(e.findtext('a:content', default='', namespaces=ns))
    print(f"### {title}")
    print(f"{author}  {link}")
    if body:
        print(body[:2500] + ('…' if len(body) > 2500 else ''))
    print()
PY
