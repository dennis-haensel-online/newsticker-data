# newsticker-data

Automatischer Schlagzeilen-Ticker für die Unterrichtsseiten (BPE-Übersichtsseiten).
Eine GitHub-Action holt stündlich öffentliche RSS-Feeds und legt pro Ticker-Kennung
eine gefilterte Datei `ticker-<ID>.json` ab (ID = `KLASSE-bpeNN`, z. B.
`ticker-wg12iw-bpe06.json`), die die Moodle-Seiten beim Laden abrufen. Die Kennung
enthält die Klasse, damit `bpe06` aus verschiedenen Klassen/Schularten nicht kollidiert.

**Hier liegt nichts Sensibles** — nur öffentliche Zeitungs-Schlagzeilen + dieses Skript.
Das Repo ist bewusst öffentlich (nur so sind die Action-Minuten unbegrenzt frei und die
JSON per CDN abrufbar).

## Dateien

| Datei | Zweck |
|---|---|
| `feeds.txt` | Quellenliste: `label \| feed-url \| paywall(0/1)` |
| `ticker-config.json` | pro BPE: Stichwörter + Negativliste + max. Anzahl |
| `fetch_ticker.py` | holt die Feeds, schreibt `ticker-bpe*.json` (+ `_cache.json`) |
| `.github/workflows/ticker.yml` | Zeitplan-Job (stündlich) — **muss** unter diesem Pfad liegen |
| `ticker-*.json` | erzeugte Ausgabe je Kennung (von der Action geschrieben), z. B. `ticker-wg12iw-bpe06.json` |
| `_cache.json` | mitwachsender 60-Tage-Cache (von der Action gepflegt) |

## Eine neue BPE anschließen (3 Schritte)

**1. Keywords** — in `ticker-config.json` (im quarto-Repo `_assets/newsticker-github/`, dann hierher
hochladen) einen Block je **Ticker-Kennung `KLASSE-bpeNN`** ergänzen (deutsche Keywords — die Feeds
sind deutsch). Die Klasse ist der Ordner über dem `bpe-…`-Ordner:

```json
"wg12iw-bpe18": {
  "keywords": ["preisbildung", "wettbewerb", "kartell", "monopol", "inflation"],
  "negative": ["monopoly", "brettspiel"],
  "max": 100
}
```

**Suchbegriffe verknüpfen (OR / AND / NOT):**

| Feld | Verknüpfung | Wirkung |
|---|---|---|
| `keywords` | **OR** | **ein** Treffer genügt, damit die Meldung aufgenommen wird |
| `require` | **AND** (optional) | Meldung zählt nur, wenn sie **zusätzlich** zu einem `keywords`-Treffer **einen** `require`-Begriff enthält |
| `negative` | **NOT** | **ein** Treffer schließt die Meldung aus |
| Leerzeichen im Begriff | **Phrase** | `"angebot und nachfrage"` matcht nur die exakte Wortfolge |

`require` ist der stärkste Präzisionshebel für **breit streuende Pools** (allgemeiner Nachrichten-Topf):
Das Thema-Keyword darf breit bleiben, der Pflicht-Kontext erzwingt den fachlichen Bezug. Fehlt `require`,
verhält sich der Filter wie bisher (reine OR-Liste). Beispiel:

```json
"ik": {
  "keywords": ["diversität", "migration", "integration", "vielfalt"],
  "require":  ["arbeitsmarkt", "unternehmen", "wirtschaft", "fachkräfte", "betrieb", "gesellschaft"],
  "negative": ["artenvielfalt", "biodiversität"],
  "max": 100
}
```
→ „Diversität im DAX-Vorstand" bleibt, „Diversität der Käferarten" fällt raus.

