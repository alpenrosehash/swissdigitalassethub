# SDAH Swiss–Korea AI Intelligence

This is a **static HTML site** plus an optional scheduled GitHub Actions editorial workflow. It retains the original homepage design, founder image and EN/KR switch. **No API key is ever put in browser JavaScript.**

## Files

- `index.html`: original homepage with approved-news cards; original cards remain as fallback until the first approval.
- `intelligence.html`: bilingual index and detailed analysis pages (`?article=<id>`).
- `data/articles.json`: **only manually approved** published articles; initially empty.
- `sources.json`: RSS sources (sample endpoints; **test/verify before enabling**; FINMA's RSS landing page may not itself be an RSS XML feed, and SNB paths may change).
- `scripts/collect.py`: RSS collection, duplicate prevention, AI draft generation; only writes `drafts/` and `data/seen.json`.
- `scripts/publish.py`: manual validation and promotion of a reviewed draft into `data/articles.json`.
- `.github/workflows/editorial-drafts.yml`: scheduled draft PR, no auto-publish.

## Install on GitHub

1. Back up your existing GitHub repository. Copy these files into the **same directory as the current homepage** (typically repository root). Do not overwrite any other existing assets. Check that your hosting serves `index.html`, `intelligence.html` and `data/articles.json` at the same URL level. GitHub Pages can serve these directly; if using another host, confirm its deploy configuration.
2. In GitHub **Settings → Secrets and variables → Actions**, create repository secret `OPENAI_API_KEY` (OpenAI API billing is separate from ChatGPT subscription).
3. In GitHub **Settings → Actions → General**, allow GitHub Actions to create pull requests if your repository policy permits. Some orgs disallow this; then configure a PAT or GitHub App with minimal repository permissions. Set default workflow permissions appropriately. Ensure branch protection/review policies.
4. Check each RSS endpoint in `sources.json` returns a real RSS/Atom feed; replace broken endpoints with official feed URLs. No claim is made that these sample paths work today. You may add more official feeds as available. Do not scrape sites in violation of terms.
5. Push to GitHub. Go to **Actions → SDAH AI editorial drafts → Run workflow** for a manual test. The scheduled run is weekdays 06:20 UTC (not Zurich-local time).
6. Review the created PR and every claim against its **original official source**. The AI only sees an RSS excerpt, not the full article; do not publish unsupported claims. Merge the draft PR to preserve it, then locally run `python scripts/publish.py drafts/<id>.json`, review the resulting diff to `data/articles.json`, commit and push or submit a **separate publication PR**. Publishing is not automatic on draft PR merge.
7. Confirm live homepage news cards and detail pages work, and EN/KR switching works. If no articles are approved, homepage retains the four original editorial cards.

## Operational safeguards

- Drafts are not public website content until explicitly promoted and merged into the deployed branch. **GitHub draft PRs may be visible to repository collaborators or the public if the repository is public**; avoid confidential customer details.
- `data/seen.json` prevents duplicate draft generation; failed feeds do not mark items seen. `source_excerpt` and original titles remain only in editorial drafts.
- `MAX_ITEMS` caps paid AI calls per run. Set OpenAI usage limits and check Actions billing. Schedule timing is best-effort.
- The model is prompted to distinguish facts from hypotheses, but **human review is mandatory**. Source dates, jurisdiction, licensing, partnership claims, and Korean regulatory references need independent verification.
- Browser renders article fields with `textContent`, not `innerHTML`, to prevent HTML injection. External source links use HTTPS and `noopener noreferrer`.
- No copying full source articles. Verify feed reuse rights and cite/link originals. Add editorial policies and legal disclaimers if needed.
- If feed retrieval fails, no news is fabricated. Verify the RSS URLs and inspect Actions logs.

## Local test

Run a local server in the folder: `python -m http.server 8000`, then open `http://localhost:8000/`. A local server is needed for `fetch('data/articles.json')` in many browsers.

To create drafts locally: `pip install -r requirements.txt` then set `OPENAI_API_KEY` as an environment variable and run `python scripts/collect.py`. **Never commit your key.**

## Editorial publication process

1. Verify source and rewrite/approve draft in `drafts/`.
2. `python scripts/publish.py drafts/<id>.json`
3. Inspect `git diff data/articles.json` and open a separate publication PR; merge after final approval.

This is an initial MVP, not a complete CMS, source verification engine, or legal compliance review.
