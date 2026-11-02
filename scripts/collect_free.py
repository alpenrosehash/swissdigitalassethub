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
