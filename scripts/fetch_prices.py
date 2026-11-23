"""Holt Xetra-Tagesschlusskurse und schreibt data/prices.json.

Quellen (je Wertpapier):
1. Yahoo Finance (Xetra, Kürzel .DE): tagesaktuell kurz nach Börsenschluss, kein Key nötig.
   Neue Kurse werden nur übernommen, wenn sie an überlappenden Tagen zu den
   gespeicherten Kursen passen (Schutz vor falschem Wertpapier/Börsenplatz).
2. Alpha Vantage (Kürzel .DEX) als Ersatz, wenn Yahoo nichts liefert.
   Braucht die Umgebungsvariable ALPHAVANTAGE_KEY.

Bestehende Kurse bleiben erhalten; neue Tage werden ergänzt, so wächst die Historie.
"""
import csv
import io
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SYMBOLS = {  # id: (Yahoo, Alpha Vantage)
    "xaix": ("XAIX.DE", "XAIX.DEX"),
    "aswc": ("ASWC.DE", "ASWC.DEX"),
    "iusq": ("IUSQ.DE", "IUSQ.DEX"),
    "is3n": ("IS3N.DE", "IS3N.DEX"),
    "mweq": ("MWEQ.DE", "MWEQ.DEX"),
    "euna": ("EUNA.DE", "EUNA.DEX"),
    "p911": ("P911.DE", "P911.DEX"),
    "5j50": ("5J50.DE", "5J50.DEX"),
}
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "prices.json")
KEEP_DAYS = 800
UA = {"User-Agent": "Mozilla/5.0 (depot-monitor; GitHub Actions)"}


def get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def yahoo(symbol: str, rng: str) -> list:
    q = urllib.parse.urlencode({"range": rng, "interval": "1d", "includePrePost": "false"})
    last_err = None
    for host in ("query1", "query2"):
        try:
            data = json.loads(get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}?{q}"))
            res = data["chart"]["result"][0]
            meta = res.get("meta", {})
            if meta.get("currency") not in (None, "EUR"):
                raise RuntimeError(f"Währung {meta.get('currency')}")
            ts = res.get("timestamp") or []
            closes = res["indicators"]["quote"][0]["close"]
            tz = meta.get("gmtoffset", 3600)
            rows = []
            for t, c in zip(ts, closes):
                if c is None:
                    continue
                d = datetime.fromtimestamp(t + tz, timezone.utc).strftime("%Y-%m-%d")
                rows.append([d, round(float(c), 4)])
            # Der laufende Tag erscheint während des Handels als Zwischenstand: nur
            # übernehmen, wenn der Handel vorbei ist (Xetra schließt 17:30 Uhr).
            now = datetime.now(timezone.utc)
            today = datetime.fromtimestamp(now.timestamp() + tz, timezone.utc)
            if rows and rows[-1][0] == today.strftime("%Y-%m-%d") and (today.hour, today.minute) < (17, 45):
                rows.pop()
            return rows
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"Yahoo: {last_err}")


def alphavantage(symbol: str, key: str) -> list:
    q = urllib.parse.urlencode({"function": "TIME_SERIES_DAILY", "symbol": symbol,
                                "outputsize": "compact", "datatype": "csv", "apikey": key})
    text = get("https://www.alphavantage.co/query?" + q)
    if not text.startswith("timestamp"):
        raise RuntimeError("Alpha Vantage: " + text.strip()[:200])
    rows = []
    for rec in csv.DictReader(io.StringIO(text)):
        try:
            rows.append([rec["timestamp"], round(float(rec["close"]), 4)])
        except (KeyError, ValueError):
            continue
    return sorted(rows)


def plausible(old: dict, new: list) -> bool:
    """Neue Reihe passt zur gespeicherten, wenn die Kurse an gemeinsamen Tagen im Median < 1,5 % abweichen."""
    common = [(old[d], c) for d, c in new if d in old]
    if len(common) < 5:
        return not old  # ohne Überlappung nur akzeptieren, wenn noch nichts gespeichert ist
    return statistics.median(abs(c / o - 1) for o, c in common) < 0.015


def main() -> int:
    key = os.environ.get("ALPHAVANTAGE_KEY", "").strip()
    try:
        with open(OUT, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"series": {}}
    series = data.setdefault("series", {})
    ok, failed, av_calls = 0, [], 0
    for pid, (ysym, asym) in SYMBOLS.items():
        old = {d: c for d, c in series.get(pid, [])}
        rows, src = None, None
        try:
            r = yahoo(ysym, "1mo" if old else "6mo")
            if r and plausible(old, r):
                rows, src = r, "Yahoo"
            elif r:
                print(f"{ysym}: Yahoo-Kurse passen nicht zu den gespeicherten – verworfen")
        except Exception as e:  # noqa: BLE001
            print(f"{ysym}: {e}")
        if rows is None and key:
            try:
                if av_calls:
                    time.sleep(3)  # kostenloser Key: höchstens 1 Abfrage pro Sekunde
                av_calls += 1
                rows, src = alphavantage(asym, key), "Alpha Vantage"
            except Exception as e:  # noqa: BLE001
                print(f"{asym}: {e}")
        if not rows:
            failed.append(pid)
            continue
        old.update({d: c for d, c in rows})
        series[pid] = [list(x) for x in sorted(old.items())[-KEEP_DAYS:]]
        ok += 1
        print(f"{pid}: {src}, letzter Kurs {rows[-1][0]} = {rows[-1][1]}")
        time.sleep(0.5)
    data["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["failed"] = failed
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{ok} von {len(SYMBOLS)} aktualisiert, Alpha-Vantage-Abfragen: {av_calls}.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
