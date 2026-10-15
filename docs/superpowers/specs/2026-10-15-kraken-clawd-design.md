# kraken-clawd — Design

Stand: 2026-10-15 · Status: Spec zur Review

## Ziel

Auf dem LCD der NZXT Kraken 2023 (240×240, felixlinux) läuft die echte Claude-Code-Figur („Clawd“), recolored in Lila passend zum Aurora-Desktop. Sie bewegt sich ständig leicht und reagiert live auf die Claude-Code-Sessions auf diesem PC: arbeitet, wartet auf Felix, fertig, Fehler, Rate-Limit, Subagents, mehrere Sessions.

**Erfolgskriterien**

- Die Figur ist auf Anhieb als Claude-Code-Maskottchen erkennbar, nur in Lila.
- Animation läuft flüssig (≥ 12 fps) ohne sichtbares Flackern/Tearing.
- Zustandswechsel erscheinen < 1 s nach dem auslösenden Hook.
- Wartet irgendeine Session auf Felix, ist das sofort sichtbar.
- Daemon aus → Eclipse-Bild ist wieder da. Daemon kaputt → Claude Code merkt nichts.

**Nicht-Ziele (YAGNI)**

- Kein Windows / NZXT CAM.
- Kein Abo-Status pro Account vom Server-Gateway (es gibt dort keinen passenden Endpoint ohne Login). Limits werden lokal über `StopFailure` erkannt. Erst nachrüsten, wenn es fehlt.
- Keine Weitergabe/Veröffentlichung (Clawd ist Anthropic-Branding; privater Nachbau).

## Rahmenbedingungen (gemessen)

- Kraken 2023 `1e71:300e`, Firmware 2.0.0 → keine GIFs, nur statische Bilder.
- liquidctl 1.16.0 (Python-API). Spike 2026-10-15:
  - `set_screen('lcd','static', png)`: ~9,7 fps (fragt vor jedem Bild LCD-Info ab).
  - `_send_2023_data_fw2(rgb16, header)` mit vorberechneten Daten: ~37 fps.
- udev-Regel `/etc/udev/rules.d/71-nzxt-kraken.rules` existiert (Zugriff ohne root).
- Bestehend: `~/.config/rgb-aurora/kraken.sh` setzt `kraken-eclipse.png` (statisch).

## Architektur

```
Claude Code (alle Sessions)
   │ hooks: type "http", POST http://127.0.0.1:7377/hook
   ▼
clawd-lcd daemon (systemd --user, Python 3.13, uv)
   ├─ server.py  — HTTP-Server (stdlib), nimmt Hook-JSON an, antwortet sofort 200
   ├─ state.py   — Sessions nach session_id, Subagent-Zähler, Prioritäten → Anzeige-Modell
   ├─ sprites.py — Clawd-Pixelraster, Palette, Frame-Folgen pro Animation
   ├─ render.py  — Frame-Komposition (Haupt-Clawd + Mini-Clawds + Badges) → 240×240
   ├─ lcd.py     — Kraken-Ausgabe: Fast-Path + Fallback, Reconnect
   └─ main.py    — Loop 15 fps: Anzeige-Modell → Animation → Frame → LCD
```

**Repo:** `~/Documents/IT/kraken-clawd`, lokales Git, direkt auf `main`. Abhängigkeiten: `liquidctl==1.16.0` (exakt gepinnt wegen privater API), `Pillow`, `pytest` (dev).

**Schnittstellen**

- `state.Store.apply(event: dict, now: float) -> None` — verarbeitet ein Hook-Payload.
- `state.Store.view(now: float) -> View` — liefert `View(main: SessionView | None, others: list[SessionView], sleeping: bool, dimmed: bool)`; `SessionView(state: str, subagents: int, since: float)`.
- `sprites.animation(name: str) -> list[Image]` — Frames einer Animation, 240×240 RGB.
- `render.frame(view: View, t: float) -> Image` — fertiges Frame.
- `lcd.Display.show(img: Image)` / `lcd.Display.brightness(pct: int)`.

