"""Holt Xetra-Tagesschlusskurse von Alpha Vantage und schreibt data/prices.json.

Läuft in der GitHub Action. Braucht die Umgebungsvariable ALPHAVANTAGE_KEY.
Bestehende Kurse bleiben erhalten; neue Tage werden ergänzt, so wächst die Historie.
Schlägt ein Symbol fehl, bleiben seine alten Daten stehen.
"""
import csv
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SYMBOLS = {
    "xaix": "XAIX.DEX",
    "aswc": "ASWC.DEX",
    "iusq": "IUSQ.DEX",
    "is3n": "IS3N.DEX",
    "mweq": "MWEQ.DEX",
    "euna": "EUNA.DEX",
    "p911": "P911.DEX",
    "5j50": "5J50.DEX",
}
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "prices.json")
KEEP_DAYS = 800  # rund 3 Jahre Handelstage


def fetch(symbol: str, key: str, full: bool) -> list:
    q = urllib.parse.urlencode({
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "outputsize": "full" if full else "compact",
        "datatype": "csv",
        "apikey": key,
    })
    with urllib.request.urlopen("https://www.alphavantage.co/query?" + q, timeout=60) as r:
        text = r.read().decode("utf-8")
    if not text.startswith("timestamp"):
        raise RuntimeError(text.strip()[:300])
    rows = []
    for rec in csv.DictReader(io.StringIO(text)):
        try:
            rows.append([rec["timestamp"], round(float(rec["close"]), 4)])
        except (KeyError, ValueError):
            continue
    return rows


def main() -> int:
    key = os.environ.get("ALPHAVANTAGE_KEY", "").strip()
    if not key:
        print("ALPHAVANTAGE_KEY fehlt (GitHub: Settings → Secrets and variables → Actions).")
        return 1
    try:
        with open(OUT, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"series": {}}
    series = data.setdefault("series", {})
    ok, failed = 0, []
    for i, (pid, sym) in enumerate(SYMBOLS.items()):
        if i:
            time.sleep(3)  # kostenloser Key: höchstens 1 Abfrage pro Sekunde
        try:
            rows = fetch(sym, key, full=False)
        except Exception as e:  # noqa: BLE001
            print(f"{sym}: {e}")
            failed.append(sym)
            continue
        merged = {d: c for d, c in series.get(pid, [])}
        merged.update({d: c for d, c in rows})
        series[pid] = sorted(merged.items())[-KEEP_DAYS:]
        ok += 1
        print(f"{sym}: {len(rows)} Kurse, letzter {rows[0][0] if rows else '-'}")
    data["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["failed"] = failed
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{ok} von {len(SYMBOLS)} aktualisiert.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
