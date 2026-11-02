"""Collect and rank relevant RSS news candidates without paid AI or auto-publishing."""
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests

ROOT = Path(__file__).resolve().parents[1]
SOURCES = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
OUT = ROOT / 'data/news_candidates.json'
LIMIT = max(int(os.getenv('MAX_ITEMS', '10')), 1)
CUTOFF = datetime.now(timezone.utc) - timedelta(days=14)

# Scores are simple editorial rules, not AI analysis.
TOPICS = {
    'digital_assets': (5, [r'\bdigital assets?\b', r'\bcrypto(?:currency|currencies|assets?)?\b', r'\bblockchain\b', r'\bbitcoin\b', r'\bethereum\b', r'\bkrypto\w*', r'\bdigitale? vermögenswerte\b']),
    'tokenization': (5, [r'\btokeni[sz]\w*', r'\btokenisierung\w*', r'\btokenisierte\w*', r'\bsecurity tokens?\b', r'\bsto\b', r'\brwa\b', r'\breal.world assets?\b']),
    'stablecoins_payments': (5, [r'\bstablecoins?\b', r'\bcbdc\b', r'\bdigital (?:franc|currency|money)\b', r'\bzahlungsverkehr\b', r'\bzahlungsabwicklung\b', r'\bsettlement\b', r'\biso.?20022\b']),
    'funds_etp': (4, [r'\betfs?\b', r'\betps?\b', r'\bexchange.traded\b', r'\bcollective investment\b', r'\bkollektivanlage\w*', r'\banlagefonds\b']),
    'custody_banking': (4, [r'\bcustod\w*', r'\bverwahrung\b', r'\bverwahrstelle\b', r'\bdigital asset bank\w*', r'\bcrypto bank\w*', r'\bkryptobank\w*']),
    'market_infrastructure': (3, [r'\bfinancial market infrastructure\b', r'\bfinanzmarktinfrastruktur\w*', r'\bsecurities depository\b', r'\bwertpapierverwahr\w*', r'\bdistributed ledger\b', r'\bdlt\b']),
}
PATTERNS = {name: [re.compile(p, re.IGNORECASE) for p in pats] for name, (_, pats) in TOPICS.items()}

def https(url):
    p = urlparse(url)
    return p.scheme == 'https' and bool(p.hostname) and not p.username and not p.password

def clean(value, length):
    value = re.sub(r'<[^>]*>', ' ', str(value or ''))
    return re.sub(r'\s+', ' ', html.unescape(value)).strip()[:length]

def relevance(title, summary):
    # Title matches are weighted higher than excerpt matches.
    matches = []
    score = 0
    for topic, (weight, _) in TOPICS.items():
        pats = PATTERNS[topic]
        in_title = any(p.search(title) for p in pats)
        in_excerpt = any(p.search(summary) for p in pats)
        if in_title or in_excerpt:
            matches.append(topic)
            score += weight * (2 if in_title else 1)
    return score, matches

def main():
    previous = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {'candidates': []}
    by_url = {}
    # Re-evaluate previously collected candidates so irrelevant old items disappear.
    for item in previous.get('candidates', []):
        if not isinstance(item, dict) or not https(item.get('source_url', '')):
            continue
        score, topics = relevance(item.get('original_title', ''), item.get('source_excerpt', ''))
        if score:
            item['relevance_score'] = score
            item['matched_topics'] = topics
            by_url[item['source_url']] = item
    added = 0
    for src in SOURCES:
        try:
            url = src['feed_url']
            if not https(url):
                raise ValueError('Invalid HTTPS feed')
            resp = requests.get(url, timeout=20, headers={'User-Agent': 'SDAH-NewsCollector/1.0 (+https://swissdigitalassethub.ch/)'})
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            if not feed.entries:
                print('NO RSS ENTRIES:', src['name'], file=sys.stderr)
            seen = 0
            relevant = 0
            for entry in feed.entries[:50]:
                seen += 1
                link = entry.get('link', '').strip()
                if not https(link) or link in by_url:
                    continue
                date_tuple = entry.get('published_parsed') or entry.get('updated_parsed')
                date = datetime(*date_tuple[:6], tzinfo=timezone.utc) if date_tuple else None
                if date and date < CUTOFF:
                    continue
                title = clean(entry.get('title', ''), 250)
                summary = clean(entry.get('summary', ''), 900)
                score, topics = relevance(title, summary)
                if not score:
                    continue
                by_url[link] = {
                    'id': hashlib.sha256(link.encode()).hexdigest()[:16],
                    'source_name': src['name'],
                    'source_url': link,
                    'original_title': title,
                    'published_at': date.date().isoformat() if date else '',
                    'source_excerpt': summary,
                    'review_status': 'unreviewed',
                    'relevance_score': score,
                    'matched_topics': topics,
                }
                added += 1
                relevant += 1
            print(f"SOURCE: {src['name']}; scanned: {seen}; new relevant: {relevant}")
        except Exception as exc:
            print('SOURCE ERROR:', src.get('name', 'unknown'), str(exc), file=sys.stderr)
    candidates = sorted(by_url.values(), key=lambda x: (x.get('relevance_score', 0), x.get('published_at', '')), reverse=True)[:LIMIT]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'candidates': candidates}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'New relevant: {added}; saved candidates: {len(candidates)}; no AI API; no public publishing')

if __name__ == '__main__':
    main()
