"""The content-policy block list, data/news-blocked.json (rule M4 in scripts/news.py): one-way ids of the stories removed
under the content policy, with the day each was blocked. No titles, links or reasons: the repository is public.

news.py writes it and skips blocked stories when it collects; the news archive (scripts/news_archive.py) uses it too, so
a story blocked after it was archived is taken out of the archive's files (news_archive.drop) and is never shown from an
archived copy (news_archive.shown, as the build and the app export use it). Rule-based, no AI and no network.

  block_keys(url, source, title)  the ids a story is blocked by: the hash of its exact URL (the item id), of its
                                  canonical URL (no tracking query), and of its source and normalised headline
  is_blocked(item, blocked)       does any of the story's ids appear in `blocked` ({id: day})
  load(path)                      the ids of data/news-blocked.json ({} when it is missing or unreadable)
"""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

import policy

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'data' / 'news-blocked.json'

# Query parameters that only track where a click came from: the same story with any of them is the same story.
TRACKING = re.compile(r'^(?:utm_\w*|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|igshid|ref|ref_src|output|cmpid|ncid|smid|at_medium|at_campaign|__twitter_impression)$', re.I)

def canonical_url(url):
    """The URL with the host in lower case and without the fragment, tracking parameters and a trailing slash, the
    path percent-decoded: https://X.com/a/?utm_source=rss#c and https://x.com/a are one story. A URL that is already
    canonical is unchanged, so its hash is the item id."""
    u = urlparse((url or '').strip())
    host = (u.hostname or '').lower()
    query = urlencode(sorted((k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if not TRACKING.match(k)))
    return urlunparse(('https', host, unquote(u.path).rstrip('/') or '/', '', query, ''))

def _hash(text):
    return hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]

def block_keys(url, source_id, title):
    """One-way ids a removed story is blocked by: the hash of its exact URL (the item id), of its canonical URL, and of
    its source and normalised headline, so it does not come back with a tracking query or as a repost."""
    headline = ' '.join(re.findall(r'\w+', policy.normalize(title).casefold()))
    return {_hash(url), _hash(canonical_url(url)), _hash(f'title\x1f{source_id}\x1f{headline}')}

def is_blocked(item, blocked):
    return bool(blocked) and not blocked.keys().isdisjoint(block_keys(item.get('url', ''), item.get('source', ''), item.get('title', '')))

def load(path=None):
    """The block list's ids ({id: day blocked}); {} when the file is missing or unreadable."""
    try:
        ids = json.loads(Path(path or PATH).read_text(encoding='utf-8')).get('ids') or {}
    except (OSError, ValueError, AttributeError):
        return {}
    return dict(ids) if isinstance(ids, dict) else {}
