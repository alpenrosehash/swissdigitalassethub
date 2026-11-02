def story_group(item):
    """Group repeated reports about the same major incident."""
    title = clean(item['original_title']).lower()
    if re.search(r'binance', title) and re.search(r'hack|diebstahl|breach|angriff', title):
        return 'binance-security-incident'
    return None


def main():
    previous = {'candidates': []}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            print(f'WARNING: Cannot read previous candidates: {exc}', file=sys.stderr)

    gathered = []
    successful_sources = 0
    for src in SOURCES:
        name = src.get('name', 'unknown')
        try:
            feed_url = src['feed_url']
            if not https(feed_url):
                raise ValueError('Feed must use HTTPS')
            response = requests.get(feed_url, timeout=20, headers={
                'User-Agent': 'SDAH-NewsCollector/1.0 (+https://swissdigitalassethub.ch/)'
            })
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            if not feed.entries:
                print(f'NO RSS ENTRIES: {name}', file=sys.stderr)
            successful_sources += 1
            accepted = 0
            for entry in feed.entries[:50]:
                url = str(entry.get('link', '')).strip()
                if not https(url):
                    continue
                date_tuple = entry.get('published_parsed') or entry.get('updated_parsed')
                date = datetime(*date_tuple[:6], tzinfo=timezone.utc) if date_tuple else None
                if date and date < CUTOFF:
                    continue
                title = clean(entry.get('title', ''), 250)
                excerpt = clean(entry.get('summary', ''))
                result = classify(title, excerpt)
                if result is None:
                    continue
                score, topics = result
                canonical = canonical_url(url)
                gathered.append({
                    'id': hashlib.sha256(canonical.encode()).hexdigest()[:16],
                    'source_name': name,
                    'source_url': canonical,
                    'original_title': title,
                    'published_at': date.date().isoformat() if date else '',
                    'source_excerpt': excerpt,
                    'review_status': 'unreviewed',
                    'relevance_score': score,
                    'matched_topics': topics,
                })
                accepted += 1
            print(f'SOURCE: {name}; scanned: {min(len(feed.entries), 50)}; relevant: {accepted}')
        except Exception as exc:
            print(f'SOURCE ERROR: {name}: {exc}', file=sys.stderr)

    # Keep older candidates only when all feeds fail; never silently erase data.
    if successful_sources == 0:
        print('ERROR: No RSS sources were successfully fetched; existing data left unchanged.', file=sys.stderr)
        sys.exit(1)

    # Reclassify previously saved candidates so old price-only items do not survive.
    for old in previous.get('candidates', []):
        if not isinstance(old, dict) or not https(old.get('source_url', '')):
            continue
        date_str = old.get('published_at', '')
        try:
            if date_str and datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc) < CUTOFF:
                continue
        except (TypeError, ValueError):
            continue
        title = clean(old.get('original_title', ''), 250)
        excerpt = clean(old.get('source_excerpt', ''))
        result = classify(title, excerpt)
        if result is None:
            continue
        score, topics = result
        canonical = canonical_url(old['source_url'])
        gathered.append({
            'id': hashlib.sha256(canonical.encode()).hexdigest()[:16],
            'source_name': old.get('source_name', ''),
            'source_url': canonical,
            'original_title': title,
            'published_at': date_str,
            'source_excerpt': excerpt,
            'review_status': old.get('review_status', 'unreviewed'),
            'relevance_score': score,
            'matched_topics': topics,
        })

    gathered.sort(key=lambda x: (x['relevance_score'], x['published_at']), reverse=True)
    selected = []
    groups = set()
    for candidate in gathered:
        group = story_group(candidate)
        if group and group in groups:
            continue
        if any(same_story(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
        if group:
            groups.add(group)
        if len(selected) >= LIMIT:
            break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    output = json.dumps({'candidates': selected}, ensure_ascii=False, indent=2) + '\n'
    if not OUT.exists() or OUT.read_text(encoding='utf-8') != output:
        OUT.write_text(output, encoding='utf-8')
    print(f'Collected: {len(gathered)} relevant entries; saved candidates: {len(selected)}; no AI API; no public publishing')


if __name__ == '__main__':
    main()
