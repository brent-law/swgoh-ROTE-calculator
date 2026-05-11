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


def canonical_defid(value):
    return str(value or "").split(":")[0].strip()


def coerce_int(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(float(str(value).strip()))
    except Exception:
        return default


def normalized_skills(unit):
    out = []
    for skill in (unit.get("skill") or unit.get("skills") or []):
        if not isinstance(skill, dict):
            continue
        skill_id = str(skill.get("id") or skill.get("skillId") or skill.get("abilityId") or "").strip()
        if not skill_id:
            continue
        out.append({
            "id": skill_id,
            "tier": coerce_int(skill.get("tier"), 0) + 2,
        })
    return out


def normalized_char(unit):
    return {
        "defId": canonical_defid(unit.get("definitionId") or unit.get("defId") or unit.get("baseId")),
        "rarity": coerce_int(unit.get("currentRarity") or unit.get("rarity"), 0),
        "level": coerce_int(unit.get("currentLevel") or unit.get("level"), 0),
        "gear": coerce_int(unit.get("currentTier") or unit.get("gear"), 0),
        "equipped": unit.get("equipment") or unit.get("equipped") or [],
        "equippedStatMod": unit.get("equippedStatMod"),
        "mods": unit.get("mods"),
        "relic": unit.get("relic"),
        "skills": normalized_skills(unit),
        "purchasedAbilityId": list(unit.get("purchasedAbilityId") or []),
    }


def is_character_unit(unit):
    if not isinstance(unit, dict):
        return False
    combat_type = unit.get("combatType") or unit.get("type")
    try:
        if combat_type is not None:
            return int(combat_type) != 2
    except Exception:
        pass
    if unit.get("equippedStatMod") is not None or unit.get("mods") is not None:
        return True
    if unit.get("relic") is not None:
        return True
    if unit.get("currentTier") is not None or unit.get("gear") is not None:
        return True
    if unit.get("equipment") is not None or unit.get("equipped") is not None:
        return True
    return False


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
        errors = []
        if not isinstance(roster, list):
            results.append({"powers": [], "error": "Roster payload was not a list."})
            continue
        try:
            calc.calc_roster_stats(roster)
        except Exception as exc:
            errors.append(str(exc))

        powers = []
        for unit in roster:
            if not isinstance(unit, dict):
                powers.append(0)
                continue
            if is_character_unit(unit):
                try:
                    powers.append(calc.calc_char_gp(normalized_char(unit)))
                    continue
                except Exception as exc:
                    errors.append(str(exc))
            powers.append(extract_power(unit))

        if not errors and roster and not any(power > 0 for power in powers):
            errors.append("StatCalc completed but did not produce any unit GP values.")
        results.append({"powers": powers, "error": "; ".join(entry for entry in errors if entry)[:1000]})

    sys.stdout.write(json.dumps({"ok": True, "error": "", "results": results}))


if __name__ == "__main__":
    main()