Thread-Modell: HTTP-Server in eigenem Thread, schreibt unter Lock in den `Store`; Render-Loop im Hauptthread liest `view()`.

**Performance:** Frames der Animationen werden beim Start einmal gerendert und als RGB16-Bytes gecacht (Schlüssel: Animation, Frame-Index, Variante). Nur zusammengesetzte Frames mit Overlays (Mini-Clawds, Badge) werden pro Tick neu gebaut und dann konvertiert. Ziel-CPU-Last < 3 % eines Kerns.

## Figur & Palette

- Clawd wird als Pixelraster im Code definiert (Raster ca. 16×12, Integer-Skalierung auf ~150 px Breite, nearest-neighbor, keine Glättung).
- Vorlage: Welcome-Mascot der Claude-Code-CLI; Abgleich mit Felix' Stream-Deck-Icon. Bewegungsideen aus clawd-tank (MIT) nur als visuelle Referenz, keine Assets übernommen. Assets von clawd-on-desk (All rights reserved) werden nicht verwendet.
- Palette (Startwerte, Feintuning am echten LCD): Körper `#9B6BFF`, Schatten `#6A3FD1`, Highlight `#C9B0FF`, Augen `#120A1E`, Fehler-Akzent `#D0408A`. Hintergrund: dunkler Violett-Verlauf wie `kraken_gif.py`.
- Das LCD ist rund: alle relevanten Inhalte innerhalb des Kreises (Radius 120 px), Mini-Clawds auf einem Bogen im unteren Drittel.

## Zustände

Mapping Hook-Event → Session-Zustand:

| Zustand | Auslöser | Animation (Loop, 8–12 Frames) |
|---|---|---|
| `thinking` | `UserPromptSubmit`, `PostToolUse` | blinzelt, „…“ pulsiert über dem Kopf |
| `typing` | `PreToolUse` mit tool_name Edit, Write, MultiEdit, NotebookEdit | tippt auf Mini-Tastatur |
| `reading` | `PreToolUse` mit Read, Grep, Glob, WebFetch, WebSearch | Lupe schwenkt |
| `bash` | `PreToolUse` mit Bash | Hammer klopft |
| `conducting` | `PreToolUse` mit Agent, Task | dirigiert mit Taktstock |
| `working` | `PreToolUse` mit anderem tool_name (z. B. MCP) | wippt geschäftig |
| `waiting` | `PermissionRequest`; `Notification` mit notification_type permission_prompt / elicitation_dialog / agent_needs_input | hüpft und winkt, sanftes Pulsieren |
| `done` | `Stop` mit `stop_hook_active == false` | Jubel ~2 s, danach `idle` |
| `error` | `PostToolUseFailure` | Erschrecken + Rotviolett-Flash ~1,5 s, danach vorheriger Zustand |
| `limit` | `StopFailure` mit `error == "rate_limit"` | kippt um, liegt flach, leere Batterie — bis nächster `UserPromptSubmit` |
| `idle` | `SessionStart`, `Notification` idle_prompt, nach `done` | atmet langsam, blinzelt gelegentlich |

Global:

- `sleep`: keine Session hatte > 30 min einen Hook → Schlaf-Animation mit Zzz; nach weiteren 10 min LCD-Helligkeit 20 %. Jeder Hook weckt sofort (Helligkeit zurück auf 100 %).
- Keine Session bekannt → `sleep`.

**Priorität (Auswahl des Haupt-Clawds):** `limit` > `waiting` > `error` > (`typing`, `reading`, `bash`, `conducting`, `working`, `thinking`) > `done` > `idle`. Bei Gleichstand gewinnt die Session mit dem jüngsten Hook.

**Mehrere Sessions:** Alle anderen Sessions erscheinen — ausgenommen Sessions, die seit mehr als 10 min `idle` sind — als Mini-Clawds (ca. 1/4 Größe) unten, vereinfachter Zustand: arbeitet (wippt) / wartet (winkt, pulsiert) / idle (steht). Max. 4 Mini-Clawds, danach Text `+N`.

