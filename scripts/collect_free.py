"""SDAH institutional RSS candidate collector. Free, review-only; never publishes."""
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import requests

ROOT = Path(__file__).resolve().parents[1]
SOURCES = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
OUT = ROOT / 'data/news_candidates.json'
LIMIT = max(1, int(os.getenv('MAX_ITEMS', '30')))
CUTOFF = datetime.now(timezone.utc) - timedelta(days=14)

# Strong institutional signals (English and German). Scores are editorial heuristics.
TOPICS = {
    'funds_etp': (7, r'\b(?:etfs?|etps?|exchange.traded|investment funds?|asset management|fonds|anlagefonds|vermögensverwaltung|fund managers?|collective investment|kollektivanlage|pensionskass\w*|pension funds?)\b'),
    'tokenization': (7, r'\b(?:tokeni[sz]\w*|security tokens?|sto|rwa|real.world assets?|digitale wertpapiere|tokenisierte\w*)\b'),
    'stablecoins_payments': (7, r'\b(?:stablecoins?|cbdc|iso.?20022|payment rails?|zahlungsverkehr|zahlungsabwicklung|settlement|digital (?:franc|currency|money)|rlusd|usdc|euroc)\b'),
    'custody_banking': (7, r'\b(?:custod\w*|verwahr\w*|depotbank|crypto.bank\w*|krypto.bank\w*|trust bank|banklizenz|banking licen[cs]e|banking infrastructure|paying agent|prime broker\w*)\b'),
    'regulation': (6, r'\b(?:finma|fsc|bis|basel committee|regulat\w*|aufsicht\w*|licen[cs]\w*|genehmigung\w*|zulassung\w*|compliance|capital requirements|kapitalanforderung\w*)\b'),
    'market_infrastructure': (6, r'\b(?:six swiss exchange|sdx|central securities depositor\w*|clearing|exchange infrastructure|marktinfrastruktur|wertpapierabwicklung|interoperabilit\w*|institutional adoption)\b'),
}
DIGITAL = re.compile(r'\b(?:bitcoin|btc|ethereum|ether|binance|coinbase|bybit|ripple|crypto\w*|krypto\w*|blockchain|digital assets?|digitale vermögenswerte|defi|token\w*|stablecoin\w*)\b', re.I)
INSTITUTIONAL = re.compile(r'\b(?:bank\w*|finanzinstitut\w*|institution\w*|investor\w*|fonds|fund\w*|etf\w*|etp\w*|finma|snb|six|sdx|custod\w*|verwahr\w*|regulat\w*|aufsicht\w*|settlement|zahlung\w*|lizenz\w*|licen[cs]\w*|treasury|wertpapier\w*|kapitalmarkt\w*|capital market\w*|asset manag\w*|vermögensverwalt\w*|pension\w*|rwa|tokeni[sz]\w*|stablecoin\w*|cbdc|paying agent|central bank|zentralbank)\b', re.I)
RISK = re.compile(r'\b(?:hack\w*|breach\w*|cyber\w*|theft|diebstahl|exploit\w*|insolven\w*|bankrupt\w*|liquidit\w*|liquidit[yä]\w*|withdrawal\w*|abhebung\w*|sanction\w*|sanktion\w*|systemic|systemisch\w*|fraud|betrug|outage\w*|ausfall\w*)\b', re.I)
MAJOR_RISK = re.compile(r'\b(?:mrd\.?|billion|milliard\w*|systemic|systemisch|bankrupt\w*|insolven\w*|custod\w*|verwahr\w*|reserves?|reserven|settlement|abwicklung|withdrawal\w*|abhebung\w*)\b', re.I)
PRICE_ONLY = re.compile(r'\b(?:kurs\w*|preis\w*|price|trading below|f[aä]llt unter|rutscht unter|chart\w*|technical analysis|marktkommentar|correlation|korrelation|rendite\w*|high.beta|fed.zinsentscheid)\b', re.I)
TRACKING = {'utm_source','utm_medium','utm_campaign','utm_content','utm_term','fbclid','gclid','mc_cid','mc_eid'}


def https(url):
    p = urlparse(url)
    return p.scheme == 'https' and bool(p.hostname) and not p.username and not p.password


