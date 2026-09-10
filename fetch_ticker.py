# -*- coding: utf-8 -*-
"""
fetch_ticker.py — läuft in GitHub Actions (Cloud), NICHT lokal.

Holt die RSS-Feeds aus feeds.txt, pflegt einen mitwachsenden 60-Tage-Cache
(_cache.json) und schreibt pro Eintrag aus ticker-config.json eine gefilterte
Datei `ticker-<ID>.json` (ID = Ticker-Kennung, z. B. `wg12iw-bpe06`), die die
Unterrichtsseiten per fetch() laden.

Kein Key, kein Secret — nur öffentliche Feeds rein, öffentliche JSON raus.

Abhängigkeit (im Workflow per pip installiert): feedparser, requests.
"""

from __future__ import annotations
import datetime as dt
import json
import re
import sys
from pathlib import Path

import feedparser
import requests

HERE = Path(__file__).resolve().parent
FEEDS = HERE / "feeds.txt"
CONFIG = HERE / "ticker-config.json"
CACHE = HERE / "_cache.json"

MAX_AGE_DAYS = 60
CACHE_HARD_CAP = 1500
SUMMARY_CAP = 240
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) newsticker/1.0 "
      "(Unterrichtsmaterial-Recherche)")


# --------------------------------------------------------------------------- #
def parse_feeds(path):
    """feeds.txt -> [(label, url, paywall_bool)]. Format: 'label | url | 0/1'."""
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        label = parts[0] if parts else ""
        url = parts[1] if len(parts) > 1 else ""
        paywall = len(parts) > 2 and parts[2] in ("1", "true", "yes", "paywall")
        if url:
            out.append((label or url, url, paywall))
    return out


def fetch_bytes(url):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=25, allow_redirects=True)
    r.raise_for_status()
    return r.content


def entry_iso(entry):
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            return dt.datetime(*st[:6], tzinfo=dt.timezone.utc).isoformat()
    return None


def clean_summary(entry, limit=SUMMARY_CAP):
    text = entry.get("summary", "") or ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def load_cache():
    if CACHE.exists():
        try:
            data = json.loads(CACHE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data
        except (ValueError, OSError):
            pass
    return {"updated": None, "items": []}


def prune(items, now):
    cutoff = now - dt.timedelta(days=MAX_AGE_DAYS)
    kept = []
    for it in items:
        stamp = it.get("published") or it.get("first_seen")
        try:
            when = dt.datetime.fromisoformat(stamp) if stamp else None
        except ValueError:
            when = None
        if when is None:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt.timezone.utc)
        if when >= cutoff:
            kept.append(it)
    kept.sort(key=lambda it: it.get("published") or it.get("first_seen") or "", reverse=True)
    return kept[:CACHE_HARD_CAP]


def build_matchers(terms):
    pats = []
    for t in terms:
        t = (t or "").strip().lower()
        if not t:
            continue
        if len(t) <= 4 and " " not in t:
            pats.append(re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)", re.I))
        else:
            pats.append(re.compile(r"(?<!\w)" + re.escape(t), re.I))
    return pats


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat()
    sources = parse_feeds(FEEDS)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    cache = load_cache()

    by_link = {}
    for it in cache["items"]:
        by_link[it.get("link") or (it.get("label", "") + "|" + it.get("title", ""))] = it

    added, ok, failed = 0, 0, []
    for label, url, paywall in sources:
        try:
            parsed = feedparser.parse(fetch_bytes(url))
            if parsed.bozo and not parsed.entries:
                raise RuntimeError(getattr(parsed, "bozo_exception", "Parse-Fehler"))
        except Exception as e:
            failed.append((label, str(e).splitlines()[0][:90]))
            continue
        ok += 1
        for entry in parsed.entries:
            title = (entry.get("title", "") or "").strip()
            if not title:
                continue
            link = entry.get("link", "").strip()
            key = link or (label + "|" + title)
            if key in by_link:
                continue
            by_link[key] = {
                "label": label,
                "title": title,
                "summary": clean_summary(entry),
                "link": link,
                "published": entry_iso(entry),
                "first_seen": now_iso,
                "paywall": bool(paywall),
            }
            added += 1

    items = prune(list(by_link.values()), now)
    CACHE.write_text(json.dumps({"updated": now_iso, "items": items},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"cache: +{added} neu, {len(items)} im Fenster, {ok}/{len(sources)} Feeds ok",
          file=sys.stderr)
    for n, err in failed:
        print(f"  ! {n}: {err}", file=sys.stderr)

    # Pro BPE eine gefilterte Datei schreiben.
    known = {label for label, _url, _pw in sources}   # entfernte Quellen sofort raus
    for bpe, spec in config.items():
        pos = build_matchers(spec.get("keywords", []))
        neg = build_matchers(spec.get("negative", []))
        maxn = int(spec.get("max", 12))
        hits = []
        for it in items:
            if it.get("label") not in known:
                continue
            hay = (it.get("title", "") + " " + it.get("summary", "")).lower()
            if neg and any(p.search(hay) for p in neg):
                continue
            if any(p.search(hay) for p in pos):
                hits.append(it)
        hits.sort(key=lambda it: it.get("published") or it.get("first_seen") or "", reverse=True)
        payload = {"id": bpe, "updated": now_iso, "items": hits[:maxn]}
        (HERE / f"ticker-{bpe}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  ticker-{bpe}.json: {len(hits[:maxn])} Meldungen", file=sys.stderr)


if __name__ == "__main__":
    main()
