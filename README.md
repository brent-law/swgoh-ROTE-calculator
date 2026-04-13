# SWGOH ROTE Planner

Rise of the Empire Territory Battle planner for Star Wars: Galaxy of Heroes.

## Included Files

- `rote_planner.py`
- `rote_ops_fallback.py`
- `ROTE_Planner.spec`
- `ROTE_TB_PLANNER_PROJECT_STATE.txt`
- `requirements.txt`
- `build_command.txt`

## What This App Does

- Launches a local web app for planning Rise of the Empire Territory Battles
- Uses `swgoh-comlink` for live guild import and roster scanning
- Falls back to bundled wiki-based Operations definitions for ROTE platoons
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

Install PyInstaller:

```powershell
python -m pip install -r requirements.txt
```

Build the executable:

```powershell
python -m PyInstaller --onefile --name ROTE_Planner rote_planner.py
```

The built executable will be created in:

```text
dist\ROTE_Planner.exe
```

## Runtime Notes

- The app downloads `swgoh-comlink` automatically into a local `.comlink` folder on first run.
- Operations assignments only appear after:
  1. fetching a guild
  2. scanning rosters
  3. running the day-by-day optimizer at least once
- The app writes startup logs to `rote_planner_startup.log` in the same folder as the executable or script.

## GitHub Notes

Recommended files to commit:

- all files in this folder

Recommended files not to commit:

- `.comlink/`
- `build/`
- `dist/`
- `__pycache__/`
- `rote_planner_startup.log`
