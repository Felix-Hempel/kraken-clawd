# kraken-clawd

Die Claude-Code-Figur in Lila auf dem LCD der NZXT Kraken 2023. Reagiert über Claude-Code-Hooks auf alle lokalen Sessions.

- Spec: `docs/superpowers/specs/2026-10-15-kraken-clawd-design.md`
- Daemon: `systemctl --user {status,restart,stop} kraken-clawd` (Stop → Eclipse-Bild über `~/.config/rgb-aurora/kraken.sh`)
- Hooks: `node install-hooks.mjs` / `node install-hooks.mjs --remove` (Backup: `~/.claude/settings.json.bak-kraken-clawd`)
- Vorschau ohne LCD: `uv run python -m kraken_clawd.preview`
- Eine Animation am LCD testen: `uv run python -m kraken_clawd.try_lcd <name> <sekunden>` (Daemon vorher stoppen)
- Alle Zustände durchspielen: `./demo.sh`
- Tests: `uv run pytest`
- `liquidctl` ist auf 1.16.0 gepinnt (private Methode `_send_2023_data_fw2`); beim Update Fast-Path prüfen.