**Subagents:** `SubagentStart`/`SubagentStop` (Feld `agent_id`) zählen pro `session_id`. Hooks mit `agent_id` im Payload ändern nicht den Zustand der Haupt-Session (außer `waiting`). Hat der Haupt-Clawd 1–3 Subagents: entsprechend viele kleine Klone kreisen um ihn; ab 4: Badge `×N`. Zähler wird bei `Stop` der Session auf 0 gesetzt (Schutz gegen verlorene Stop-Events).

**Aufräumen:** Session entfernt bei `SessionEnd` oder nach 2 h ohne Hook.

**Extras:**

- 00:00–00:00:10 Uhr Ortszeit: Clawd trägt Schlafmütze.
- `done` nach einer Session-Arbeitsphase > 30 min (seit erstem `UserPromptSubmit` ohne zwischenzeitliches `done`): großer Jubel mit lila Konfetti, ~4 s.

## Hooks-Konfiguration

In `~/.claude/settings.json` (global) für die Events `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PermissionRequest`, `Notification`, `Stop`, `StopFailure`, `SubagentStart`, `SubagentStop`:

```json
{ "type": "http", "url": "http://127.0.0.1:7377/hook", "timeout": 1 }
```

Bestehende Hooks in der Datei bleiben unverändert; die neuen Einträge werden ergänzt. Ein Installationsskript (`install-hooks.mjs`, node) fügt sie idempotent hinzu und kann sie wieder entfernen. Vor der Änderung wird ein Backup `settings.json.bak-kraken-clawd` angelegt.

## systemd

`~/.config/systemd/user/kraken-clawd.service`:

- `ExecStart=` uv-venv-Python `-m kraken_clawd`
- `ExecStopPost=%h/.config/rgb-aurora/kraken.sh` (Eclipse-Bild zurück)
- `Restart=on-failure`, `RestartSec=5`
- `WantedBy=default.target`

## Fehlerbehandlung

- **Kraken nicht da / USB-Fehler:** `lcd.Display` reconnectet mit Backoff 1 s → 30 s; Daemon läuft weiter, Store bleibt aktuell.
- **Fast-Path fehlt** (`_send_2023_data_fw2` nicht vorhanden oder wirft beim ersten Frame): einmalige Warnung ins Journal, Fallback `set_screen('lcd','static', …)` über Temp-PNG mit 8 fps.
- **Ungültiges Hook-JSON / unbekannte Events:** ignorieren, Debug-Log, Antwort 200.
- **Bind nur `127.0.0.1`.** Port belegt → Exit mit klarer Fehlermeldung (systemd-Restart greift).

## Tests

- `state.py`: pytest, TDD. Event-Sequenzen mit injizierter Zeit → erwartete `View` (Mapping, Prioritäten, Subagent-Zähler, Timeouts, Aufräumen, `limit` bis nächster Prompt).
- `sprites.py`/`render.py`: Tests auf Größe 240×240, Modus RGB, nur Palettenfarben im Clawd-Bereich; `python -m kraken_clawd.preview` schreibt jede Animation als GIF nach `preview/` zur Sichtprüfung.
- `lcd.py`: Mock-Test für Fast-Path-Erkennung und Fallback.
- Manuell am LCD: Flackern/Tearing, Farben, Erkennbarkeit der Figur.
- `demo.sh`: curl-Sequenz durch alle Zustände (prompt → tools → subagents → permission → stop → rate_limit → sleep) gegen den laufenden Daemon.

## Umsetzungsreihenfolge

1. Clawd-Raster + Palette + Preview-GIF (Abgleich Figur mit Felix).
2. LCD-Prototyp: Idle-Animation live auf der Kraken (Sichtprüfung Flackern/Farben).
3. `state.py` (TDD).
4. `server.py` + Hook-Installer + `demo.sh`.
5. Alle Animationen.
6. Mini-Clawds, Subagent-Klone, Badges, Extras.
7. systemd-Service + Eclipse-Fallback.