def canonical_url(url):
    p = urlparse(url.strip())
    query = urlencode([(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in TRACKING])
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/') or '/', '', query, ''))


def clean(s, limit=900):
    s = re.sub(r'<[^>]*>', ' ', str(s or ''))
    return re.sub(r'\s+', ' ', html.unescape(s)).strip()[:limit]


def classify(title, excerpt):
    title, excerpt = clean(title, 250), clean(excerpt)
    body = f'{title} {excerpt}'
    matches = [key for key, (_, pattern) in TOPICS.items() if re.search(pattern, body, re.I)]
    digital = bool(DIGITAL.search(body))
    institutional = bool(INSTITUTIONAL.search(body))
    risk = bool(RISK.search(body))
    major_risk = risk and bool(MAJOR_RISK.search(body))
    # Institutional financial innovation, or a consequential risk for institutions.
    if not ((digital and institutional) or (risk and major_risk and digital) or (risk and institutional and major_risk)):
        return None
    if PRICE_ONLY.search(title) and not (re.search(r'\b(?:etf|etp|fund|fonds|bank|regulat|finma|tokeni[sz]|stablecoin|custod|liquidit|liquidit[yä])\w*\b', body, re.I) or major_risk):
        return None
    if risk and not major_risk and not any(t in matches for t in ('custody_banking','stablecoins_payments','market_infrastructure','regulation')):
        return None
    if not matches and not major_risk:
        return None
    score = sum(TOPICS[k][0] for k in matches)
    if digital: score += 3
    if institutional: score += 3
    if major_risk: score += 5
    if risk and 'institutional_risk' not in matches: matches.append('institutional_risk')
    return score, matches


def cluster_key(title):
    text = clean(title).lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    stop = {'der','die','das','und','mit','nach','von','für','bei','den','dem','ein','eine','the','and','with','from','after','into','über','wie','des','auf','sich','ist','will','news'}
    return ' '.join(sorted(set(w for w in text.split() if len(w) > 2 and w not in stop)))


def same_story(a, b):
    if canonical_url(a['source_url']) == canonical_url(b['source_url']):
        return True
    ka, kb = cluster_key(a['original_title']), cluster_key(b['original_title'])
    if not ka or not kb: return False
    wa, wb = set(ka.split()), set(kb.split())
    # Require substantial lexical overlap; avoids merging all articles on Bitcoin.
    return len(wa & wb) >= 3 and (len(wa & wb) / min(len(wa), len(wb)) >= .72 or SequenceMatcher(None, ka, kb).ratio() >= .80)

"""SDAH institutional RSS candidate collector. Free, review-only; never publishes."""
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import requests

ROOT = Path(__file__).resolve().parents[1]
SOURCES = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
OUT = ROOT / 'data/news_candidates.json'
LIMIT = max(1, int(os.getenv('MAX_ITEMS', '30')))
CUTOFF = datetime.now(timezone.utc) - timedelta(days=14)

# Strong institutional signals (English and German). Scores are editorial heuristics.
TOPICS = {
    'funds_etp': (7, r'\b(?:etfs?|etps?|exchange.traded|investment funds?|asset management|fonds|anlagefonds|vermögensverwaltung|fund managers?|collective investment|kollektivanlage|pensionskass\w*|pension funds?)\b'),
    'tokenization': (7, r'\b(?:tokeni[sz]\w*|security tokens?|sto|rwa|real.world assets?|digitale wertpapiere|tokenisierte\w*)\b'),
    'stablecoins_payments': (7, r'\b(?:stablecoins?|cbdc|iso.?20022|payment rails?|zahlungsverkehr|zahlungsabwicklung|settlement|digital (?:franc|currency|money)|rlusd|usdc|euroc)\b'),
    'custody_banking': (7, r'\b(?:custod\w*|verwahr\w*|depotbank|crypto.bank\w*|krypto.bank\w*|trust bank|banklizenz|banking licen[cs]e|banking infrastructure|paying agent|prime broker\w*)\b'),
    'regulation': (6, r'\b(?:finma|fsc|bis|basel committee|regulat\w*|aufsicht\w*|licen[cs]\w*|genehmigung\w*|zulassung\w*|compliance|capital requirements|kapitalanforderung\w*)\b'),
    'market_infrastructure': (6, r'\b(?:six swiss exchange|sdx|central securities depositor\w*|clearing|exchange infrastructure|marktinfrastruktur|wertpapierabwicklung|interoperabilit\w*|institutional adoption)\b'),
}
DIGITAL = re.compile(r'\b(?:bitcoin|btc|ethereum|ether|binance|coinbase|bybit|ripple|crypto\w*|krypto\w*|blockchain|digital assets?|digitale vermögenswerte|defi|token\w*|stablecoin\w*)\b', re.I)
INSTITUTIONAL = re.compile(r'\b(?:bank\w*|finanzinstitut\w*|institution\w*|investor\w*|fonds|fund\w*|etf\w*|etp\w*|finma|snb|six|sdx|custod\w*|verwahr\w*|regulat\w*|aufsicht\w*|settlement|zahlung\w*|lizenz\w*|licen[cs]\w*|treasury|wertpapier\w*|kapitalmarkt\w*|capital market\w*|asset manag\w*|vermögensverwalt\w*|pension\w*|rwa|tokeni[sz]\w*|stablecoin\w*|cbdc|paying agent|central bank|zentralbank)\b', re.I)
RISK = re.compile(r'\b(?:hack\w*|breach\w*|cyber\w*|theft|diebstahl|exploit\w*|insolven\w*|bankrupt\w*|liquidit\w*|liquidit[yä]\w*|withdrawal\w*|abhebung\w*|sanction\w*|sanktion\w*|systemic|systemisch\w*|fraud|betrug|outage\w*|ausfall\w*)\b', re.I)
MAJOR_RISK = re.compile(r'\b(?:mrd\.?|billion|milliard\w*|systemic|systemisch|bankrupt\w*|insolven\w*|custod\w*|verwahr\w*|reserves?|reserven|settlement|abwicklung|withdrawal\w*|abhebung\w*)\b', re.I)
PRICE_ONLY = re.compile(r'\b(?:kurs\w*|preis\w*|price|trading below|f[aä]llt unter|rutscht unter|chart\w*|technical analysis|marktkommentar|correlation|korrelation|rendite\w*|high.beta|fed.zinsentscheid)\b', re.I)
TRACKING = {'utm_source','utm_medium','utm_campaign','utm_content','utm_term','fbclid','gclid','mc_cid','mc_eid'}


def https(url):
    p = urlparse(url)
    return p.scheme == 'https' and bool(p.hostname) and not p.username and not p.password


def canonical_url(url):
    p = urlparse(url.strip())
    query = urlencode([(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in TRACKING])
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/') or '/', '', query, ''))


def clean(s, limit=900):
    s = re.sub(r'<[^>]*>', ' ', str(s or ''))
    return re.sub(r'\s+', ' ', html.unescape(s)).strip()[:limit]


def classify(title, excerpt):
    title, excerpt = clean(title, 250), clean(excerpt)
    body = f'{title} {excerpt}'
    matches = [key for key, (_, pattern) in TOPICS.items() if re.search(pattern, body, re.I)]
    digital = bool(DIGITAL.search(body))
    institutional = bool(INSTITUTIONAL.search(body))
    risk = bool(RISK.search(body))
    major_risk = risk and bool(MAJOR_RISK.search(body))
    # Institutional financial innovation, or a consequential risk for institutions.
    if not ((digital and institutional) or (risk and major_risk and digital) or (risk and institutional and major_risk)):
        return None
    if PRICE_ONLY.search(title) and not (re.search(r'\b(?:etf|etp|fund|fonds|bank|regulat|finma|tokeni[sz]|stablecoin|custod|liquidit|liquidit[yä])\w*\b', body, re.I) or major_risk):
        return None
    if risk and not major_risk and not any(t in matches for t in ('custody_banking','stablecoins_payments','market_infrastructure','regulation')):
        return None
    if not matches and not major_risk:
        return None
    score = sum(TOPICS[k][0] for k in matches)
    if digital: score += 3
    if institutional: score += 3
    if major_risk: score += 5
    if risk and 'institutional_risk' not in matches: matches.append('institutional_risk')
    return score, matches


def cluster_key(title):
    text = clean(title).lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    stop = {'der','die','das','und','mit','nach','von','für','bei','den','dem','ein','eine','the','and','with','from','after','into','über','wie','des','auf','sich','ist','will','news'}
    return ' '.join(sorted(set(w for w in text.split() if len(w) > 2 and w not in stop)))


def same_story(a, b):
    if canonical_url(a['source_url']) == canonical_url(b['source_url']):
        return True
    ka, kb = cluster_key(a['original_title']), cluster_key(b['original_title'])
    if not ka or not kb: return False
    wa, wb = set(ka.split()), set(kb.split())
    # Require substantial lexical overlap; avoids merging all articles on Bitcoin.
    return len(wa & wb) >= 3 and (len(wa & wb) / min(len(wa), len(wb)) >= .72 or SequenceMatcher(None, ka, kb).ratio() >= .80)
    if __name__ == "__main__":
    main()

