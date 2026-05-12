use serde_json::Value;
use std::collections::HashMap;
use std::fs;
use std::time::Instant;
use swgoh_toolkit_lib::models::{
    GuildRosters, OpsDefinitions, PlannerSettings, PlatoonRequirement, SimplifiedRosterUnit,
};
use swgoh_toolkit_lib::planner;

const APP_STATE_PATH: &str =
    "C:\\Users\\brent\\AppData\\Local\\com.swgoh-toolkit.app\\.comlink\\app_state.json";
const STATCALC_REQUEST_PATH: &str =
    "C:\\Users\\brent\\AppData\\Local\\com.swgoh-toolkit.app\\.comlink\\statcalc_request.json";
const UNIT_NAMES_PATH: &str =
    "C:\\Users\\brent\\AppData\\Local\\com.swgoh-toolkit.app\\.comlink\\unit_names.json";
const BUNDLED_OPS_FALLBACK_PATH: &str =
    concat!(env!("CARGO_MANIFEST_DIR"), "/bundled/ops_fallback_embedded.json");

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let algorithm = args.first().cloned().unwrap_or_else(|| String::from("all"));
    let repeats = args
        .get(1)
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(1)
        .max(1);
    let batch_samples = args
        .get(2)
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(250);

    let settings = load_planner_settings(APP_STATE_PATH)?;
    let unit_names = load_unit_names(UNIT_NAMES_PATH)?;
    let rosters = load_rosters(STATCALC_REQUEST_PATH, &unit_names)?;
    let ops_defs = load_ops_definitions(BUNDLED_OPS_FALLBACK_PATH, &unit_names)?;

    println!(
        "Loaded benchmark data: {} roster profiles, {} operation planets, algorithm={}, repeats={}",
        rosters.len(),
        ops_defs.len(),
        algorithm,
        repeats,
    );

    let mut total_ms = 0.0f64;
    let mut best_stars = 0i64;
    for attempt in 0..repeats {
        let start = Instant::now();
        if algorithm == "batch" {
            let aggregate = planner::benchmark_eval_batch(
                &settings,
                &rosters,
                Some(&ops_defs),
                batch_samples,
                0xBAD5EED + attempt as u64,
            );
            let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
            total_ms += elapsed_ms;
            best_stars = aggregate;
            println!(
                "Run {}: {:.2} ms | {} genome evals | aggregate score={}",
                attempt + 1,
                elapsed_ms,
                batch_samples,
                aggregate,
            );
        } else {
            let result =
                planner::run_optimizer(&settings, &rosters, Some(&ops_defs), &algorithm, |_| {});
            let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
            total_ms += elapsed_ms;
            best_stars = result.total_stars;
            println!(
                "Run {}: {:.2} ms | best={} | selected={} | scores={}",
                attempt + 1,
                elapsed_ms,
                result.best_algorithm,
                result.total_stars,
                result
                    .algorithm_scores
                    .iter()
                    .map(|entry| format!("{}={}", entry.algorithm, entry.score))
                    .collect::<Vec<_>>()
                    .join(", "),
            );
        }
    }

    println!(
        "Average: {:.2} ms over {} run(s) | final metric={}",
        total_ms / repeats as f64,
        repeats,
        best_stars,
    );

    Ok(())
}

fn load_planner_settings(path: &str) -> Result<PlannerSettings, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("Failed to read {path}: {error}"))?;
    let value = serde_json::from_str::<Value>(&text)
        .map_err(|error| format!("Failed to parse planner settings JSON: {error}"))?;
    let settings_value = value
        .get("plannerSettings")
        .cloned()
        .ok_or_else(|| String::from("plannerSettings was missing from app_state.json"))?;
    serde_json::from_value(settings_value)
        .map_err(|error| format!("Failed to deserialize planner settings: {error}"))
}

fn load_unit_names(path: &str) -> Result<HashMap<String, String>, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("Failed to read {path}: {error}"))?;
    let raw = serde_json::from_str::<HashMap<String, String>>(&text)
        .map_err(|error| format!("Failed to parse unit names JSON: {error}"))?;
    Ok(raw
        .into_iter()
        .map(|(def_id, name)| (canonical_defid(&def_id), name))
        .collect())
}

fn load_rosters(
    path: &str,
    unit_names: &HashMap<String, String>,
) -> Result<GuildRosters, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("Failed to read {path}: {error}"))?;
    let value = serde_json::from_str::<Value>(&text)
        .map_err(|error| format!("Failed to parse statcalc request JSON: {error}"))?;
    let rosters = value
        .get("rosters")
        .and_then(Value::as_array)
        .ok_or_else(|| String::from("The statcalc request file did not contain a rosters array."))?;

    let mut out = GuildRosters::new();
    for (member_idx, roster_value) in rosters.iter().enumerate() {
        let Some(units) = roster_value.as_array() else {
            continue;
        };
        let simplified = units
            .iter()
            .filter_map(|unit| simplify_roster_unit(unit, unit_names))
            .collect::<Vec<_>>();
        if simplified.is_empty() {
            continue;
        }
        out.insert(format!("bench-member-{}", member_idx + 1), simplified);
    }
    Ok(out)
}