**Matching-Mechanik (gilt für alle drei Felder):** Begriffe mit **≤ 4 Zeichen** (`ki`, `bip`, `zoll`)
matchen **wortgenau** (kein Wortinneres — `zoll` trifft „Zoll", nicht „Zollstock"); **längere** Begriffe
binden am **Wortanfang** und fangen so Flexion/Komposita (`inflation` → „Inflationsrate",
`standort` → „Standortverlagerung"). Durchsucht werden **Titel + Kurzzusammenfassung**.

**2. Pre-Render** — in der `_quarto.yml` der BPE unter `pre-render:` ergänzen:

```yaml
    - ../../../../_assets/newsticker.py --emit-project
```

**3. Include** — in der `index.qmd` der BPE an passender Stelle:

```
{{< include _ticker.qmd >}}
```

Danach die geänderte `ticker-config.json` **hierher ins GitHub-Repo hochladen** → die Action legt
`ticker-<ID>.json` an. Die Kennung `KLASSE-bpeNN` wird aus dem **Pfad** abgeleitet: Klasse = Ordner
über dem `bpe-…`-Ordner, BPE-Nummer aus dem Ordnernamen (`…/wg12iw/bpe-18-…` → `wg12iw-bpe18`),
die Sprache aus `lang:` der index.qmd — sonst nichts einzustellen. Der Config-Schlüssel **muss exakt
dieser Kennung entsprechen**, sonst bleibt der Live-Layer leer (der gebackene Fallback greift dennoch).

**Tipp Keyword-Wahl:** kurze/mehrdeutige Begriffe (`preis` matcht auch „Preisträger", weil > 4 Zeichen →
Wortanfang-Bindung) meiden bzw. über `negative` abfangen; lieber prägnante Komposita (`preisbildung`,
`energiepreise`) — oder einen `require`-Pflichtkontext setzen (s. o.). Abstrakte Grundlagen-Themen
(z. B. BPE 1) matchen dünn — Ticker dort optional.

## Hochladen / Sync (alle BPE in einem Aufwasch)

**Alle BPEs stecken in der EINEN `ticker-config.json`** — es gibt keinen Pro-BPE-Upload.
Beim Push baut die Action aus dieser Config automatisch jede `ticker-<ID>.json` neu. Der
bequeme Weg aus dem quarto-Repo (Skript rekonstruiert den Push aus den Quellen, unabhängig
von irgendeinem Arbeitsordner):

```
python _assets/push-data-repos.py --repo ticker        # nur den Ticker
python _assets/push-data-repos.py                      # Ticker + Stats
python _assets/push-data-repos.py --repo ticker --dry  # nur zeigen, was sich ändert
```

Das Skript klont das Repo frisch, kopiert `ticker-config.json` / `feeds.txt` / `fetch_ticker.py`
(LF-normalisiert) + `ticker-workflow.yml` → `.github/workflows/ticker.yml`, committet **nur bei
echter Änderung** und pusht. **Der erste Push öffnet einmalig das GitHub-Login** (Credential
Manager) — danach ist der Zugang gecacht.

**Erstaufbau eines noch nicht existierenden Repos:** auf github.com ein **öffentliches** Repo
anlegen (New repository → Name wie im Slug → Public → ohne README), dann das Skript laufen
lassen; danach im Repo **Settings → Actions → General → Workflow permissions → „Read and write
permissions"** setzen (sonst darf der Bot die JSON nicht zurückschreiben).

Von Hand ginge es genauso: Repo klonen, die vier Dateien hineinkopieren (die `.yml` nach
`.github/workflows/ticker.yml`), committen, `git push`.

## Andere Quellen für eine BPE

Standardmäßig filtern alle BPEs aus demselben Quellentopf (`feeds.txt`). Sollen für eine
BPE andere Quellen gelten (z. B. Tech-Feeds für Informatik), einfach die gewünschten
Feeds in `feeds.txt` ergänzen — der Keyword-Filter je BPE sorgt dann für die Trennung.

## Läuft der Job nicht?

- **Reiter „Actions"** zeigt jeden Lauf (grün = ok, rot = Fehler mit Log).
- Committet der Job nichts? → `Settings → Actions → General → Workflow permissions`
  auf **„Read and write permissions"** stellen.
- Ein Feed liefert Fehler? → Log ansehen, betroffene Zeile in `feeds.txt` korrigieren
  oder auskommentieren (`#` davor).
