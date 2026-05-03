# SWGOH ROTE Planner

Rise of the Empire Territory Battle planner for Star Wars: Galaxy of Heroes.

## Included Files

- `rote_planner.py`
- `rote_ops_fallback.py`
- `ROTE_Planner.spec`
- `ROTE_TB_PLANNER_PROJECT_STATE.txt`
- `ROTE_manual_mission_confirmations_2026-05-01.md`
- `requirements.txt`
- `build_command.txt`

## What This App Does

- Launches a local web app for planning Rise of the Empire Territory Battles
- Uses `swgoh-comlink` for live guild import and roster scanning
- Uses bundled wiki-based Operations definitions for ROTE platoons
- Uses the manually confirmed mission-definition reference to keep guide and planner mission data aligned
- Exports day-by-day plans and Operations into print-friendly PDF views
- Supports full-plan overview exports with compact daily estimation summaries
- Supports detailed or condensed Operations export layouts for sharing
- Saves and loads full planning snapshots, including rosters, optimizer output, and Operations assignments
- Supports building a standalone Windows `.exe` with PyInstaller

## Requirements

- Windows
- Python 3.14 recommended
- Internet access for first-run `swgoh-comlink` download

## Run From Source

```powershell
python rote_planner.py
```

## Build EXE

```powershell
python -m pip install -r requirements.txt
python -m PyInstaller --onefile --name ROTE_Planner rote_planner.py
```

The built executable will be created in:

```text
dist\ROTE_Planner.exe
```

## Runtime Notes

- The app downloads `swgoh-comlink` automatically into a local `.comlink` folder on first run.
- `ROTE_manual_mission_confirmations_2026-05-01.md` is the current manual reference for confirmed mission structure and requirements.
- Operations assignments appear after fetching a guild, scanning rosters, and running the optimizer.
- The Operations view includes missing-unit shortfall summaries for impossible platoons and planet-level blockers.
- PDF export supports one combined document or separate day-by-day export windows.
- Full-plan PDF export includes a day-at-a-glance overview section at the top.
- Operations PDF export can be printed in detailed or condensed mode.
- Planning snapshots can restore guild summary, scanned rosters, optimizer output, and Operations state.
- Roster scans and generated plan results are treated as session data and are not restored as live data on next launch.
- The app writes startup logs to `rote_planner_startup.log` beside the executable or script.

## GitHub Notes

Recommended files to commit:

- all files in this folder

Recommended files not to commit:

- `.comlink/`
- `build/`
- `dist/`
- `__pycache__/`
- `rote_planner_startup.log`