fn simplify_roster_unit(
    value: &Value,
    unit_names: &HashMap<String, String>,
) -> Option<SimplifiedRosterUnit> {
    let def_id = canonical_defid(first_string(value, &["definitionId"])?);
    if def_id.is_empty() {
        return None;
    }

    let name = unit_names
        .get(&def_id)
        .cloned()
        .unwrap_or_else(|| def_id.clone());
    let relic = value
        .get("relic")
        .and_then(|entry| entry.get("currentTier"))
        .and_then(Value::as_i64)
        .unwrap_or(0);
    let combat_type = if def_id.starts_with("CAPITAL")
        || def_id.contains("STARFIGHTER")
        || def_id.contains("SHIP")
        || def_id.contains("XWING")
        || def_id.contains("YWING")
        || def_id.contains("UWING")
        || def_id.contains("MILLENNIUMFALCON")
        || def_id.contains("TIEFIGHTER")
        || def_id.contains("BOMBER")
        || def_id.contains("INTERCEPTOR")
        || def_id.contains("ARC170")
        || def_id.contains("GAUNTLET")
        || def_id.contains("RAVENSCLAW")
    {
        2
    } else {
        1
    };

    Some(SimplifiedRosterUnit {
        def_id,
        name,
        rarity: value.get("currentRarity").and_then(Value::as_i64).unwrap_or(0),
        gear: value.get("currentTier").and_then(Value::as_i64).unwrap_or(0),
        relic,
        combat_type,
        mods_present: value
            .get("equippedStatMod")
            .and_then(Value::as_array)
            .map(|entries| !entries.is_empty())
            .unwrap_or(false),
        speed: 0,
        power: 0,
        zetas: 0,
        omicrons: 0,
        skills: Vec::new(),
    })
}

fn load_ops_definitions(
    path: &str,
    unit_names: &HashMap<String, String>,
) -> Result<OpsDefinitions, String> {
    let json_text =
        fs::read_to_string(path).map_err(|error| format!("Failed to read {path}: {error}"))?;
    let names = serde_json::from_str::<HashMap<String, Vec<Vec<String>>>>(&json_text)
        .map_err(|error| format!("Failed to parse bundled ops JSON: {error}"))?;

    let mut defs = OpsDefinitions::new();
    for (planet_id, platoons) in names {
        let min_relic = zone_relic_by_planet(&planet_id);
        let converted = platoons
            .into_iter()
            .map(|slots| {
                slots
                    .into_iter()
                    .map(|name| {
                        let def_id = find_def_id_by_name(&name, unit_names)
                            .unwrap_or_else(|| name.clone());
                        PlatoonRequirement {
                            def_id,
                            name,
                            min_rarity: 7,
                            min_relic,
                        }
                    })
                    .collect::<Vec<_>>()
            })
            .collect::<Vec<_>>();
        defs.insert(planet_id, converted);
    }
    Ok(defs)
}

fn find_def_id_by_name(name: &str, unit_names: &HashMap<String, String>) -> Option<String> {
    let target = normalize_name(name);
    unit_names.iter().find_map(|(def_id, unit_name)| {
        if normalize_name(unit_name) == target {
            Some(def_id.clone())
        } else {
            None
        }
    })
}

fn zone_relic_by_planet(planet_id: &str) -> i64 {
    match planet_id {
        "mustafar" | "corellia" | "coruscant" => 5,
        "geonosis" | "felucia" | "bracca" => 6,
        "dathomir" | "tatooine" | "kashyyyk" | "zeffo" => 7,
        "medstation" | "kessel" | "lothal" | "mandalore" => 8,
        "malachor" | "vandor" | "kafrene" | "deathstar" | "hoth" | "scarif" => 9,
        _ => 7,
    }
}

fn first_string<'a>(value: &'a Value, path: &[&str]) -> Option<&'a str> {
    let mut cursor = value;
    for segment in path {
        cursor = cursor.get(*segment)?;
    }
    cursor.as_str()
}

fn canonical_defid(value: &str) -> String {
    value.split(':').next().unwrap_or_default().trim().to_string()
}

fn normalize_name(value: &str) -> String {
    let mut out = String::new();
    for ch in value.chars() {
        if ch == '&' {
            out.push_str("and");
            continue;
        }
        if ch.is_alphanumeric() {
            for lower in ch.to_lowercase() {
                out.push(lower);
            }
        }
    }
    out
}
