import json
import os
import sys

try:
    from swgoh_comlink import GameDataBuilder, StatCalc, SwgohComlink
except Exception as exc:
    sys.stdout.write(
        json.dumps(
            {
                "ok": False,
                "error": f"Could not import swgoh_comlink: {exc}",
                "results": [],
            }
        )
    )
    raise SystemExit(0)


def extract_power(unit):
    if not isinstance(unit, dict):
        return 0
    for key in ("gp", "power", "galacticPower", "unitPower"):
        value = unit.get(key)
        if value in (None, ""):
            continue
        try:
            power = int(value)
        except Exception:
            try:
                power = int(float(str(value).strip()))
            except Exception:
                power = 0
        if power > 0:
            return power
    return 0


def load_calc(cache_path, comlink_url):
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as handle:
                return StatCalc(game_data=json.load(handle))
        except Exception:
            pass

    if comlink_url:
        try:
            with SwgohComlink(url=comlink_url) as comlink:
                game_data = GameDataBuilder(comlink).build()
            if cache_path:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as handle:
                    json.dump(game_data, handle)
            return StatCalc(game_data=game_data)
        except Exception:
            pass

    return StatCalc()


def main():
    if len(sys.argv) < 2:
        sys.stdout.write(
            json.dumps(
                {
                    "ok": False,
                    "error": "Missing request file path.",
                    "results": [],
                }
            )
        )
        return

    try:
        with open(sys.argv[1], "r", encoding="utf-8-sig") as handle:
            request = json.load(handle)
    except Exception as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Could not load request payload: {exc}",
                    "results": [],
                }
            )
        )
        return

    try:
        calc = load_calc(request.get("cachePath", ""), request.get("comlinkUrl", ""))
    except Exception as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Could not initialize StatCalc: {exc}",
                    "results": [],
                }
            )
        )
        return

    results = []
    for roster in request.get("rosters", []):
        error = ""
        if not isinstance(roster, list):
            results.append({"powers": [], "error": "Roster payload was not a list."})
            continue
        try:
            calc.calc_roster_stats(roster)
        except Exception as exc:
            error = str(exc)

        powers = [extract_power(unit) for unit in roster]
        if not error and roster and not any(power > 0 for power in powers):
            error = "StatCalc completed but did not produce any unit GP values."
        results.append({"powers": powers, "error": error})

    sys.stdout.write(json.dumps({"ok": True, "error": "", "results": results}))


if __name__ == "__main__":
    main()
