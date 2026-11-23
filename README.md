# Depot-Monitor

Private Depot-Übersicht als Web-App (GitHub Pages).

- **Kurse:** `.github/workflows/update.yml` holt werktags nach Xetra-Schluss die Tagesschlusskurse von Alpha Vantage
  (`scripts/fetch_prices.py`) und speichert sie in `data/prices.json`. Benötigt das Repository-Secret `ALPHAVANTAGE_KEY`.
- **Entwicklungen:** `data/news.json` (wird von Claude aktualisiert).
- **Bestand:** liegt **nicht** im Repository, sondern nur im persönlichen Link (Teil hinter `#d=`) und im Browser des Geräts.
  Ändern über die Schaltfläche „Bestand“ in der App.

Manuell aktualisieren: Actions → „Kurse aktualisieren und veröffentlichen“ → Run workflow.
