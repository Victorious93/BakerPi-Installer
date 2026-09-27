# BakerPi Tool Installer — orientation and phase tracker

No `CLAUDE.md`/`CODEX.md` existed before this file (2026-09-27). Read this
first; update it at the end of every session.

## What this repo is

A cross-platform (Linux/Windows, native app + web server) tool installer
for BakerPi, the project owner's fork of
[P4wnP1_aloa](https://github.com/Victorious93/P4wnP1_aloa) adapted for a
Raspberry Pi Zero 1.3. FastAPI + uvicorn backend (`server.py`, 543 lines),
`pywebview`-based native desktop wrapper (`launcher.py`, 186 lines), a
static PWA frontend (`static/`), and a tool catalog (`tools/catalog.json`
— `version`/`platform`/`categories` keys, 13 categories per README). SSH
mode (installs onto a Pi over the network) and local/on-device mode share
one codebase.

## Current phase

Verified 2026-09-27 by direct inspection (file contents, `.github/workflows/`,
a grep for TODO/FIXME/"not yet"/"coming soon" across `.py`/`.sh`/`.json`):

- **No open TODOs, FIXMEs, or "not yet implemented" markers found anywhere
  in the codebase.** README describes every listed feature (13 categories,
  85+ tools, native app, web/PWA modes, SSE install streaming, batch
  install/update/uninstall, VNC control for Kali/Parrot desktop variants)
  as present, not planned.
- `.github/workflows/build-installers.yml` and `release.yml` exist —
  CI build/release automation is real, not just described.
- **This reads as a complete, working v1** as of the last commit, not a
  project with visible unfinished work. That's different from "nothing
  left to do" — it just means nothing *incomplete* is visible from the
  repo alone. If there's a next milestone in mind, it isn't recorded
  anywhere in this repo yet; add it below once decided, rather than this
  file guessing at a roadmap that doesn't exist in the code or docs.

## Repo history note

Shallow clone shows one commit (`Add status filter pills, / search
shortcut, filter count`, 2026-08-09) — the true history is longer than
this depth-1 view; fetch deeper if session-by-session history matters.
No activity since 2026-08-09 (idle ~7 weeks as of this writing), unlike
the project owner's other active repos.

## What to do next

Nothing is queued in the repo itself. Before starting new work here:
1. Decide and record the next milestone (a 14th tool category? Android
   APK parity work in the linked `P4wnP1_aloa` fork? something else?) —
   there's no existing roadmap doc to defer to, so state it explicitly
   here once chosen, per the project owner's standing phase-tracking rule.
2. If picking this back up cold, first verify `pip3 install -r
   requirements.txt` and both run modes (`run_pc.sh` / `run_ondevice.sh`)
   still work — nothing here confirms the last-committed state was
   actually tested against a real Pi Zero device.

## Source of truth

When this file and the code disagree, the code wins — update this file,
don't trust it uncritically.
