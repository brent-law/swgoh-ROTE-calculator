use crate::error::{CommandError, CommandResult};
use crate::models::{
    BootstrapResponse, BulkRosterScanResponse, BulkScanGuildRostersRequest, ComlinkStatusResponse,
    ExportPreviewDocument, ExportPreviewResponse, ExportPreviewTokenRequest, GuildImportRequest,
    GuildImportResponse, GuildMember, GuildRosters, GuildScanProgressEvent, GuildSummary,
    GuideTbOmicron, GuideTbOmicronMap, GuideTbOmicronResponse, GuideUnitCatalogEntry,
    GuideUnitCatalogResponse, ImportSessionRequest, ImportSessionResponse, LoadAppStateResponse,
    OpenExportPreviewRequest, OpenExportPreviewResponse, OpsDefinitions, OpsDefinitionsResponse,
    PlannerOptimizationProgressEvent, PlannerOptimizationRequest, PlannerOptimizationResponse,
    PlannerProjectionRequest, PlannerProjectionResponse, PlannerReferenceResponse,
    PlatoonAnalysisEntry, PlatoonAnalysisMap, PlatoonAnalysisResponse, PlatoonRequirement,
    PlatoonSlotAnalysis, ReleaseExportPreviewResponse, ResetScanSessionResponse,
    RosterScanResponse, SaveAppStateRequest, SaveAppStateResponse, ScanFailure,
    SessionSnapshot, SimplifiedRosterUnit, SimplifiedSkillRow, WriteExportBundleRequest,
    WriteExportBundleResponse,
};
use crate::planner;
use base64::engine::general_purpose::STANDARD as BASE64_STANDARD;
use base64::Engine;
use flate2::read::{GzDecoder, ZlibDecoder};
use serde_json::{json, Map, Value};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::io::{BufRead, BufReader, Cursor, Read};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{
    atomic::{AtomicU64, Ordering},
    OnceLock,
};
use std::thread;
use std::time::Duration;
use tar::Archive;
use tauri::{AppHandle, Emitter, Manager};
use tokio::sync::Mutex;
use zip::ZipArchive;

const COMLINK_PORT: u16 = 3000;
const APP_NAME: &str = "rote-tb-planner";
const SCAN_REQ_DELAY_MS: u64 = 100;
const SCAN_MAX_IN_FLIGHT: usize = 12;
const SCAN_RETRY_DELAY_MS: u64 = 2000;
const SCAN_MAX_ATTEMPTS: usize = 3;
const SCAN_RECOVERY_THRESHOLD: usize = 3;
const SCAN_RECOVERY_ATTEMPTS: usize = 12;
const SCAN_RECOVERY_WAIT_MS: u64 = 3000;
const SCAN_FETCH_TIMEOUT_SECONDS: u64 = 10;
const COMLINK_RELEASE_API: &str =
    "https://api.github.com/repos/swgoh-utils/swgoh-comlink/releases/latest";
const GUILD_SCAN_PROGRESS_EVENT: &str = "guild-scan-progress";
const PLANNER_OPTIMIZATION_PROGRESS_EVENT: &str = "planner-optimization-progress";
const LEGACY_OPS_FALLBACK: &str = include_str!("../../old code base/rote_ops_fallback.py");
const LEGACY_PLANNER_SOURCE: &str = include_str!("../../old code base/rote_planner.py");
const STATCALC_BRIDGE_SOURCE: &str = include_str!("../python/statcalc_bridge.py");
static COMLINK_HTTP_CLIENT: OnceLock<reqwest::Client> = OnceLock::new();
static LEGACY_UNIT_DATA: OnceLock<LegacyUnitData> = OnceLock::new();
static EXPORT_PREVIEW_COUNTER: AtomicU64 = AtomicU64::new(1);

struct GuildScanTaskResult {
    key: String,
    display_name: String,
    result: CommandResult<Value>,
}

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct StatCalcBridgeRequest {
    cache_path: String,
    comlink_url: String,
    rosters: Vec<Vec<Value>>,
}

#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
struct StatCalcBridgeRosterResult {
    powers: Vec<i64>,
    error: String,
}

#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
struct StatCalcBridgeResponse {
    ok: bool,
    error: String,
    results: Vec<StatCalcBridgeRosterResult>,
}

#[derive(Debug, Default)]
struct LegacyUnitData {
    playable_names: HashMap<String, String>,
    alias_by_name: HashMap<String, String>,
    ship_defid_keys: HashSet<String>,
    character_defid_keys: HashSet<String>,
    name_index: HashMap<String, Vec<String>>,
}

const UNIT_NAMES_CACHE_FILE: &str = "unit_names.json";
const ABILITY_NAMES_CACHE_FILE: &str = "ability_names.json";
const SKILL_META_CACHE_FILE: &str = "skill_meta.json";
const UNIT_SKILL_REFS_CACHE_FILE: &str = "unit_skill_refs.json";
const UNIT_CREW_MAP_CACHE_FILE: &str = "unit_crew_map.json";
const UNIT_CREW_SKILL_REFS_CACHE_FILE: &str = "unit_crew_skill_refs.json";
const SCAN_LOG_FILE: &str = "scan_log.json";
const APP_STATE_FILE: &str = "app_state.json";
const STATCALC_BRIDGE_FILE: &str = "statcalc_bridge.py";
const STATCALC_REQUEST_FILE: &str = "statcalc_request.json";
const STATCALC_GAMEDATA_CACHE_FILE: &str = "statcalc_game_data.json";
const VOLATILE_APP_STATE_KEYS: &[&str] = &[
    "guildSummary",
    "guildRosters",
    "lastPlanResult",
    "lastPlanStars",
    "platoonAnalysis",
    "selectedGuideMember",
    "selectedRosterMember",
];

#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
struct SkillMeta {
    max_tier: i64,
    is_zeta: bool,
    is_omicron: bool,
    omicron_area: i64,
    kind: String,
    zeta_tiers: Vec<i64>,
    omicron_tiers: Vec<i64>,
}

#[derive(Debug, Default)]
struct BackendRuntime {
    guild_summary: Option<GuildSummary>,
    guild_rosters: GuildRosters,
    unit_name_map: HashMap<String, String>,
    ability_name_map: HashMap<String, String>,
    localization_value_map: HashMap<String, String>,
    skill_meta_map: HashMap<String, SkillMeta>,
    unit_skill_reference_map: HashMap<String, Vec<String>>,
    unit_crew_map: HashMap<String, Vec<String>>,
    unit_crew_skill_reference_map: HashMap<String, Vec<String>>,
    known_ship_defids: HashSet<String>,
    known_character_defids: HashSet<String>,
    ops_defs_cache: Option<OpsDefinitions>,
    guide_tb_omicron_cache: Option<GuideTbOmicronMap>,
    export_previews: HashMap<String, ExportPreviewSession>,
    comlink_binary: Option<PathBuf>,
    comlink_child: Option<Child>,
    localization_warmup_running: bool,
}

#[derive(Debug, Clone, Default)]
struct ExportPreviewSession {
    title: String,
    initial_document_id: String,
    documents: Vec<ExportPreviewDocument>,
}

#[derive(Default)]
pub struct BackendState {
    runtime: Mutex<BackendRuntime>,
}

pub async fn get_bootstrap_state(app_handle: AppHandle) -> CommandResult<BootstrapResponse> {
    let app_state = load_app_state_from_disk(&app_handle)?;
    let comlink_status = refresh_comlink_status_internal(&app_handle).await?;

    let state = app_handle.state::<BackendState>();
    let runtime = state.runtime.lock().await;
    let session = SessionSnapshot {
        guild_summary: runtime.guild_summary.clone(),
        guild_rosters: runtime.guild_rosters.clone(),
        ops_source: runtime
            .ops_defs_cache
            .as_ref()
            .map(|_| String::from("bundled-wiki")),
    };
    drop(runtime);

    let response = BootstrapResponse {
        app_state,
        comlink_status,
        session,
    };

    if response.comlink_status.comlink == "online" {
        schedule_localization_warmup(app_handle);
    }

    Ok(response)
}

pub async fn refresh_comlink_status(app_handle: AppHandle) -> CommandResult<ComlinkStatusResponse> {
    let response = refresh_comlink_status_internal(&app_handle).await?;
    if response.comlink == "online" {
        schedule_localization_warmup(app_handle);
    }
    Ok(response)
}

pub async fn start_comlink(app_handle: AppHandle) -> CommandResult<ComlinkStatusResponse> {
    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;
    start_comlink_internal(&app_handle, &mut runtime).await?;
    drop(runtime);
    let response = refresh_comlink_status_internal(&app_handle).await?;
    if response.comlink == "online" {
        schedule_localization_warmup(app_handle);
    }
    Ok(response)
}

pub async fn stop_comlink(app_handle: AppHandle) -> CommandResult<ComlinkStatusResponse> {
    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;
    stop_comlink_internal(&mut runtime)?;
    drop(runtime);
    refresh_comlink_status_internal(&app_handle).await
}

pub async fn shutdown_backend(app_handle: &AppHandle) {
    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;
    let _ = stop_comlink_internal(&mut runtime);
}

pub async fn release_export_preview_window(app_handle: &AppHandle, window_label: &str) {
    let Some(token) = window_label.strip_prefix("export-preview-") else {
        return;
    };
    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;
    runtime.export_previews.remove(token);
}

fn emit_scan_progress(app_handle: &AppHandle, payload: GuildScanProgressEvent) {
    let _ = app_handle.emit(GUILD_SCAN_PROGRESS_EVENT, payload);
}

fn emit_optimizer_progress(app_handle: &AppHandle, payload: PlannerOptimizationProgressEvent) {
    let _ = app_handle.emit(PLANNER_OPTIMIZATION_PROGRESS_EVENT, payload);
}

fn schedule_localization_warmup(app_handle: AppHandle) {
    tauri::async_runtime::spawn(async move {
        let state = app_handle.state::<BackendState>();
        {
            let mut runtime = state.runtime.lock().await;
            if runtime.localization_warmup_running || localization_maps_ready(&runtime) {
                return;
            }
            runtime.localization_warmup_running = true;
        }

        {
            let state = app_handle.state::<BackendState>();
            let mut runtime = state.runtime.lock().await;
            let _ = ensure_localization_maps(&app_handle, &mut runtime).await;
            runtime.localization_warmup_running = false;
        }
    });
}

pub async fn fetch_guild_by_allycode(
    app_handle: AppHandle,
    request: GuildImportRequest,
) -> CommandResult<GuildImportResponse> {
    let normalized = normalize_ally_code_input(&request.ally_code);
    if normalized.is_empty() {
        return Err(CommandError::new("validation", "An ally code is required."));
    }

    let player = lookup_player_by_ally_code(&normalized).await?;
    let guild_id = extract_first_string(
        &player,
        &[
            &["guildId"],
            &["guild_id"],
            &["guild", "id"],
            &["player", "guild", "id"],
            &["player", "guildId"],
        ],
    )
    .ok_or_else(|| {
        CommandError::new(
            "comlink_payload",
            "Could not find a guild id in the comlink player response.",
        )
    })?;

    let guild = comlink_post(
        "guild",
        json!({
            "guildId": guild_id,
            "includeRecentGuildActivityInfo": true
        }),
        20,
    )
    .await?;
    let summary = normalize_guild_summary(&guild)?;

    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;
    runtime.guild_summary = Some(summary.clone());
    runtime.guild_rosters.clear();
    runtime.guide_tb_omicron_cache = None;
    runtime.ops_defs_cache = None;
    drop(runtime);
    schedule_localization_warmup(app_handle.clone());

    Ok(GuildImportResponse { summary })
}

pub async fn scan_roster(
    app_handle: AppHandle,
    request: crate::models::ScanRosterRequest,
) -> CommandResult<RosterScanResponse> {
    scan_roster_internal(&app_handle, &request.ally_code).await
}

pub async fn scan_guild_rosters(
    app_handle: AppHandle,
    request: BulkScanGuildRostersRequest,
) -> CommandResult<BulkRosterScanResponse> {
    {
        let state = app_handle.state::<BackendState>();
        let mut runtime = state.runtime.lock().await;
        runtime.guild_rosters.clear();
        runtime.guide_tb_omicron_cache = None;
        runtime.ops_defs_cache = None;
        ensure_localization_maps(&app_handle, &mut runtime).await?;
    }

    let mut failures = Vec::new();
    let mut seen_keys = HashSet::<String>::new();
    let mut scan_members = Vec::<(String, String)>::new();
    for member in request.members {
        let key = normalize_scan_key(&member.key);
        let display_name = member.display_name.unwrap_or_default();
        if key.is_empty() {
            failures.push(ScanFailure {
                key,
                display_name,
                error: String::from("This guild member is missing a valid roster key."),
            });
            continue;
        }
        if !seen_keys.insert(key.clone()) {
            continue;
        }
        scan_members.push((key, display_name));
    }

    let mut scanned_members = 0usize;
    let mut consecutive_failures = 0usize;
    let total_members = scan_members.len();
    let mut successful_players = Vec::<(String, Value)>::new();
    emit_scan_progress(
        &app_handle,
        GuildScanProgressEvent {
            phase: String::from("starting"),
            total_members,
            completed_members: 0,
            successful_members: 0,
            failed_members: 0,
            current_key: None,
            current_display_name: None,
            last_error: None,
        },
    );
    let (result_tx, mut result_rx) =
        tokio::sync::mpsc::unbounded_channel::<GuildScanTaskResult>();
    let mut pending_members = scan_members.into_iter();
    let mut next_member = pending_members.next();
    let mut in_flight = 0usize;
    let mut scan_stopped = false;
    let mut next_launch_at = tokio::time::Instant::now();

    while next_member.is_some() || in_flight > 0 {
        if !scan_stopped && next_member.is_some() && in_flight < SCAN_MAX_IN_FLIGHT {
            if consecutive_failures >= SCAN_RECOVERY_THRESHOLD {
                let (key, display_name) = next_member.clone().unwrap_or_default();
                emit_scan_progress(
                    &app_handle,
                    GuildScanProgressEvent {
                        phase: String::from("recovering"),
                        total_members,
                        completed_members: scanned_members + failures.len(),
                        successful_members: scanned_members,
                        failed_members: failures.len(),
                        current_key: Some(key.clone()),
                        current_display_name: if display_name.is_empty() {
                            None
                        } else {
                            Some(display_name.clone())
                        },
                        last_error: Some(String::from(
                            "swgoh-comlink stopped responding; attempting recovery.",
                        )),
                    },
                );

                if !recover_comlink_for_scan(&app_handle).await {
                    failures.push(ScanFailure {
                        key,
                        display_name,
                        error: String::from(
                            "swgoh-comlink stayed offline during recovery, so the guild scan was stopped.",
                        ),
                    });
                    scan_stopped = true;
                    next_member = None;
                    continue;
                }

                consecutive_failures = 0;
                next_launch_at = tokio::time::Instant::now();
            }

            let now = tokio::time::Instant::now();
            if now >= next_launch_at {
                let (key, display_name) = next_member.take().unwrap();
                let send_key = key.clone();
                let send_display_name = display_name.clone();
                let send_app_handle = app_handle.clone();
                let send_result_tx = result_tx.clone();
                tauri::async_runtime::spawn(async move {
                    let result = fetch_roster_player_with_retry(&send_app_handle, &send_key).await;
                    let _ = send_result_tx.send(GuildScanTaskResult {
                        key: send_key,
                        display_name: send_display_name,
                        result,
                    });
                });
                in_flight += 1;
                next_launch_at = now + Duration::from_millis(SCAN_REQ_DELAY_MS);
                next_member = pending_members.next();
                continue;
            }
        }

        if in_flight == 0 {
            if scan_stopped || next_member.is_none() {
                break;
            }
            tokio::time::sleep_until(next_launch_at).await;
            continue;
        }

        let can_launch_later = !scan_stopped && next_member.is_some() && in_flight < SCAN_MAX_IN_FLIGHT;
        let recv_result = if can_launch_later {
            let wait_duration =
                next_launch_at.saturating_duration_since(tokio::time::Instant::now());
            match tokio::time::timeout(wait_duration, result_rx.recv()).await {
                Ok(result) => result,
                Err(_) => continue,
            }
        } else {
            result_rx.recv().await
        };

        let Some(task_result) = recv_result else {
            break;
        };
        in_flight = in_flight.saturating_sub(1);

        match task_result.result {
            Ok(player) => {
                scanned_members += 1;
                consecutive_failures = 0;
                successful_players.push((task_result.key.clone(), player));
                emit_scan_progress(
                    &app_handle,
                    GuildScanProgressEvent {
                        phase: String::from("running"),
                        total_members,
                        completed_members: scanned_members + failures.len(),
                        successful_members: scanned_members,
                        failed_members: failures.len(),
                        current_key: Some(task_result.key),
                        current_display_name: if task_result.display_name.is_empty() {
                            None
                        } else {
                            Some(task_result.display_name)
                        },
                        last_error: None,
                    },
                );
            }
            Err(error) => {
                consecutive_failures += 1;
                let message = error.message;
                failures.push(ScanFailure {
                    key: task_result.key.clone(),
                    display_name: task_result.display_name.clone(),
                    error: message.clone(),
                });
                emit_scan_progress(
                    &app_handle,
                    GuildScanProgressEvent {
                        phase: String::from("running"),
                        total_members,
                        completed_members: scanned_members + failures.len(),
                        successful_members: scanned_members,
                        failed_members: failures.len(),
                        current_key: Some(task_result.key),
                        current_display_name: if task_result.display_name.is_empty() {
                            None
                        } else {
                            Some(task_result.display_name)
                        },
                        last_error: Some(message),
                    },
                );
            }
        }
    }

    emit_scan_progress(
        &app_handle,
        GuildScanProgressEvent {
            phase: String::from("calculating-power"),
            total_members,
            completed_members: scanned_members + failures.len(),
            successful_members: scanned_members,
            failed_members: failures.len(),
            current_key: None,
            current_display_name: None,
            last_error: None,
        },
    );

    let mut successful_rosters = successful_players
        .iter()
        .map(|(_, player)| player.clone())
        .collect::<Vec<_>>();
    let (power_ready, power_error) =
        try_apply_statcalc_power(&app_handle, &mut successful_rosters);

    let guild_rosters = {
        let state = app_handle.state::<BackendState>();
        let mut runtime = state.runtime.lock().await;
        runtime.guild_rosters.clear();

        for ((member_key, _), player) in successful_players
            .into_iter()
            .zip(successful_rosters.into_iter())
        {
            let (simplified, _) = simplify_player_roster(&runtime, &player);
            runtime.guild_rosters.insert(member_key, simplified);
        }

        runtime.guide_tb_omicron_cache = None;
        runtime.ops_defs_cache = None;
        runtime.guild_rosters.clone()
    };

    emit_scan_progress(
        &app_handle,
        GuildScanProgressEvent {
            phase: String::from("complete"),
            total_members,
            completed_members: scanned_members + failures.len(),
            successful_members: scanned_members,
            failed_members: failures.len(),
            current_key: None,
            current_display_name: None,
            last_error: if power_ready || power_error.is_empty() {
                None
            } else {
                Some(power_error.clone())
            },
        },
    );

    Ok(BulkRosterScanResponse {
        scanned_members,
        failed_members: failures,
        guild_rosters,
        power_ready,
        power_error,
    })
}

pub async fn load_ops_definitions(app_handle: AppHandle) -> CommandResult<OpsDefinitionsResponse> {
    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;
    ensure_localization_maps(&app_handle, &mut runtime).await?;
    let defs = load_ops_definitions_internal(&mut runtime)?;
    Ok(OpsDefinitionsResponse {
        status: String::from("ok"),
        defs,
        count: runtime.ops_defs_cache.as_ref().map_or(0, HashMap::len),
        source: String::from("bundled-wiki"),
        source_label: String::from("Bundled wiki definitions"),
    })
}

pub async fn analyze_platoons(app_handle: AppHandle) -> CommandResult<PlatoonAnalysisResponse> {
    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;
    if runtime.guild_rosters.is_empty() {
        return Err(CommandError::new(
            "validation",
            "No roster data is available yet. Run Scan Rosters first.",
        ));
    }
    ensure_localization_maps(&app_handle, &mut runtime).await?;
    let defs = load_ops_definitions_internal(&mut runtime)?;
    let analysis = analyze_platoons_internal(&runtime, &defs);
    Ok(PlatoonAnalysisResponse {
        status: String::from("ok"),
        planet_count: analysis.len(),
        roster_count: runtime.guild_rosters.len(),
        analysis,
    })
}

pub async fn get_guide_tb_omicrons(
    app_handle: AppHandle,
) -> CommandResult<GuideTbOmicronResponse> {
    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;
    ensure_localization_maps(&app_handle, &mut runtime).await?;
    let units = build_guide_tb_omicron_map(&mut runtime);
    Ok(GuideTbOmicronResponse {
        status: String::from("ok"),
        units,
        omicron_area: 7,
        area_label: String::from("Territory Battles"),
    })
}

pub async fn get_guide_unit_catalog(
    app_handle: AppHandle,
) -> CommandResult<GuideUnitCatalogResponse> {
    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;
    ensure_localization_maps(&app_handle, &mut runtime).await?;
    let units = build_guide_unit_catalog(&runtime);
    Ok(GuideUnitCatalogResponse {
        status: String::from("ok"),
        units,
    })
}

pub async fn get_planner_reference() -> CommandResult<PlannerReferenceResponse> {
    Ok(planner::planner_reference())
}

pub async fn write_export_bundle(
    app_handle: AppHandle,
    request: WriteExportBundleRequest,
) -> CommandResult<WriteExportBundleResponse> {
    let root = comlink_dir(&app_handle)?.join("exports");
    fs::create_dir_all(&root).map_err(|error| CommandError::new("path", error.to_string()))?;

    let folder_name = sanitize_export_path_segment(&request.folder_name);
    if folder_name.is_empty() {
        return Err(CommandError::new(
            "export",
            String::from("The export folder name was empty."),
        ));
    }

    let bundle_dir = root.join(folder_name);
    if bundle_dir.exists() {
        fs::remove_dir_all(&bundle_dir)
            .map_err(|error| CommandError::new("export", error.to_string()))?;
    }
    fs::create_dir_all(&bundle_dir).map_err(|error| CommandError::new("export", error.to_string()))?;

    let mut open_path = None::<PathBuf>;
    let requested_open_name = sanitize_export_file_name(&request.open_file_name);

    for file in request.files {
        let file_name = sanitize_export_file_name(&file.name);
        if file_name.is_empty() {
            continue;
        }
        let path = bundle_dir.join(&file_name);
        fs::write(&path, file.contents).map_err(|error| CommandError::new("export", error.to_string()))?;
        if file_name == requested_open_name {
            open_path = Some(path);
        }
    }

    let files_written = fs::read_dir(&bundle_dir)
        .map_err(|error| CommandError::new("export", error.to_string()))?
        .filter_map(Result::ok)
        .count();

    let open_path = open_path.ok_or_else(|| {
        CommandError::new(
            "export",
            String::from("The requested export launch file was not written."),
        )
    })?;

    Ok(WriteExportBundleResponse {
        directory: bundle_dir.to_string_lossy().into_owned(),
        open_path: open_path.to_string_lossy().into_owned(),
        files_written,
    })
}

pub async fn open_export_preview(
    app_handle: AppHandle,
    request: OpenExportPreviewRequest,
) -> CommandResult<OpenExportPreviewResponse> {
    if request.documents.is_empty() {
        return Err(CommandError::new(
            "export_preview",
            String::from("There was no export document to preview."),
        ));
    }

    let token = format!(
        "export_{}",
        EXPORT_PREVIEW_COUNTER.fetch_add(1, Ordering::Relaxed)
    );
    let window_label = format!("export-preview-{token}");
    let initial_document_id = if request.initial_document_id.trim().is_empty() {
        request
            .documents
            .first()
            .map(|document| document.id.clone())
            .unwrap_or_default()
    } else {
        request.initial_document_id.trim().to_string()
    };

    {
        let state = app_handle.state::<BackendState>();
        let mut runtime = state.runtime.lock().await;
        runtime.export_previews.insert(
            token.clone(),
            ExportPreviewSession {
                title: request.title.clone(),
                initial_document_id: initial_document_id.clone(),
                documents: request.documents.clone(),
            },
        );
        while runtime.export_previews.len() > 12 {
            let oldest = runtime.export_previews.keys().next().cloned();
            if let Some(oldest) = oldest {
                runtime.export_previews.remove(&oldest);
            } else {
                break;
            }
        }
    }

    let preview_url = format!("index.html#/export-preview?token={token}");
    let build_result = tauri::WebviewWindowBuilder::new(
        &app_handle,
        window_label.clone(),
        tauri::WebviewUrl::App(preview_url.into()),
    )
    .title(&request.title)
    .inner_size(1480.0, 940.0)
    .resizable(true)
    .focused(true)
    .build();

    if let Err(error) = build_result {
        let state = app_handle.state::<BackendState>();
        let mut runtime = state.runtime.lock().await;
        runtime.export_previews.remove(&token);
        return Err(CommandError::new("export_preview", error.to_string()));
    }

    Ok(OpenExportPreviewResponse { token, window_label })
}

pub async fn get_export_preview(
    app_handle: AppHandle,
    request: ExportPreviewTokenRequest,
) -> CommandResult<ExportPreviewResponse> {
    let state = app_handle.state::<BackendState>();
    let runtime = state.runtime.lock().await;
    let preview = runtime
        .export_previews
        .get(request.token.trim())
        .cloned()
        .ok_or_else(|| {
            CommandError::new(
                "export_preview",
                String::from("The requested export preview is no longer available."),
            )
        })?;

    Ok(ExportPreviewResponse {
        title: preview.title,
        initial_document_id: preview.initial_document_id,
        documents: preview.documents,
    })
}

pub async fn release_export_preview(
    app_handle: AppHandle,
    request: ExportPreviewTokenRequest,
) -> CommandResult<ReleaseExportPreviewResponse> {
    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;
    let released = runtime.export_previews.remove(request.token.trim()).is_some();
    Ok(ReleaseExportPreviewResponse { released })
}

pub async fn build_planner_projection(
    app_handle: AppHandle,
    request: PlannerProjectionRequest,
) -> CommandResult<PlannerProjectionResponse> {
    let state = app_handle.state::<BackendState>();
    let runtime = state.runtime.lock().await;
    let analysis = runtime
        .ops_defs_cache
        .as_ref()
        .map(|defs| analyze_platoons_internal(&runtime, defs));
    Ok(planner::build_projection(
        &request.settings,
        &runtime.guild_rosters,
        analysis.as_ref(),
    ))
}

pub async fn run_planner_optimization(
    app_handle: AppHandle,
    request: PlannerOptimizationRequest,
) -> CommandResult<PlannerOptimizationResponse> {
    let state = app_handle.state::<BackendState>();
    let (guild_rosters, ops_defs) = {
        let mut runtime = state.runtime.lock().await;
        let ops_defs = load_ops_definitions_internal(&mut runtime).unwrap_or_default();
        (runtime.guild_rosters.clone(), ops_defs)
    };

    Ok(planner::run_optimizer(
        &request.settings,
        &guild_rosters,
        Some(&ops_defs),
        &request.algorithm,
        |payload| emit_optimizer_progress(&app_handle, payload),
    ))
}

pub async fn load_app_state(app_handle: AppHandle) -> CommandResult<LoadAppStateResponse> {
    Ok(LoadAppStateResponse {
        state: load_app_state_from_disk(&app_handle)?,
    })
}

pub async fn save_app_state(
    app_handle: AppHandle,
    request: SaveAppStateRequest,
) -> CommandResult<SaveAppStateResponse> {
    save_app_state_to_disk(&app_handle, request.snapshot)?;
    Ok(SaveAppStateResponse { saved: true })
}

pub async fn import_session_state(
    app_handle: AppHandle,
    request: ImportSessionRequest,
) -> CommandResult<ImportSessionResponse> {
    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;

    let members = request.guild_rosters.len();
    let units = request
        .guild_rosters
        .values()
        .map(std::vec::Vec::len)
        .sum::<usize>();
    runtime.guild_rosters = request.guild_rosters;
    runtime.guide_tb_omicron_cache = None;
    runtime.ops_defs_cache = None;

    Ok(ImportSessionResponse {
        imported: true,
        members,
        units,
    })
}

pub async fn reset_scan_session(app_handle: AppHandle) -> CommandResult<ResetScanSessionResponse> {
    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;
    runtime.guild_rosters.clear();
    runtime.guide_tb_omicron_cache = None;
    runtime.ops_defs_cache = None;
    drop(runtime);
    if let Ok(path) = comlink_dir(&app_handle).map(|dir| dir.join(SCAN_LOG_FILE)) {
        let _ = fs::write(path, "[]");
    }
    Ok(ResetScanSessionResponse { reset: true })
}

async fn refresh_comlink_status_internal(
    app_handle: &AppHandle,
) -> CommandResult<ComlinkStatusResponse> {
    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;
    let binary_path = find_existing_comlink_binary(app_handle, &mut runtime)
        .map(|path| path.display().to_string())
        .or_else(|| runtime.comlink_binary.as_ref().map(|path| path.display().to_string()));

    match comlink_metadata().await {
        Ok(meta) => {
            let version = first_non_empty_string(
                &meta,
                &["latestGamedataVersion", "gameVersion", "version"],
            )
            .unwrap_or_else(|| String::from("?"));
            Ok(ComlinkStatusResponse {
                comlink: String::from("online"),
                port: COMLINK_PORT,
                version,
                binary_path,
                managed_process: managed_child_running(&mut runtime),
                message: None,
            })
        }
        Err(error) => Ok(ComlinkStatusResponse {
            comlink: String::from("offline"),
            port: COMLINK_PORT,
            version: String::from("?"),
            binary_path,
            managed_process: managed_child_running(&mut runtime),
            message: Some(error.message),
        }),
    }
}

async fn start_comlink_internal(
    app_handle: &AppHandle,
    runtime: &mut BackendRuntime,
) -> CommandResult<()> {
    if comlink_metadata().await.is_ok() {
        return Ok(());
    }

    let binary_path = ensure_comlink_binary(app_handle, runtime).await?;
    let working_dir = binary_path
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or(comlink_dir(app_handle)?);

    let mut command = Command::new(&binary_path);
    command
        .arg("-n")
        .arg(APP_NAME)
        .env("APP_NAME", APP_NAME)
        .current_dir(&working_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    let mut child = command.spawn().map_err(|error| {
        CommandError::new(
            "comlink_spawn",
            format!(
                "Could not start swgoh-comlink from '{}': {error}. If this is Windows, open the file Properties and make sure the binary is unblocked.",
                binary_path.display()
            ),
        )
    })?;

    drain_child_pipes(&mut child);
    runtime.comlink_binary = Some(binary_path.clone());
    runtime.comlink_child = Some(child);

    for _ in 0..30 {
        tokio::time::sleep(Duration::from_millis(500)).await;
        if comlink_metadata().await.is_ok() {
            return Ok(());
        }
    }

    stop_comlink_internal(runtime)?;
    Err(CommandError::new(
        "comlink_health",
        format!(
            "swgoh-comlink started from '{}' but never became responsive on port {}. Try running it manually from that folder once to confirm it launches cleanly.",
            binary_path.display(),
            COMLINK_PORT
        ),
    ))
}

fn stop_comlink_internal(runtime: &mut BackendRuntime) -> CommandResult<()> {
    if let Some(child) = runtime.comlink_child.as_mut() {
        let _ = child.kill();
        let _ = child.wait();
    }
    runtime.comlink_child = None;
    Ok(())
}

async fn lookup_player_by_ally_code(ally_code: &str) -> CommandResult<Value> {
    if ally_code.is_empty() {
        return Err(CommandError::new("validation", "An ally code is required."));
    }

    if let Ok(parsed) = ally_code.parse::<i64>() {
        if let Ok(player) = comlink_post("player", json!({ "allyCode": parsed }), 15).await {
            return Ok(player);
        }
    }

    comlink_post("player", json!({ "allyCode": ally_code }), 15).await
}

async fn scan_roster_internal(
    app_handle: &AppHandle,
    raw_ally_code: &str,
) -> CommandResult<RosterScanResponse> {
    let normalized = normalize_scan_key(raw_ally_code);
    if normalized.is_empty() {
        return Err(CommandError::new("validation", "A roster key is required."));
    }

    {
        let state = app_handle.state::<BackendState>();
        let mut runtime = state.runtime.lock().await;
        ensure_localization_maps(app_handle, &mut runtime).await?;
    }

    let mut player = fetch_roster_player_with_retry(app_handle, &normalized).await?;
    let (power_ready, power_error) =
        try_apply_statcalc_power(app_handle, std::slice::from_mut(&mut player));
    let (simplified, skipped);
    {
        let state = app_handle.state::<BackendState>();
        let mut runtime = state.runtime.lock().await;
        (simplified, skipped) = simplify_player_roster(&runtime, &player);
        runtime.guild_rosters.insert(normalized.clone(), simplified.clone());
        runtime.guide_tb_omicron_cache = None;
        runtime.ops_defs_cache = None;
    }

    Ok(RosterScanResponse {
        ally_code: normalized,
        units: simplified.len(),
        skipped,
        roster: simplified,
        power_ready,
        power_error,
    })
}

async fn fetch_roster_player_with_retry(
    app_handle: &AppHandle,
    raw_ally_code: &str,
) -> CommandResult<Value> {
    let normalized = normalize_scan_key(raw_ally_code);
    let mut last_error = CommandError::new(
        "scan_roster",
        format!("Roster scan failed for '{normalized}'."),
    );

    for attempt in 0..SCAN_MAX_ATTEMPTS {
        match fetch_roster_player(&normalized).await {
            Ok(player)
                if player
                    .get("rosterUnit")
                    .and_then(Value::as_array)
                    .map(|roster| !roster.is_empty())
                    .unwrap_or(false) =>
            {
                return Ok(player);
            }
            Ok(_) => {
                last_error = CommandError::new(
                    "scan_roster",
                    format!("Comlink returned an empty roster for '{normalized}'."),
                );
            }
            Err(error) => last_error = error,
        }

        if attempt + 1 < SCAN_MAX_ATTEMPTS {
            let delay_ms = SCAN_RETRY_DELAY_MS * (attempt as u64 + 1);
            tokio::time::sleep(Duration::from_millis(delay_ms)).await;
        }
    }

    log_scan_failure(
        app_handle,
        json!({
            "allyCode": normalized,
            "status": "FAILED",
            "error": last_error.message.clone(),
            "timestampUnix": std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|duration| duration.as_secs())
                .unwrap_or_default(),
        }),
    );

    Err(last_error)
}

fn simplify_player_roster(
    runtime: &BackendRuntime,
    player: &Value,
) -> (Vec<SimplifiedRosterUnit>, usize) {
    let roster = player
        .get("rosterUnit")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    let mut simplified = Vec::new();
    let mut skipped = 0usize;
    for unit in roster {
        match simplify_roster_unit(runtime, &unit) {
            Some(unit) => simplified.push(unit),
            None => skipped += 1,
        }
    }

    (simplified, skipped)
}

fn try_apply_statcalc_power(app_handle: &AppHandle, players: &mut [Value]) -> (bool, String) {
    if players.is_empty() {
        return (true, String::new());
    }
    if !players.iter().any(player_needs_power_calc) {
        return (true, String::new());
    }

    let Ok(cache_root) = comlink_dir(app_handle) else {
        return (
            false,
            String::from("Could not resolve the app cache directory for unit power calculation."),
        );
    };
    let script_path = cache_root.join(STATCALC_BRIDGE_FILE);
    let request_path = cache_root.join(STATCALC_REQUEST_FILE);
    let cache_path = cache_root.join(STATCALC_GAMEDATA_CACHE_FILE);

    if let Err(error) = fs::write(&script_path, STATCALC_BRIDGE_SOURCE) {
        return (
            false,
            format!("Could not stage the stat calculator bridge script: {error}"),
        );
    }

    let request = StatCalcBridgeRequest {
        cache_path: cache_path.to_string_lossy().into_owned(),
        comlink_url: format!("http://127.0.0.1:{COMLINK_PORT}"),
        rosters: players
            .iter()
            .map(|player| {
                player
                    .get("rosterUnit")
                    .and_then(Value::as_array)
                    .cloned()
                    .unwrap_or_default()
            })
            .collect(),
    };

    let request_body = match serde_json::to_vec(&request) {
        Ok(body) => body,
        Err(error) => {
            return (
                false,
                format!("Could not serialize the unit power calculation request: {error}"),
            );
        }
    };
    if let Err(error) = fs::write(&request_path, request_body) {
        return (
            false,
            format!("Could not write the unit power calculation request: {error}"),
        );
    }

    let bridge_output = match run_statcalc_bridge(&script_path, &request_path) {
        Ok(output) => output,
        Err(error) => return (false, error),
    };
    let response = match serde_json::from_slice::<StatCalcBridgeResponse>(&bridge_output) {
        Ok(response) => response,
        Err(error) => {
            return (
                false,
                format!("Could not parse the unit power calculation response: {error}"),
            );
        }
    };

    if !response.ok {
        return (
            false,
            if response.error.trim().is_empty() {
                String::from("The unit power bridge reported an unknown failure.")
            } else {
                response.error
            },
        );
    }
    if response.results.len() != players.len() {
        return (
            false,
            format!(
                "The unit power bridge returned {} rosters for {} requests.",
                response.results.len(),
                players.len()
            ),
        );
    }

    let mut errors = Vec::new();
    for (player, result) in players.iter_mut().zip(response.results.into_iter()) {
        if let Some(roster) = player.get_mut("rosterUnit").and_then(Value::as_array_mut) {
            for (unit, power) in roster.iter_mut().zip(result.powers.into_iter()) {
                if power <= 0 || extract_unit_power(unit) > 0 {
                    continue;
                }
                if let Some(record) = unit.as_object_mut() {
                    record.insert(String::from("gp"), json!(power));
                }
            }
        }
        if !result.error.trim().is_empty() {
            errors.push(result.error);
        }
    }

    let power_ready = players.iter().all(player_has_complete_power);
    if !power_ready && errors.is_empty() {
        errors.push(String::from(
            "Some unit power values are still missing after stat calculation.",
        ));
    }

    let error_message = errors
        .into_iter()
        .filter(|entry| !entry.trim().is_empty())
        .take(3)
        .collect::<Vec<_>>()
        .join("; ");
    (power_ready, error_message)
}

fn run_statcalc_bridge(script_path: &Path, request_path: &Path) -> Result<Vec<u8>, String> {
    let candidates = [
        ("python", Vec::<&str>::new()),
        ("py", vec!["-3"]),
        ("python3", Vec::<&str>::new()),
    ];
    let mut failures = Vec::new();

    for (command_name, prefix_args) in candidates {
        let mut command = Command::new(command_name);
        for arg in prefix_args {
            command.arg(arg);
        }
        let output = command
            .arg(script_path)
            .arg(request_path)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .output();

        match output {
            Ok(output) if output.status.success() => return Ok(output.stdout),
            Ok(output) => {
                let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
                let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
                let detail = [stderr, stdout]
                    .into_iter()
                    .filter(|entry| !entry.is_empty())
                    .collect::<Vec<_>>()
                    .join(" | ");
                failures.push(if detail.is_empty() {
                    format!("{command_name}: exited with status {}", output.status)
                } else {
                    format!("{command_name}: {detail}")
                });
            }
            Err(error) => failures.push(format!("{command_name}: {error}")),
        }
    }

    Err(if failures.is_empty() {
        String::from("No compatible Python runtime was available for unit power calculation.")
    } else {
        failures.join("; ")
    })
}

fn player_needs_power_calc(player: &Value) -> bool {
    player
        .get("rosterUnit")
        .and_then(Value::as_array)
        .map(|roster| roster.iter().any(|unit| extract_unit_power(unit) <= 0))
        .unwrap_or(false)
}

fn player_has_complete_power(player: &Value) -> bool {
    player
        .get("rosterUnit")
        .and_then(Value::as_array)
        .map(|roster| {
            roster.is_empty() || roster.iter().all(|unit| extract_unit_power(unit) > 0)
        })
        .unwrap_or(true)
}

async fn recover_comlink_for_scan(app_handle: &AppHandle) -> bool {
    for _ in 0..SCAN_RECOVERY_ATTEMPTS {
        tokio::time::sleep(Duration::from_millis(SCAN_RECOVERY_WAIT_MS)).await;
        if comlink_metadata().await.is_ok() {
            return true;
        }

        if restart_comlink_for_recovery(app_handle).await.is_ok() && comlink_metadata().await.is_ok()
        {
            return true;
        }
    }

    false
}

async fn restart_comlink_for_recovery(app_handle: &AppHandle) -> CommandResult<()> {
    let state = app_handle.state::<BackendState>();
    let mut runtime = state.runtime.lock().await;
    let can_restart = managed_child_running(&mut runtime)
        || runtime.comlink_binary.is_some()
        || find_existing_comlink_binary(app_handle, &mut runtime).is_some();

    if !can_restart {
        return Err(CommandError::new(
            "comlink_recovery",
            "No swgoh-comlink binary is available for recovery.",
        ));
    }

    let _ = stop_comlink_internal(&mut runtime);
    start_comlink_internal(app_handle, &mut runtime).await
}

async fn fetch_roster_player(scan_key: &str) -> CommandResult<Value> {
    let is_guid = !scan_key.chars().all(|ch| ch.is_ascii_digit()) && scan_key.len() > 10;

    if is_guid {
        if let Ok(player) = comlink_post(
            "player",
            json!({ "playerId": scan_key }),
            SCAN_FETCH_TIMEOUT_SECONDS,
        )
        .await
        {
            return Ok(player);
        }
        return comlink_post(
            "player",
            json!({ "allyCode": scan_key }),
            SCAN_FETCH_TIMEOUT_SECONDS,
        )
        .await;
    }

    if let Ok(parsed) = scan_key.parse::<i64>() {
        if let Ok(player) = comlink_post(
            "player",
            json!({ "allyCode": parsed }),
            SCAN_FETCH_TIMEOUT_SECONDS,
        )
        .await
        {
            return Ok(player);
        }
    }
    comlink_post(
        "player",
        json!({ "allyCode": scan_key }),
        SCAN_FETCH_TIMEOUT_SECONDS,
    )
    .await
}

async fn comlink_metadata() -> CommandResult<Value> {
    comlink_post("metadata", json!({}), 4).await
}

async fn comlink_post(path: &str, payload: Value, timeout_seconds: u64) -> CommandResult<Value> {
    let client = COMLINK_HTTP_CLIENT.get_or_init(|| {
        reqwest::Client::builder()
            .build()
            .expect("failed to build shared reqwest client for swgoh-comlink")
    });

    let response = client
        .post(format!("http://127.0.0.1:{COMLINK_PORT}/{path}"))
        .timeout(Duration::from_secs(timeout_seconds))
        .json(&json!({
            "payload": payload,
            "enums": false
        }))
        .send()
        .await
        .map_err(|error| CommandError::new("comlink_unreachable", error.to_string()))?;

    let status = response.status();
    let body = response
        .text()
        .await
        .map_err(|error| CommandError::new("comlink_body", error.to_string()))?;

    let value = serde_json::from_str::<Value>(&body).map_err(|error| {
        CommandError::new(
            "comlink_json",
            format!("Could not parse comlink response for '{path}': {error}"),
        )
    })?;

    if !status.is_success() {
        return Err(CommandError::new(
            "comlink_status",
            format!("Comlink returned {status} for '{path}'."),
        ));
    }

    Ok(value)
}

async fn ensure_localization_maps(
    app_handle: &AppHandle,
    runtime: &mut BackendRuntime,
) -> CommandResult<()> {
    let cache_root = comlink_dir(app_handle)
        .ok()
        .or_else(app_data_root_from_runtime_path_hint);
    load_localization_caches(cache_root.as_deref(), runtime);
    if localization_maps_ready(runtime) {
        return Ok(());
    }

    let meta = comlink_metadata().await.unwrap_or_else(|_| json!({}));
    let bundle_id = first_non_empty_string(
        &meta,
        &["latestLocalizationBundleVersion", "localizationBundleVersion"],
    )
    .unwrap_or_default();
    let game_version =
        first_non_empty_string(&meta, &["latestGamedataVersion", "gameVersion"]).unwrap_or_default();

    let mut localization_payloads = Vec::new();
    if !bundle_id.is_empty() {
        localization_payloads.push(json!({ "id": bundle_id }));
    }
    localization_payloads.push(json!({ "id": "Loc_ENG_US.txt", "unzip": true }));
    localization_payloads.push(json!({ "id": "Loc_ENG_US.txt" }));
    localization_payloads.push(json!({ "language": "ENG_US" }));
    localization_payloads.push(json!({}));

    for payload in localization_payloads {
        if let Ok(bundle) = comlink_post("localization", payload, 10).await {
            let loc_values = extract_localization_bundle(&bundle);
            let (unit_added, ability_added) = merge_localization_bundle(runtime, loc_values);
            if unit_added > 0 || ability_added > 0 {
                break;
            }
        }
    }

    if !runtime.localization_value_map.is_empty() && !game_version.is_empty() {
        populate_gamedata_maps(runtime, &game_version).await?;
    }

    runtime.ops_defs_cache = None;
    cache_localization_maps(cache_root.as_deref(), runtime);
    Ok(())
}

async fn populate_gamedata_maps(
    runtime: &mut BackendRuntime,
    version: &str,
) -> CommandResult<()> {
    let (skill_data, ability_data, unit_data) = tokio::try_join!(
        comlink_post(
            "data",
            json!({
                "version": version,
                "includePveUnits": false,
                "requestSegment": 1
            }),
            45,
        ),
        comlink_post(
            "data",
            json!({
                "version": version,
                "includePveUnits": false,
                "requestSegment": 2
            }),
            45,
        ),
        comlink_post(
            "data",
            json!({
                "version": version,
                "includePveUnits": false,
                "requestSegment": 3
            }),
            45,
        ),
    )?;

    let mut ability_name_by_id = HashMap::<String, String>::new();
    if let Some(abilities) = ability_data.get("ability").and_then(Value::as_array) {
        for ability in abilities {
            let ability_id = first_non_empty_string(ability, &["id"]).unwrap_or_default();
            let name = lookup_localized_text(
                runtime,
                first_non_empty_string(ability, &["nameKey"]).as_deref().unwrap_or_default(),
            );
            if !ability_id.is_empty() && !name.is_empty() {
                store_ability_name(runtime, &ability_id, &name);
                ability_name_by_id.insert(normalize_loc_key(&ability_id), name);
            }
        }
    }

    if let Some(skills) = skill_data.get("skill").and_then(Value::as_array) {
        for skill in skills {
            let skill_id = first_non_empty_string(skill, &["id"]).unwrap_or_default();
            if skill_id.is_empty() {
                continue;
            }

            let ability_reference =
                first_non_empty_string(skill, &["abilityReference"]).unwrap_or_default();
            let mut name = ability_name_by_id
                .get(&normalize_loc_key(&ability_reference))
                .cloned()
                .unwrap_or_default();
            if name.is_empty() {
                name = lookup_localized_text(
                    runtime,
                    first_non_empty_string(skill, &["nameKey"]).as_deref().unwrap_or_default(),
                );
            }
            if !name.is_empty() {
                store_ability_name(runtime, &skill_id, &name);
            }

            let tier_rows = skill
                .get("tier")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            let mut zeta_tiers = Vec::new();
            let mut omicron_tiers = Vec::new();
            for (index, tier) in tier_rows.iter().enumerate() {
                if truthy(tier.get("isZetaTier")) {
                    zeta_tiers.push((index + 1) as i64);
                }
                if truthy(tier.get("isOmicronTier")) {
                    omicron_tiers.push((index + 1) as i64);
                }
            }

            runtime.skill_meta_map.insert(
                normalize_loc_key(&skill_id),
                SkillMeta {
                    max_tier: tier_rows.len() as i64 + 1,
                    is_zeta: truthy(skill.get("isZeta")) || !zeta_tiers.is_empty(),
                    is_omicron: !omicron_tiers.is_empty(),
                    omicron_area: extract_i64(skill.get("omicronMode")).unwrap_or(0),
                    kind: infer_skill_kind(&skill_id),
                    zeta_tiers,
                    omicron_tiers,
                },
            );
        }
    }

    if let Some(units) = unit_data.get("units").and_then(Value::as_array) {
        for unit in units {
            let base_id = first_non_empty_string(unit, &["baseId", "id"]).unwrap_or_default();
            if base_id.is_empty() {
                continue;
            }
            let normalized = normalize_loc_key(&base_id);
            let name = lookup_localized_text(
                runtime,
                first_non_empty_string(unit, &["nameKey"]).as_deref().unwrap_or_default(),
            );
            if !name.is_empty() {
                runtime.unit_name_map.insert(normalized.clone(), name);
            }

            runtime.unit_skill_reference_map.insert(
                normalized.clone(),
                extract_skill_ids(unit.get("skillReference"), false),
            );

            let mut crew_unit_ids = Vec::new();
            let mut crew_skill_ids = Vec::new();
            if let Some(crew_entries) = unit.get("crew").and_then(Value::as_array) {
                for crew_entry in crew_entries {
                    if let Some(unit_id) =
                        first_non_empty_string(crew_entry, &["unitId"]).filter(|value| !value.is_empty())
                    {
                        crew_unit_ids.push(normalize_loc_key(&unit_id));
                    }
                    crew_skill_ids.extend(extract_skill_ids(crew_entry.get("skillReference"), true));
                }
            }
            runtime
                .unit_crew_map
                .insert(normalized.clone(), crew_unit_ids);
            runtime
                .unit_crew_skill_reference_map
                .insert(normalized.clone(), crew_skill_ids);

            let combat_type = extract_i64(unit.get("combatType")).unwrap_or(1);
            if combat_type == 2
                || unit
                    .get("crew")
                    .and_then(Value::as_array)
                    .map_or(false, |crew| !crew.is_empty())
            {
                runtime.known_ship_defids.insert(canonical_defid_key(&base_id));
            } else {
                runtime
                    .known_character_defids
                    .insert(canonical_defid_key(&base_id));
            }
        }
    }

    rebuild_known_combat_type_indexes(runtime);

    Ok(())
}

fn simplify_roster_unit(runtime: &BackendRuntime, unit: &Value) -> Option<SimplifiedRosterUnit> {
    let raw_def_id = first_non_empty_string(
        unit,
        &["defId", "baseId", "definitionId", "unitDefId", "id"],
    )?;
    let def_id = canonical_defid(&raw_def_id);
    if def_id.is_empty() {
        return None;
    }

    let relic_tier = match unit.get("relic") {
        Some(Value::Object(relic)) => extract_i64(relic.get("currentTier"))
            .or_else(|| extract_i64(relic.get("tier")))
            .unwrap_or(0),
        Some(other) => extract_i64(Some(other)).unwrap_or(0),
        None => extract_i64(unit.get("relicTier")).unwrap_or(0),
    };
    let relic_level = (relic_tier - 2).max(0);
    let combat_type = infer_combat_type(
        runtime,
        &def_id,
        unit.get("combatType").or_else(|| unit.get("type")),
    );
    let skills = simplify_skills(runtime, unit, &def_id, combat_type);
    let zetas = skills.iter().filter(|skill| skill.has_zeta).count() as i64;
    let omicrons = skills.iter().filter(|skill| skill.has_omicron).count() as i64;
    let fallback_name = first_non_empty_string(unit, &["name"]).unwrap_or_else(|| def_id.clone());

    Some(SimplifiedRosterUnit {
        def_id: def_id.clone(),
        name: lookup_unit_name(runtime, &def_id, &fallback_name),
        rarity: extract_i64_with_default(
            unit,
            &["currentRarity", "rarity", "starLevel", "stars"],
            0,
        ),
        gear: extract_i64_with_default(
            unit,
            &["currentTier", "gear", "currentGear", "gearLevel", "gearTier"],
            0,
        ),
        relic: relic_level,
        combat_type,
        mods_present: unit.get("equippedStatMod").is_some(),
        speed: extract_speed(unit),
        power: extract_unit_power(unit),
        zetas,
        omicrons,
        skills,
    })
}

fn simplify_skills(
    runtime: &BackendRuntime,
    unit: &Value,
    def_id: &str,
    combat_type: i64,
) -> Vec<SimplifiedSkillRow> {
    let mut roster_skill_tiers = HashMap::<String, i64>::new();
    if let Some(skills) = unit.get("skill").or_else(|| unit.get("skills")).and_then(Value::as_array)
    {
        for skill in skills {
            let skill_id = first_non_empty_string(skill, &["id", "skillId", "abilityId"])
                .unwrap_or_default();
            if skill_id.is_empty() {
                continue;
            }
            roster_skill_tiers.insert(
                normalize_loc_key(&skill_id),
                extract_i64(skill.get("tier")).unwrap_or(0),
            );
        }
    }

    let mut seen = HashSet::<String>::new();
    let mut skills = Vec::new();
    let source_skill_rows = unit
        .get("skill")
        .or_else(|| unit.get("skills"))
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    for skill_id in collect_unit_skill_ids(runtime, def_id, combat_type) {
        push_skill_row(
            runtime,
            &mut skills,
            &mut seen,
            &skill_id,
            *roster_skill_tiers
                .get(&normalize_loc_key(&skill_id))
                .unwrap_or(&1),
            false,
        );
    }

    for (skill_key, raw_tier) in roster_skill_tiers {
        if seen.contains(&skill_key) {
            continue;
        }
        let skill_id = source_skill_rows
            .iter()
            .find_map(|skill| {
                let id = first_non_empty_string(skill, &["id", "skillId", "abilityId"])?;
                if normalize_loc_key(&id) == skill_key {
                    Some(id)
                } else {
                    None
                }
            })
            .unwrap_or(skill_key.clone());
        push_skill_row(runtime, &mut skills, &mut seen, &skill_id, raw_tier, false);
    }

    if let Some(purchased) = unit.get("purchasedAbilityId").and_then(Value::as_array) {
        for entry in purchased {
            if let Some(skill_id) = entry.as_str() {
                push_skill_row(runtime, &mut skills, &mut seen, skill_id, 0, true);
            }
        }
    }

    skills
}

fn push_skill_row(
    runtime: &BackendRuntime,
    target: &mut Vec<SimplifiedSkillRow>,
    seen: &mut HashSet<String>,
    skill_id: &str,
    raw_tier: i64,
    unlocked: bool,
) {
    let skill_key = normalize_loc_key(skill_id);
    if skill_key.is_empty() || seen.contains(&skill_key) {
        return;
    }
    seen.insert(skill_key);
    target.push(skill_row_from_meta(runtime, skill_id, raw_tier, unlocked));
}

fn skill_row_from_meta(
    runtime: &BackendRuntime,
    skill_id: &str,
    raw_tier: i64,
    unlocked: bool,
) -> SimplifiedSkillRow {
    let meta = runtime
        .skill_meta_map
        .get(&normalize_loc_key(skill_id))
        .cloned()
        .unwrap_or_default();
    let level = skill_level_from_tier(raw_tier, meta.max_tier);
    let has_zeta = meta
        .zeta_tiers
        .iter()
        .any(|tier| (*tier - 1).max(0) <= raw_tier);
    let has_omicron = meta
        .omicron_tiers
        .iter()
        .any(|tier| (*tier - 1).max(0) <= raw_tier);

    SimplifiedSkillRow {
        id: skill_id.to_string(),
        skill_id: skill_id.to_string(),
        name: lookup_ability_name(runtime, skill_id),
        tier: raw_tier,
        level,
        max_tier: meta.max_tier,
        kind: if meta.kind.is_empty() {
            infer_skill_kind(skill_id)
        } else {
            meta.kind
        },
        is_zeta: meta.is_zeta,
        is_omicron: meta.is_omicron,
        omicron_area: meta.omicron_area,
        has_zeta,
        has_omicron,
        unlocked,
    }
}

fn collect_unit_skill_ids(runtime: &BackendRuntime, def_id: &str, combat_type: i64) -> Vec<String> {
    let base_key = normalize_loc_key(def_id);
    let mut ordered = Vec::new();
    let mut seen = HashSet::<String>::new();

    let mut push = |values: &[String]| {
        for value in values {
            let key = normalize_loc_key(value);
            if key.is_empty() || seen.contains(&key) {
                continue;
            }
            seen.insert(key);
            ordered.push(value.clone());
        }
    };

    if let Some(values) = runtime.unit_skill_reference_map.get(&base_key) {
        push(values);
    }

    if combat_type == 2 {
        if let Some(values) = runtime.unit_crew_skill_reference_map.get(&base_key) {
            push(values);
        } else if let Some(crew_units) = runtime.unit_crew_map.get(&base_key) {
            for crew_unit in crew_units {
                if let Some(values) = runtime.unit_skill_reference_map.get(&normalize_loc_key(crew_unit))
                {
                    let first = values.first().cloned().into_iter().collect::<Vec<_>>();
                    push(&first);
                }
            }
        }
    }

    ordered
}

fn build_guide_tb_omicron_map(runtime: &mut BackendRuntime) -> GuideTbOmicronMap {
    if let Some(cached) = runtime.guide_tb_omicron_cache.clone() {
        return cached;
    }

    let mut result = HashMap::<String, Vec<GuideTbOmicron>>::new();
    for unit_id in runtime.unit_skill_reference_map.keys() {
        if infer_combat_type(runtime, unit_id, None) != 1 {
            continue;
        }

        let mut seen = HashSet::<String>::new();
        let mut rows = Vec::new();
        for skill_id in collect_unit_skill_ids(runtime, unit_id, 1) {
            let skill_key = normalize_loc_key(&skill_id);
            if seen.contains(&skill_key) {
                continue;
            }
            seen.insert(skill_key.clone());
            let meta = runtime.skill_meta_map.get(&skill_key).cloned().unwrap_or_default();
            if !meta.is_omicron || meta.omicron_area != 7 {
                continue;
            }
            rows.push(GuideTbOmicron {
                skill_id: skill_id.clone(),
                name: lookup_ability_name(runtime, &skill_id),
                kind: if meta.kind.is_empty() {
                    infer_skill_kind(&skill_id)
                } else {
                    meta.kind
                },
                omicron_area: 7,
            });
        }
        if !rows.is_empty() {
            result.insert(normalize_loc_key(unit_id), rows);
        }
    }

    runtime.guide_tb_omicron_cache = Some(result.clone());
    result
}

fn build_guide_unit_catalog(runtime: &BackendRuntime) -> Vec<GuideUnitCatalogEntry> {
    let legacy = legacy_unit_data();
    let mut entries = HashMap::<String, GuideUnitCatalogEntry>::new();

    let mut upsert = |def_id: &str, fallback_name: &str| {
        let key = canonical_defid_key(def_id);
        if key.is_empty() {
            return;
        }

        let name = lookup_unit_name(runtime, def_id, fallback_name).trim().to_string();
        if name.is_empty() || name == "(unknown)" {
            return;
        }

        let next = GuideUnitCatalogEntry {
            def_id: key.clone(),
            name,
            combat_type: infer_combat_type(runtime, def_id, None),
        };

        match entries.get(&key) {
            Some(existing) if existing.name != existing.def_id || next.name == next.def_id => return,
            _ => {}
        }

        entries.insert(key, next);
    };

    for (def_id, fallback_name) in &legacy.playable_names {
        upsert(def_id, fallback_name);
    }

    for roster in runtime.guild_rosters.values() {
        for unit in roster {
            upsert(&unit.def_id, &unit.name);
        }
    }

    let mut units = entries.into_values().collect::<Vec<_>>();
    units.sort_by(|left, right| {
        left.name
            .to_lowercase()
            .cmp(&right.name.to_lowercase())
            .then(left.def_id.cmp(&right.def_id))
    });
    units
}

fn load_ops_definitions_internal(runtime: &mut BackendRuntime) -> CommandResult<OpsDefinitions> {
    if let Some(defs) = runtime.ops_defs_cache.clone() {
        return Ok(defs);
    }

    let wiki_names = load_wiki_ops_names()?;
    let zone_relic_by_planet = zone_relic_by_planet();
    let mut defs = HashMap::<String, Vec<Vec<PlatoonRequirement>>>::new();

    for (planet_id, platoons) in wiki_names {
        let relic = zone_relic_by_planet.get(planet_id.as_str()).copied().unwrap_or(0);
        let mut built = Vec::new();
        for platoon in platoons {
            let mut slots = Vec::new();
            for display_name in platoon {
                let def_id = resolve_unit_name_to_defid(runtime, &display_name)
                    .unwrap_or_else(|| placeholder_ops_defid(&display_name));
                let min_relic = if is_ship_name_or_defid(runtime, &display_name, &def_id) {
                    0
                } else {
                    relic
                };
                slots.push(PlatoonRequirement {
                    name: lookup_unit_name(runtime, &def_id, &display_name),
                    def_id,
                    min_rarity: 7,
                    min_relic,
                });
            }
            if !slots.is_empty() {
                built.push(slots);
            }
        }
        if !built.is_empty() {
            defs.insert(planet_id, built);
        }
    }

    runtime.ops_defs_cache = Some(defs.clone());
    Ok(defs)
}

fn analyze_platoons_internal(runtime: &BackendRuntime, defs: &OpsDefinitions) -> PlatoonAnalysisMap {
    let mut out = HashMap::<String, Vec<PlatoonAnalysisEntry>>::new();
    for (planet_id, platoons) in defs {
        let mut planet_rows = Vec::new();
        for platoon in platoons {
            let mut needs = HashMap::<String, PlatoonSlotAnalysis>::new();
            for slot in platoon {
                let entry = needs.entry(slot.def_id.clone()).or_insert_with(|| PlatoonSlotAnalysis {
                    def_id: slot.def_id.clone(),
                    name: slot.name.clone(),
                    need: 0,
                    have: 0,
                    min_rarity: slot.min_rarity,
                    min_relic: slot.min_relic,
                    ok: false,
                });
                entry.need += 1;
            }

            let mut slot_rows = Vec::new();
            for (_, mut requirement) in needs {
                let requirement_is_ship =
                    is_ship_name_or_defid(runtime, &requirement.name, &requirement.def_id);
                let target_name = normalize_unit_name_lookup(&requirement.name);
                let mut have = 0i64;
                for roster in runtime.guild_rosters.values() {
                    for unit in roster {
                        let unit_name_key =
                            normalize_unit_name_lookup(&lookup_unit_name(runtime, &unit.def_id, &unit.name));
                        let names_match = if requirement.def_id.starts_with("WIKI_") {
                            unit_name_key == target_name
                        } else {
                            canonical_defid(&unit.def_id) == canonical_defid(&requirement.def_id)
                                || (!target_name.is_empty() && unit_name_key == target_name)
                        };
                        if !names_match {
                            continue;
                        }
                        if unit.rarity < requirement.min_rarity {
                            continue;
                        }
                        if !requirement_is_ship && unit.relic < requirement.min_relic {
                            continue;
                        }
                        have += 1;
                    }
                }
                requirement.have = have;
                requirement.ok = have >= requirement.need;
                slot_rows.push(requirement);
            }

            slot_rows.sort_by(|left, right| {
                (left.ok, left.have - left.need).cmp(&(right.ok, right.have - right.need))
            });
            planet_rows.push(PlatoonAnalysisEntry {
                fillable: slot_rows.iter().all(|slot| slot.ok),
                slots: slot_rows,
            });
        }
        out.insert(planet_id.clone(), planet_rows);
    }
    out
}

fn load_app_state_from_disk(app_handle: &AppHandle) -> CommandResult<Value> {
    let path = app_state_path(app_handle)?;
    if !path.exists() {
        return Ok(json!({}));
    }
    let body = fs::read_to_string(&path)
        .map_err(|error| CommandError::new("app_state_read", error.to_string()))?;
    let value = serde_json::from_str::<Value>(&body)
        .map_err(|error| CommandError::new("app_state_parse", error.to_string()))?;
    Ok(sanitize_persisted_app_state(value))
}

fn save_app_state_to_disk(app_handle: &AppHandle, snapshot: Value) -> CommandResult<()> {
    let path = app_state_path(app_handle)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| CommandError::new("app_state_dir", error.to_string()))?;
    }
    let sanitized = sanitize_persisted_app_state(snapshot);
    let payload = serde_json::to_string_pretty(&sanitized)
        .map_err(|error| CommandError::new("app_state_serialize", error.to_string()))?;
    fs::write(&path, payload).map_err(|error| CommandError::new("app_state_write", error.to_string()))
}

fn sanitize_persisted_app_state(snapshot: Value) -> Value {
    let Some(mut object) = snapshot.as_object().cloned() else {
        return json!({});
    };
    for key in VOLATILE_APP_STATE_KEYS {
        object.remove(*key);
    }
    Value::Object(object)
}

fn app_state_path(app_handle: &AppHandle) -> CommandResult<PathBuf> {
    Ok(comlink_dir(app_handle)?.join(APP_STATE_FILE))
}

fn sanitize_export_path_segment(value: &str) -> String {
    value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' {
                ch
            } else {
                '_'
            }
        })
        .collect::<String>()
        .trim_matches('_')
        .to_string()
}

fn sanitize_export_file_name(value: &str) -> String {
    value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' || ch == '.' {
                ch
            } else {
                '_'
            }
        })
        .collect::<String>()
        .trim_matches('_')
        .to_string()
}

fn comlink_dir(app_handle: &AppHandle) -> CommandResult<PathBuf> {
    let dir = app_handle
        .path()
        .app_local_data_dir()
        .map_err(|error| CommandError::new("path", error.to_string()))?
        .join(".comlink");
    fs::create_dir_all(&dir).map_err(|error| CommandError::new("path", error.to_string()))?;
    Ok(dir)
}

fn log_scan_failure(app_handle: &AppHandle, entry: Value) {
    let Ok(path) = comlink_dir(app_handle).map(|dir| dir.join(SCAN_LOG_FILE)) else {
        return;
    };

    let mut existing = fs::read_to_string(&path)
        .ok()
        .and_then(|body| serde_json::from_str::<Vec<Value>>(&body).ok())
        .unwrap_or_default();
    existing.push(entry);
    let keep_from = existing.len().saturating_sub(100);
    let trimmed = existing.split_off(keep_from);
    let _ = fs::write(
        path,
        serde_json::to_string_pretty(&trimmed).unwrap_or_else(|_| String::from("[]")),
    );
}

async fn ensure_comlink_binary(
    app_handle: &AppHandle,
    runtime: &mut BackendRuntime,
) -> CommandResult<PathBuf> {
    if let Some(path) = find_existing_comlink_binary(app_handle, runtime) {
        return Ok(path);
    }

    let root = comlink_dir(app_handle)?;
    let path = download_latest_comlink_binary(&root).await?;
    runtime.comlink_binary = Some(path.clone());
    Ok(path)
}

fn find_existing_comlink_binary(
    app_handle: &AppHandle,
    runtime: &mut BackendRuntime,
) -> Option<PathBuf> {
    let candidates = comlink_candidate_filenames();
    for root in comlink_search_roots(app_handle) {
        for candidate in &candidates {
            let path = root.join(candidate);
            if looks_like_comlink_binary(&path) {
                runtime.comlink_binary = Some(path.clone());
                return Some(path);
            }
        }
        if let Some(path) = find_local_comlink_binary_in_root(&root) {
            runtime.comlink_binary = Some(path.clone());
            return Some(path);
        }
    }

    None
}

fn comlink_search_roots(app_handle: &AppHandle) -> Vec<PathBuf> {
    let mut roots = Vec::<PathBuf>::new();
    if let Ok(dir) = comlink_dir(app_handle) {
        roots.push(dir);
    }
    if let Some(dir) = app_data_root_from_runtime_path_hint() {
        roots.push(dir);
    }
    if let Ok(current_dir) = std::env::current_dir() {
        roots.push(current_dir.join(".comlink"));
        roots.push(current_dir.join("comlink"));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            roots.push(parent.join(".comlink"));
            roots.push(parent.join("comlink"));
        }
    }
    if let Ok(home) = std::env::var("USERPROFILE") {
        roots.push(PathBuf::from(home).join("comlink"));
    }

    let mut unique = Vec::<PathBuf>::new();
    for root in roots {
        if !unique.iter().any(|existing| existing == &root) {
            unique.push(root);
        }
    }
    unique
}

fn comlink_candidate_filenames() -> Vec<String> {
    #[cfg(windows)]
    {
        vec![
            String::from("swgoh-comlink.exe"),
            String::from("swgoh-comlink-win.exe"),
        ]
    }
    #[cfg(not(windows))]
    {
        vec![String::from("swgoh-comlink")]
    }
}

async fn download_latest_comlink_binary(root: &Path) -> CommandResult<PathBuf> {
    fs::create_dir_all(root).map_err(|error| CommandError::new("path", error.to_string()))?;

    let (os_name, arch, canonical_name, archive_hints) = comlink_platform_info()?;
    let canonical_path = root.join(&canonical_name);
    if looks_like_comlink_binary(&canonical_path) {
        mark_comlink_binary_executable(&canonical_path)?;
        return Ok(canonical_path);
    }

    if let Some(versioned) = find_local_comlink_binary_in_root(root) {
        copy_binary_to_canonical(&versioned, &canonical_path)?;
        return Ok(canonical_path);
    }

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(25))
        .user_agent(APP_NAME)
        .build()
        .map_err(|error| CommandError::new("http_client", error.to_string()))?;
    let release = client
        .get(COMLINK_RELEASE_API)
        .send()
        .await
        .map_err(|error| {
            CommandError::new(
                "comlink_release",
                format!("Could not fetch swgoh-comlink release info: {error}"),
            )
        })?
        .error_for_status()
        .map_err(|error| CommandError::new("comlink_release", error.to_string()))?
        .json::<Value>()
        .await
        .map_err(|error| CommandError::new("comlink_release", error.to_string()))?;

    let assets = release
        .get("assets")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            CommandError::new(
                "comlink_release",
                "GitHub did not return any release assets for swgoh-comlink.",
            )
        })?;

    let mut ranked_assets = assets
        .iter()
        .filter_map(|asset| {
            let name = asset.get("name")?.as_str()?;
            let url = asset.get("browser_download_url")?.as_str()?;
            let score = score_comlink_asset(name, &os_name, &arch, &archive_hints);
            Some((score, name.to_string(), url.to_string()))
        })
        .collect::<Vec<_>>();
    ranked_assets.sort_by(|left, right| right.0.cmp(&left.0));

    let Some((best_score, asset_name, asset_url)) = ranked_assets.into_iter().next() else {
        return Err(CommandError::new(
            "comlink_release",
            "No downloadable swgoh-comlink assets were found in the latest GitHub release.",
        ));
    };
    if best_score < 5 {
        return Err(CommandError::new(
            "comlink_release",
            format!(
                "No matching swgoh-comlink asset was found for {os_name}-{arch}. Download it manually from the official releases page if needed."
            ),
        ));
    }

    let archive_bytes = client
        .get(&asset_url)
        .send()
        .await
        .map_err(|error| {
            CommandError::new(
                "comlink_download",
                format!("Could not download swgoh-comlink asset '{asset_name}': {error}"),
            )
        })?
        .error_for_status()
        .map_err(|error| CommandError::new("comlink_download", error.to_string()))?
        .bytes()
        .await
        .map_err(|error| CommandError::new("comlink_download", error.to_string()))?;

    extract_comlink_archive(&asset_name, archive_bytes.as_ref(), root)?;

    if let Some(extracted) = find_local_comlink_binary_in_root(root) {
        copy_binary_to_canonical(&extracted, &canonical_path)?;
        return Ok(canonical_path);
    }

    Err(CommandError::new(
        "comlink_binary",
        "swgoh-comlink downloaded successfully, but no runnable binary was found after extraction.",
    ))
}

fn comlink_platform_info() -> CommandResult<(String, String, String, Vec<String>)> {
    let os_name = match std::env::consts::OS {
        "windows" => "win",
        "macos" => "macos",
        "linux" => "linux",
        other => {
            return Err(CommandError::new(
                "comlink_platform",
                format!("Unsupported platform for swgoh-comlink: {other}"),
            ))
        }
    };
    let arch = match std::env::consts::ARCH {
        "x86_64" | "amd64" => "x64",
        "aarch64" | "arm64" => "arm64",
        other if other.contains("arm") => "arm64",
        _ => "x64",
    };
    let canonical_name = if cfg!(windows) {
        String::from("swgoh-comlink.exe")
    } else {
        String::from("swgoh-comlink")
    };
    let archive_hints = if os_name == "linux" {
        vec![String::from(".tgz"), String::from(".tar.gz")]
    } else {
        vec![String::from(".zip")]
    };
    Ok((
        os_name.to_string(),
        arch.to_string(),
        canonical_name,
        archive_hints,
    ))
}

fn score_comlink_asset(name: &str, os_name: &str, arch: &str, archive_hints: &[String]) -> i64 {
    let lower = name.to_lowercase();
    let mut score = 0;
    if lower.contains(os_name) {
        score += 10;
    }
    if lower.contains(arch) {
        score += 5;
    }
    if lower.contains("comlink") {
        score += 2;
    }
    if archive_hints.iter().any(|ext| lower.ends_with(ext) || lower.contains(ext)) {
        score += 3;
    }
    score
}

fn extract_comlink_archive(asset_name: &str, bytes: &[u8], root: &Path) -> CommandResult<()> {
    let lower = asset_name.to_lowercase();
    if lower.ends_with(".zip") {
        let cursor = Cursor::new(bytes.to_vec());
        let mut archive =
            ZipArchive::new(cursor).map_err(|error| CommandError::new("comlink_extract", error.to_string()))?;
        archive
            .extract(root)
            .map_err(|error| CommandError::new("comlink_extract", error.to_string()))?;
        return Ok(());
    }
    if lower.ends_with(".tgz") || lower.ends_with(".tar.gz") {
        let decoder = GzDecoder::new(bytes);
        let mut archive = Archive::new(decoder);
        archive
            .unpack(root)
            .map_err(|error| CommandError::new("comlink_extract", error.to_string()))?;
        return Ok(());
    }
    Err(CommandError::new(
        "comlink_extract",
        format!("Unsupported swgoh-comlink archive type: {asset_name}"),
    ))
}

fn copy_binary_to_canonical(source: &Path, canonical_path: &Path) -> CommandResult<()> {
    if source != canonical_path {
        if let Some(parent) = canonical_path.parent() {
            fs::create_dir_all(parent)
                .map_err(|error| CommandError::new("path", error.to_string()))?;
        }
        if canonical_path.exists() {
            let _ = fs::remove_file(canonical_path);
        }
        fs::copy(source, canonical_path).map_err(|error| {
            CommandError::new(
                "comlink_binary",
                format!(
                    "Could not copy swgoh-comlink into '{}': {error}",
                    canonical_path.display()
                ),
            )
        })?;
    }
    mark_comlink_binary_executable(canonical_path)?;
    Ok(())
}

fn mark_comlink_binary_executable(path: &Path) -> CommandResult<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let metadata = fs::metadata(path).map_err(|error| {
            CommandError::new(
                "comlink_binary",
                format!("Could not inspect swgoh-comlink binary '{}': {error}", path.display()),
            )
        })?;
        let mut permissions = metadata.permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(path, permissions).map_err(|error| {
            CommandError::new(
                "comlink_binary",
                format!("Could not mark swgoh-comlink as executable: {error}"),
            )
        })?;
    }
    #[cfg(not(unix))]
    {
        let _ = path;
    }
    Ok(())
}

fn find_local_comlink_binary_in_root(root: &Path) -> Option<PathBuf> {
    if !root.exists() {
        return None;
    }

    let mut matches = Vec::<PathBuf>::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            if looks_like_comlink_binary(&path) {
                matches.push(path);
            }
        }
    }

    matches.sort_by_key(|path| path.to_string_lossy().len());
    matches.into_iter().next()
}

fn looks_like_comlink_binary(path: &Path) -> bool {
    if !path.is_file() {
        return false;
    }
    let Some(name) = path.file_name().map(|value| value.to_string_lossy().to_lowercase()) else {
        return false;
    };
    if !name.contains("swgoh-comlink") {
        return false;
    }
    if [
        ".zip",
        ".tgz",
        ".tar.gz",
        ".tar",
        ".gz",
        ".json",
        ".yaml",
        ".yml",
        ".html",
    ]
    .iter()
    .any(|suffix| name.ends_with(suffix))
    {
        return false;
    }

    #[cfg(windows)]
    {
        return name.ends_with(".exe");
    }

    #[cfg(not(windows))]
    {
        true
    }
}

fn managed_child_running(runtime: &mut BackendRuntime) -> bool {
    let Some(child) = runtime.comlink_child.as_mut() else {
        return false;
    };
    child.try_wait().ok().flatten().is_none()
}

fn drain_child_pipes(child: &mut Child) {
    if let Some(stdout) = child.stdout.take() {
        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for _ in reader.lines() {}
        });
    }
    if let Some(stderr) = child.stderr.take() {
        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for _ in reader.lines() {}
        });
    }
}

fn normalize_guild_summary(guild_payload: &Value) -> CommandResult<GuildSummary> {
    let root = guild_payload.get("guild").unwrap_or(guild_payload);
    let profile = root
        .get("profile")
        .or_else(|| root.get("data"))
        .or_else(|| root.get("guildInfo"))
        .unwrap_or(&Value::Null);
    let members = root
        .get("member")
        .or_else(|| root.get("members"))
        .or_else(|| root.get("roster"))
        .or_else(|| profile.get("member"))
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    if members.is_empty() {
        return Err(CommandError::new(
            "guild_payload",
            "Guild found but no members were returned by comlink.",
        ));
    }

    let name = first_non_empty_string(profile, &["name", "guildName"])
        .or_else(|| first_non_empty_string(root, &["name", "guildName"]))
        .unwrap_or_else(|| String::from("Unknown Guild"));
    let mut gp = extract_i64_from_paths(
        profile,
        &[&["guildPower"], &["galacticPower"], &["galactic_power"]],
    )
    .or_else(|| {
        extract_i64_from_paths(root, &[&["guildPower"], &["galacticPower"], &["galactic_power"]])
    })
    .unwrap_or(0);

    let normalized_members = members
        .iter()
        .map(|member| {
            let display_name = extract_member_display_name(member);
            let player_id = extract_member_player_id(member);
            let ally_code = extract_member_scan_key(member).unwrap_or_else(|| player_id.clone());
            let galactic_power = extract_member_gp(member);

            GuildMember {
                player_id,
                ally_code,
                display_name,
                galactic_power,
            }
        })
        .collect::<Vec<_>>();

    if gp <= 0 {
        gp = normalized_members.iter().map(|member| member.galactic_power).sum();
    }

    Ok(GuildSummary {
        name,
        gp,
        members: normalized_members,
    })
}

fn extract_member_display_name(member: &Value) -> String {
    first_non_empty_string(
        member,
        &[
            "playerName",
            "name",
            "playerInfo.playerName",
            "player.playerName",
            "player.name",
        ],
    )
    .unwrap_or_else(|| String::from("?"))
}

fn extract_member_player_id(member: &Value) -> String {
    first_non_empty_string(
        member,
        &[
            "playerId",
            "memberExternalId",
            "externalId",
            "player.playerId",
            "player.memberExternalId",
            "player.externalId",
        ],
    )
    .unwrap_or_default()
}

fn extract_member_scan_key(member: &Value) -> Option<String> {
    first_non_empty_string(
        member,
        &[
            "allyCode",
            "allycode",
            "ally_code",
            "playerId",
            "memberExternalId",
            "externalId",
            "player.allyCode",
            "player.allycode",
            "player.ally_code",
            "player.playerId",
            "player.memberExternalId",
            "player.externalId",
        ],
    )
    .map(|value| normalize_scan_key(&value))
    .filter(|value| !value.is_empty())
}

fn extract_member_gp(member: &Value) -> i64 {
    if let Some(value) = extract_i64(member.get("galacticPower")) {
        return value;
    }
    match member.get("memberContribution") {
        Some(Value::Array(contributions)) => contributions
            .iter()
            .find(|entry| {
                extract_i64(entry.get("type")).unwrap_or_default() == 1
                    || first_non_empty_string(entry, &["contributionType"])
                        .as_deref()
                        .map(|value| value == "GALACTIC_POWER")
                        .unwrap_or(false)
            })
            .and_then(|entry| {
                extract_i64(entry.get("currentValue"))
                    .or_else(|| extract_i64(entry.get("lifetimeValue")))
            })
            .unwrap_or(0),
        Some(other) => extract_i64(Some(other)).unwrap_or(0),
        None => 0,
    }
}

fn load_localization_caches(root: Option<&Path>, runtime: &mut BackendRuntime) {
    let Some(root) = root else {
        return;
    };
    if runtime.unit_name_map.is_empty() {
        if let Ok(body) = fs::read_to_string(root.join(UNIT_NAMES_CACHE_FILE)) {
            if let Ok(map) = serde_json::from_str::<HashMap<String, String>>(&body) {
                runtime.unit_name_map = map;
            }
        }
    }
    if runtime.ability_name_map.is_empty() {
        if let Ok(body) = fs::read_to_string(root.join(ABILITY_NAMES_CACHE_FILE)) {
            if let Ok(map) = serde_json::from_str::<HashMap<String, String>>(&body) {
                runtime.ability_name_map = map;
            }
        }
    }
    if runtime.skill_meta_map.is_empty() {
        if let Ok(body) = fs::read_to_string(root.join(SKILL_META_CACHE_FILE)) {
            if let Ok(map) = serde_json::from_str::<HashMap<String, SkillMeta>>(&body) {
                runtime.skill_meta_map = map
                    .into_iter()
                    .map(|(key, value)| (normalize_loc_key(&key), value))
                    .collect();
            }
        }
    }
    if runtime.unit_skill_reference_map.is_empty() {
        if let Ok(body) = fs::read_to_string(root.join(UNIT_SKILL_REFS_CACHE_FILE)) {
            if let Ok(map) = serde_json::from_str::<HashMap<String, Vec<String>>>(&body) {
                runtime.unit_skill_reference_map = normalize_string_vec_map(map);
            }
        }
    }
    if runtime.unit_crew_map.is_empty() {
        if let Ok(body) = fs::read_to_string(root.join(UNIT_CREW_MAP_CACHE_FILE)) {
            if let Ok(map) = serde_json::from_str::<HashMap<String, Vec<String>>>(&body) {
                runtime.unit_crew_map = normalize_string_vec_map(map);
            }
        }
    }
    if runtime.unit_crew_skill_reference_map.is_empty() {
        if let Ok(body) = fs::read_to_string(root.join(UNIT_CREW_SKILL_REFS_CACHE_FILE)) {
            if let Ok(map) = serde_json::from_str::<HashMap<String, Vec<String>>>(&body) {
                runtime.unit_crew_skill_reference_map = normalize_string_vec_map(map);
            }
        }
    }

    if !runtime.unit_skill_reference_map.is_empty() {
        rebuild_known_combat_type_indexes(runtime);
    }
}

fn cache_localization_maps(root: Option<&Path>, runtime: &BackendRuntime) {
    let Some(root) = root else {
        return;
    };
    let _ = fs::create_dir_all(root);
    if !runtime.unit_name_map.is_empty() {
        let _ = fs::write(
            root.join(UNIT_NAMES_CACHE_FILE),
            serde_json::to_string_pretty(&runtime.unit_name_map).unwrap_or_default(),
        );
    }
    if !runtime.ability_name_map.is_empty() {
        let _ = fs::write(
            root.join(ABILITY_NAMES_CACHE_FILE),
            serde_json::to_string_pretty(&runtime.ability_name_map).unwrap_or_default(),
        );
    }
    if !runtime.skill_meta_map.is_empty() {
        let _ = fs::write(
            root.join(SKILL_META_CACHE_FILE),
            serde_json::to_string_pretty(&runtime.skill_meta_map).unwrap_or_default(),
        );
    }
    if !runtime.unit_skill_reference_map.is_empty() {
        let _ = fs::write(
            root.join(UNIT_SKILL_REFS_CACHE_FILE),
            serde_json::to_string_pretty(&runtime.unit_skill_reference_map).unwrap_or_default(),
        );
    }
    if !runtime.unit_crew_map.is_empty() {
        let _ = fs::write(
            root.join(UNIT_CREW_MAP_CACHE_FILE),
            serde_json::to_string_pretty(&runtime.unit_crew_map).unwrap_or_default(),
        );
    }
    if !runtime.unit_crew_skill_reference_map.is_empty() {
        let _ = fs::write(
            root.join(UNIT_CREW_SKILL_REFS_CACHE_FILE),
            serde_json::to_string_pretty(&runtime.unit_crew_skill_reference_map)
                .unwrap_or_default(),
        );
    }
}

fn normalize_string_vec_map(map: HashMap<String, Vec<String>>) -> HashMap<String, Vec<String>> {
    map.into_iter()
        .map(|(key, values)| {
            (
                normalize_loc_key(&key),
                values
                    .into_iter()
                    .map(|value| value.trim().to_string())
                    .filter(|value| !value.is_empty())
                    .collect(),
            )
        })
        .collect()
}

fn rebuild_known_combat_type_indexes(runtime: &mut BackendRuntime) {
    runtime.known_ship_defids.clear();
    runtime.known_character_defids.clear();

    for unit_id in runtime.unit_skill_reference_map.keys() {
        let key = canonical_defid_key(unit_id);
        let is_ship = runtime
            .unit_crew_map
            .get(&normalize_loc_key(unit_id))
            .map(|crew| !crew.is_empty())
            .unwrap_or(false);
        if is_ship {
            runtime.known_ship_defids.insert(key);
        } else {
            runtime.known_character_defids.insert(key);
        }
    }
}

fn localization_maps_ready(runtime: &BackendRuntime) -> bool {
    !runtime.unit_name_map.is_empty()
        && !runtime.ability_name_map.is_empty()
        && !runtime.skill_meta_map.is_empty()
        && !runtime.unit_skill_reference_map.is_empty()
        && !runtime.unit_crew_map.is_empty()
        && !runtime.unit_crew_skill_reference_map.is_empty()
}

fn app_data_root_from_runtime_path_hint() -> Option<PathBuf> {
    let local_app_data = std::env::var("LOCALAPPDATA").ok()?;
    Some(PathBuf::from(local_app_data).join("com.swgoh-toolkit.app").join(".comlink"))
}

fn extract_localization_bundle(value: &Value) -> HashMap<String, String> {
    if let Some(bundle) = value.get("localizationBundle") {
        return extract_localization_bundle(bundle);
    }
    if let Some(map) = value.as_object() {
        return map
            .iter()
            .filter_map(|(key, value)| value.as_str().map(|text| (key.clone(), text.to_string())))
            .collect();
    }
    if let Some(text) = value.as_str() {
        return parse_localization_bundle_string(text);
    }
    HashMap::new()
}

fn parse_localization_bundle_string(text: &str) -> HashMap<String, String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return HashMap::new();
    }

    if let Ok(raw) = BASE64_STANDARD.decode(trimmed.as_bytes()) {
        let parsed = parse_localization_archive_or_text(&raw);
        if !parsed.is_empty() {
            return parsed;
        }
    }

    parse_localization_archive_or_text(trimmed.as_bytes())
}

fn parse_localization_archive_or_text(raw: &[u8]) -> HashMap<String, String> {
    if let Ok(mut archive) = ZipArchive::new(Cursor::new(raw)) {
        let mut selected_index = None;
        for index in 0..archive.len() {
            let Ok(file) = archive.by_index(index) else {
                continue;
            };
            if file
                .name()
                .to_ascii_uppercase()
                .ends_with("LOC_ENG_US.TXT")
            {
                selected_index = Some(index);
                break;
            }
            if selected_index.is_none() {
                selected_index = Some(index);
            }
        }
        if let Some(index) = selected_index {
            if let Ok(mut file) = archive.by_index(index) {
                let mut text = String::new();
                if file.read_to_string(&mut text).is_ok() {
                    let parsed = parse_localization_text(&text);
                    if !parsed.is_empty() {
                        return parsed;
                    }
                }
            }
        }
    }

    String::from_utf8(raw.to_vec())
        .ok()
        .map(|text| parse_localization_text(&text))
        .unwrap_or_default()
}

fn parse_localization_text(text: &str) -> HashMap<String, String> {
    let mut out = HashMap::new();
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let Some((key, value)) = trimmed
            .split_once('|')
            .or_else(|| trimmed.split_once('='))
        else {
            continue;
        };
        let clean_key = normalize_loc_key(key);
        let clean_value = value.trim().trim_matches('"').replace("\\\"", "\"");
        if !clean_key.is_empty() && !clean_value.is_empty() {
            out.insert(clean_key, clean_value);
        }
    }
    out
}

fn merge_localization_bundle(
    runtime: &mut BackendRuntime,
    bundle: HashMap<String, String>,
) -> (usize, usize) {
    let mut added_units = 0usize;
    let mut added_abilities = 0usize;
    for (key, value) in bundle {
        let normalized_key = normalize_loc_key(&key);
        runtime
            .localization_value_map
            .insert(normalized_key.clone(), value.clone());
        runtime
            .localization_value_map
            .insert(normalized_key.replace('_', ""), value.clone());

        if normalized_key.starts_with("UNIT_") && normalized_key.ends_with("_NAME") {
            let def_id = normalized_key
                .trim_start_matches("UNIT_")
                .trim_end_matches("_NAME")
                .to_string();
            if runtime.unit_name_map.get(&def_id) != Some(&value) {
                runtime.unit_name_map.insert(def_id, value);
                added_units += 1;
            }
        } else if normalized_key.ends_with("_NAME") {
            let ability_id = normalized_key.trim_end_matches("_NAME");
            if !ability_id.is_empty() {
                let before = runtime.ability_name_map.len();
                store_ability_name(runtime, ability_id, &value);
                if runtime.ability_name_map.len() > before {
                    added_abilities += 1;
                }
            }
        }
    }

    (added_units, added_abilities)
}

fn legacy_unit_data() -> &'static LegacyUnitData {
    LEGACY_UNIT_DATA.get_or_init(|| {
        let mut playable_names = HashMap::<String, String>::new();
        let mut alias_by_name = HashMap::<String, String>::new();
        let mut ship_defid_keys = HashSet::<String>::new();
        let mut character_defid_keys = HashSet::<String>::new();
        let mut name_index = HashMap::<String, Vec<String>>::new();

        let mut raw_playable = parse_legacy_js_string_map(LEGACY_PLANNER_SOURCE, "const UNIT_NAMES = {");
        raw_playable.extend(parse_legacy_js_string_map(
            LEGACY_PLANNER_SOURCE,
            "const EXTRA_UNIT_NAMES = {",
        ));
        let ship_map =
            parse_legacy_js_string_map(LEGACY_PLANNER_SOURCE, "const SHIP_NAME_BY_DEFID = {");
        raw_playable.extend(ship_map.clone());

        for (def_id, name) in raw_playable {
            let canonical = normalize_loc_key(&canonical_defid(&def_id));
            if canonical.is_empty() || name.trim().is_empty() {
                continue;
            }
            playable_names
                .entry(canonical.clone())
                .or_insert_with(|| name.clone());
            playable_names
                .entry(canonical.replace('_', ""))
                .or_insert_with(|| name.clone());
            let normalized_name = normalize_unit_name_lookup(&name);
            if !normalized_name.is_empty() {
                name_index.entry(normalized_name).or_default().push(canonical.clone());
            }
        }

        for def_id in ship_map.keys() {
            ship_defid_keys.insert(canonical_defid_key(def_id));
        }
        for def_id in parse_legacy_js_string_array(
            LEGACY_PLANNER_SOURCE,
            "const KNOWN_SHIP_DEFIDS = new Set([",
            "].concat",
        ) {
            ship_defid_keys.insert(canonical_defid_key(&def_id));
        }

        for canonical in name_index.values().flatten() {
            let key = canonical_defid_key(canonical);
            if ship_defid_keys.contains(&key) {
                continue;
            }
            character_defid_keys.insert(key);
        }

        for (alias, def_id) in
            parse_legacy_js_string_map(LEGACY_PLANNER_SOURCE, "const UNIT_NAME_ALIASES = {")
        {
            let normalized_alias = normalize_unit_name_lookup(&alias);
            let canonical = normalize_loc_key(&canonical_defid(&def_id));
            if normalized_alias.is_empty() || canonical.is_empty() {
                continue;
            }
            alias_by_name.insert(normalized_alias.clone(), canonical.clone());
            if !name_index
                .entry(normalized_alias)
                .or_default()
                .iter()
                .any(|existing| existing == &canonical)
            {
                name_index
                    .entry(normalize_unit_name_lookup(&alias))
                    .or_default()
                    .push(canonical);
            }
        }

        for values in name_index.values_mut() {
            values.sort();
            values.dedup();
        }

        LegacyUnitData {
            playable_names,
            alias_by_name,
            ship_defid_keys,
            character_defid_keys,
            name_index,
        }
    })
}

fn parse_legacy_js_string_map(source: &str, marker: &str) -> HashMap<String, String> {
    let Some(block) = extract_legacy_block(source, marker, "\n};") else {
        return HashMap::new();
    };
    let mut out = HashMap::<String, String>::new();
    for line in block.lines() {
        let trimmed = line.trim().trim_end_matches(',');
        if trimmed.is_empty() || trimmed.starts_with("//") || trimmed.starts_with("...") {
            continue;
        }
        let Some((raw_key, raw_value)) = trimmed.split_once(':') else {
            continue;
        };
        let key = parse_legacy_js_key(raw_key.trim());
        let value = parse_legacy_js_string(raw_value.trim());
        if let (Some(key), Some(value)) = (key, value) {
            out.insert(key, value);
        }
    }
    out
}

fn parse_legacy_js_string_array(source: &str, marker: &str, end_marker: &str) -> Vec<String> {
    let Some(block) = extract_legacy_block(source, marker, end_marker) else {
        return Vec::new();
    };
    let mut out = Vec::<String>::new();
    for token in block.split(',') {
        let trimmed = token.trim();
        if trimmed.is_empty() || trimmed.starts_with("//") {
            continue;
        }
        if let Some(value) = parse_legacy_js_string(trimmed) {
            out.push(value);
        }
    }
    out
}

fn extract_legacy_block<'a>(source: &'a str, marker: &str, end_marker: &str) -> Option<&'a str> {
    let start = source.find(marker)? + marker.len();
    let remainder = &source[start..];
    let end = remainder.find(end_marker)?;
    Some(&remainder[..end])
}

fn parse_legacy_js_key(token: &str) -> Option<String> {
    if token.is_empty() {
        return None;
    }
    if token.starts_with('\'') || token.starts_with('"') {
        return parse_legacy_js_string(token);
    }
    Some(token.trim().to_string())
}

fn parse_legacy_js_string(token: &str) -> Option<String> {
    let trimmed = token.trim();
    let quote = trimmed.chars().next()?;
    if quote != '\'' && quote != '"' {
        return None;
    }
    let mut out = String::new();
    let mut escaped = false;
    for ch in trimmed.chars().skip(1) {
        if escaped {
            out.push(ch);
            escaped = false;
            continue;
        }
        if ch == '\\' {
            escaped = true;
            continue;
        }
        if ch == quote {
            return Some(out);
        }
        out.push(ch);
    }
    None
}

fn load_wiki_ops_names() -> CommandResult<HashMap<String, Vec<Vec<String>>>> {
    let marker = "_WIKI_OPS_DATA_B64 = \"\"\"";
    let Some(start) = LEGACY_OPS_FALLBACK.find(marker) else {
        return Err(CommandError::new(
            "ops_data",
            "Could not find the bundled wiki operations data block.",
        ));
    };
    let after_marker = &LEGACY_OPS_FALLBACK[start + marker.len()..];
    let after_prefix = after_marker
        .strip_prefix("\\\r\n")
        .or_else(|| after_marker.strip_prefix("\\\n"))
        .unwrap_or(after_marker);
    let Some(end) = after_prefix.find("\"\"\"") else {
        return Err(CommandError::new(
            "ops_data",
            "Could not find the end of the bundled wiki operations data block.",
        ));
    };
    let encoded = after_prefix[..end].lines().collect::<String>();
    let compressed = BASE64_STANDARD
        .decode(encoded.as_bytes())
        .map_err(|error| CommandError::new("ops_data", error.to_string()))?;
    let mut decoder = ZlibDecoder::new(compressed.as_slice());
    let mut json_text = String::new();
    decoder
        .read_to_string(&mut json_text)
        .map_err(|error| CommandError::new("ops_data", error.to_string()))?;
    serde_json::from_str::<HashMap<String, Vec<Vec<String>>>>(&json_text)
        .map_err(|error| CommandError::new("ops_data", error.to_string()))
}

fn zone_relic_by_planet() -> HashMap<&'static str, i64> {
    HashMap::from([
        ("mustafar", 5),
        ("corellia", 5),
        ("coruscant", 5),
        ("geonosis", 6),
        ("felucia", 6),
        ("bracca", 6),
        ("dathomir", 7),
        ("tatooine", 7),
        ("kashyyyk", 7),
        ("zeffo", 7),
        ("medstation", 8),
        ("kessel", 8),
        ("lothal", 8),
        ("mandalore", 8),
        ("malachor", 9),
        ("vandor", 9),
        ("kafrene", 9),
        ("deathstar", 9),
        ("hoth", 9),
        ("scarif", 9),
    ])
}

fn resolve_unit_name_to_defid(runtime: &BackendRuntime, name: &str) -> Option<String> {
    let legacy = legacy_unit_data();
    let raw = canonical_defid(name);
    let raw_key = canonical_defid_key(&raw);
    if runtime.known_ship_defids.contains(&raw_key)
        || runtime.known_character_defids.contains(&raw_key)
        || legacy.ship_defid_keys.contains(&raw_key)
        || legacy.character_defid_keys.contains(&raw_key)
        || legacy.playable_names.contains_key(&normalize_loc_key(&raw))
        || legacy
            .playable_names
            .contains_key(&normalize_loc_key(&raw).replace('_', ""))
    {
        return Some(raw);
    }

    let target = normalize_unit_name_lookup(name);
    if target.is_empty() {
        return None;
    }

    if let Some(def_id) = legacy.alias_by_name.get(&target) {
        return Some(def_id.clone());
    }

    let mut matches = HashSet::<String>::new();
    if let Some(def_ids) = legacy.name_index.get(&target) {
        matches.extend(def_ids.iter().cloned());
    }
    for (def_id, display_name) in &runtime.unit_name_map {
        if normalize_unit_name_lookup(display_name) == target {
            matches.insert(normalize_loc_key(&canonical_defid(def_id)));
        }
    }
    for roster in runtime.guild_rosters.values() {
        for unit in roster {
            if normalize_unit_name_lookup(&unit.name) == target {
                matches.insert(normalize_loc_key(&canonical_defid(&unit.def_id)));
            }
        }
    }

    if matches.len() == 1 {
        matches.into_iter().next()
    } else {
        None
    }
}

fn placeholder_ops_defid(name: &str) -> String {
    let clean = normalize_unit_name_lookup(name).to_uppercase();
    if clean.is_empty() {
        String::from("WIKI_UNKNOWN")
    } else {
        format!("WIKI_{clean}")
    }
}

fn is_ship_name_or_defid(runtime: &BackendRuntime, name: &str, def_id: &str) -> bool {
    let legacy = legacy_unit_data();
    let def_key = canonical_defid_key(def_id);
    if runtime.known_ship_defids.contains(&def_key) || legacy.ship_defid_keys.contains(&def_key) {
        return true;
    }
    if runtime.known_character_defids.contains(&def_key)
        || legacy.character_defid_keys.contains(&def_key)
    {
        return false;
    }

    let clean_name = normalize_unit_name_lookup(name);
    if clean_name.is_empty() {
        return false;
    }

    if let Some(def_id) = legacy.alias_by_name.get(&clean_name) {
        let alias_key = canonical_defid_key(def_id);
        if legacy.ship_defid_keys.contains(&alias_key) {
            return true;
        }
        if legacy.character_defid_keys.contains(&alias_key) {
            return false;
        }
    }

    if let Some(def_ids) = legacy.name_index.get(&clean_name) {
        if def_ids.len() == 1 {
            let name_key = canonical_defid_key(&def_ids[0]);
            if legacy.ship_defid_keys.contains(&name_key) {
                return true;
            }
            if legacy.character_defid_keys.contains(&name_key) {
                return false;
            }
        }
    }

    for ship_def_id in &runtime.known_ship_defids {
        let display_name = lookup_unit_name(runtime, ship_def_id, ship_def_id);
        if normalize_unit_name_lookup(&display_name) == clean_name {
            return true;
        }
    }

    for roster in runtime.guild_rosters.values() {
        for unit in roster {
            if unit.combat_type == 2 && normalize_unit_name_lookup(&unit.name) == clean_name {
                return true;
            }
        }
    }

    false
}

fn lookup_unit_name(runtime: &BackendRuntime, def_id: &str, fallback: &str) -> String {
    let legacy = legacy_unit_data();
    let raw = canonical_defid(def_id);
    let normalized = normalize_loc_key(&raw);
    runtime
        .unit_name_map
        .get(&normalized)
        .cloned()
        .or_else(|| runtime.unit_name_map.get(&normalized.replace('_', "")).cloned())
        .or_else(|| legacy.playable_names.get(&normalized).cloned())
        .or_else(|| legacy.playable_names.get(&normalized.replace('_', "")).cloned())
        .unwrap_or_else(|| fallback.to_string())
}

fn lookup_ability_name(runtime: &BackendRuntime, skill_id: &str) -> String {
    let raw = skill_id.trim();
    let upper = normalize_loc_key(raw);
    let flat = upper.replace('_', "");
    let mut candidates = vec![raw.to_string(), upper.clone(), flat];

    let mut extend_with = |prefix: &str, suffix: &str| {
        let clean_suffix = normalize_loc_key(suffix);
        if clean_suffix.is_empty() {
            return;
        }
        candidates.push(format!("{prefix}_{clean_suffix}"));
        candidates.push(format!("{prefix}_{clean_suffix}_NAME"));
        candidates.push(format!("{prefix}{clean_suffix}"));
        candidates.push(format!("{prefix}{clean_suffix}_NAME"));
    };

    let lower = raw.to_lowercase();
    if let Some(suffix) = lower.strip_prefix("basicskill_") {
        extend_with("BASICABILITY", suffix);
    } else if let Some(suffix) = lower.strip_prefix("specialskill_") {
        extend_with("SPECIALABILITY", suffix);
    } else if let Some(suffix) = lower.strip_prefix("leaderskill_") {
        extend_with("LEADERABILITY", suffix);
    } else if let Some(suffix) = lower.strip_prefix("uniqueskill_") {
        extend_with("UNIQUEABILITY", suffix);
    } else if let Some(suffix) = lower.strip_prefix("contractskill_") {
        extend_with("CONTRACTABILITY", suffix);
        extend_with("PAYOUTABILITY", suffix);
        extend_with("CONTRACT", suffix);
    } else if let Some(suffix) = lower.strip_prefix("crew_") {
        extend_with("CREWABILITY", suffix);
    } else if let Some(suffix) = lower.strip_prefix("hardware_") {
        extend_with("HARDWAREABILITY", suffix);
    } else if let Some(suffix) = lower.strip_prefix("ultimateability_") {
        extend_with("ULTIMATEABILITY", suffix);
    }

    let mut seen = HashSet::<String>::new();
    for candidate in candidates {
        if candidate.is_empty() || !seen.insert(candidate.clone()) {
            continue;
        }
        if let Some(name) = runtime.ability_name_map.get(&candidate) {
            return name.clone();
        }
        let normalized = normalize_loc_key(&candidate);
        if let Some(name) = runtime.ability_name_map.get(&normalized) {
            return name.clone();
        }
        if let Some(name) = runtime.ability_name_map.get(&normalized.replace('_', "")) {
            return name.clone();
        }
    }

    fallback_ability_name(skill_id)
}

fn store_ability_name(runtime: &mut BackendRuntime, raw_id: &str, display_name: &str) {
    let key = normalize_loc_key(raw_id);
    if key.is_empty() || display_name.is_empty() {
        return;
    }
    runtime
        .ability_name_map
        .insert(raw_id.trim().to_string(), display_name.to_string());
    runtime
        .ability_name_map
        .insert(key.clone(), display_name.to_string());
    runtime
        .ability_name_map
        .insert(key.replace('_', ""), display_name.to_string());
}

fn lookup_localized_text(runtime: &BackendRuntime, key: &str) -> String {
    let normalized = normalize_loc_key(key);
    if normalized.is_empty() {
        return String::new();
    }
    runtime
        .localization_value_map
        .get(&normalized)
        .cloned()
        .or_else(|| runtime.localization_value_map.get(&normalized.replace('_', "")).cloned())
        .unwrap_or_default()
}

fn extract_skill_ids(value: Option<&Value>, first_only: bool) -> Vec<String> {
    let mut out = Vec::new();
    let mut seen = HashSet::<String>::new();
    let Some(values) = value.and_then(Value::as_array) else {
        return out;
    };

    for entry in values.iter().take(if first_only { 1 } else { values.len() }) {
        let skill_id = if let Some(map) = entry.as_object() {
            first_non_empty_string_from_map(map, &["skillId", "id", "abilityId"]).unwrap_or_default()
        } else {
            entry.as_str().unwrap_or_default().to_string()
        };
        if skill_id.is_empty() {
            continue;
        }
        let key = normalize_loc_key(&skill_id);
        if !seen.insert(key) {
            continue;
        }
        out.push(skill_id);
    }

    out
}

fn extract_speed(unit: &Value) -> i64 {
    let roots = [
        unit.get("unitStat"),
        unit.get("stat"),
        unit.get("stats"),
        unit.get("statList"),
    ];
    for root in roots.into_iter().flatten() {
        let stats = if let Some(map) = root.as_object() {
            map.get("stat")
                .or_else(|| map.get("stats"))
                .or_else(|| map.get("statList"))
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default()
        } else if let Some(array) = root.as_array() {
            array.clone()
        } else {
            Vec::new()
        };

        for stat in stats {
            let stat_id = first_non_empty_string(
                &stat,
                &["unitStatId", "statId", "id", "statType"],
            )
            .unwrap_or_default();
            if stat_id != "5" && stat_id != "UNIT_STAT_SPEED" && stat_id.to_lowercase() != "speed" {
                continue;
            }
            if let Some(value) = extract_i64(stat.get("statValueDecimal"))
                .or_else(|| extract_i64(stat.get("value")))
                .or_else(|| extract_i64(stat.get("statValue")))
            {
                return value;
            }
            if let Some(list) = stat.get("statValueList").and_then(Value::as_array) {
                if let Some(value) = list.first().and_then(|entry| extract_i64(Some(entry))) {
                    return value;
                }
            }
        }
    }
    0
}

fn extract_unit_power(unit: &Value) -> i64 {
    extract_i64_from_paths(
        unit,
        &[
            &["gp"],
            &["power"],
            &["galacticPower"],
            &["unitPower"],
            &["currentPower"],
            &["stats", "gp"],
            &["stats", "power"],
            &["summary", "gp"],
            &["summary", "power"],
        ],
    )
    .unwrap_or(0)
}

fn normalize_ally_code_input(value: &str) -> String {
    value.replace('-', "").replace(' ', "").trim().to_string()
}

fn normalize_scan_key(value: &str) -> String {
    let raw = value.trim();
    let compact = raw.replace('-', "").replace(' ', "");
    if compact.chars().all(|ch| ch.is_ascii_digit()) {
        compact
    } else {
        raw.to_string()
    }
}

fn canonical_defid(value: &str) -> String {
    value.split(':').next().unwrap_or_default().trim().to_string()
}

fn canonical_defid_key(value: &str) -> String {
    canonical_defid(value).to_uppercase().replace('_', "")
}

fn infer_combat_type(runtime: &BackendRuntime, def_id: &str, raw_ctype: Option<&Value>) -> i64 {
    let legacy = legacy_unit_data();
    let key = canonical_defid_key(def_id);
    if runtime.known_ship_defids.contains(&key) || legacy.ship_defid_keys.contains(&key) {
        return 2;
    }
    if runtime.known_character_defids.contains(&key) || legacy.character_defid_keys.contains(&key) {
        return 1;
    }
    if let Some(raw_ctype) = raw_ctype {
        if let Some(value) = extract_i64(Some(raw_ctype)) {
            return if value == 2 { 2 } else { 1 };
        }
        if let Some(text) = raw_ctype.as_str() {
            let upper = text.trim().to_uppercase();
            if upper == "2" || upper == "SHIP" || upper == "FLEET" {
                return 2;
            }
        }
    }
    1
}

fn normalize_loc_key(value: &str) -> String {
    value.trim().to_uppercase()
}

fn normalize_unit_name_lookup(value: &str) -> String {
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

fn infer_skill_kind(skill_id: &str) -> String {
    let lower = skill_id.trim().to_lowercase();
    if lower.starts_with("basicskill") {
        String::from("basic")
    } else if lower.starts_with("specialskill") {
        String::from("special")
    } else if lower.starts_with("leaderskill") {
        String::from("leader")
    } else if lower.starts_with("uniqueskill") {
        String::from("unique")
    } else if lower.starts_with("contract") {
        String::from("contract")
    } else if lower.starts_with("crew") {
        String::from("crew")
    } else if lower.starts_with("hardware") {
        String::from("hardware")
    } else if lower.starts_with("ultimateability") {
        String::from("ultimate")
    } else {
        String::from("ability")
    }
}

fn fallback_ability_name(skill_id: &str) -> String {
    match infer_skill_kind(skill_id).as_str() {
        "basic" => String::from("Basic"),
        "special" => String::from("Special"),
        "leader" => String::from("Leader"),
        "unique" => String::from("Unique"),
        "contract" => String::from("Contract"),
        "crew" => String::from("Crew"),
        "hardware" => String::from("Hardware"),
        "ultimate" => String::from("Ultimate"),
        _ => String::from("Ability"),
    }
}

fn skill_level_from_tier(raw_tier: i64, max_tier: i64) -> i64 {
    if max_tier > 0 && max_tier <= 3 {
        if raw_tier <= 0 {
            return 2;
        }
        return (raw_tier + 2).min(max_tier);
    }
    if raw_tier > 0 {
        raw_tier + 2
    } else {
        0
    }
}

fn first_non_empty_string(value: &Value, paths: &[&str]) -> Option<String> {
    for path in paths {
        let mut cursor = value;
        let mut found = true;
        for segment in path.split('.') {
            let Some(next) = cursor.get(segment) else {
                found = false;
                break;
            };
            cursor = next;
        }
        if found {
            if let Some(text) = cursor.as_str().map(str::trim).filter(|text| !text.is_empty()) {
                return Some(text.to_string());
            }
        }
    }
    None
}

fn first_non_empty_string_from_map(map: &Map<String, Value>, paths: &[&str]) -> Option<String> {
    first_non_empty_string(&Value::Object(map.clone()), paths)
}

fn extract_first_string(value: &Value, paths: &[&[&str]]) -> Option<String> {
    for path in paths {
        let mut cursor = value;
        let mut found = true;
        for segment in *path {
            let Some(next) = cursor.get(*segment) else {
                found = false;
                break;
            };
            cursor = next;
        }
        if found {
            if let Some(text) = cursor.as_str().map(str::trim).filter(|text| !text.is_empty()) {
                return Some(text.to_string());
            }
        }
    }
    None
}

fn extract_i64(value: Option<&Value>) -> Option<i64> {
    match value? {
        Value::Number(number) => number.as_i64().or_else(|| number.as_f64().map(|value| value as i64)),
        Value::String(text) => text
            .replace(',', "")
            .trim()
            .parse::<f64>()
            .ok()
            .map(|value| value as i64),
        _ => None,
    }
}

fn extract_i64_with_default(value: &Value, paths: &[&str], default: i64) -> i64 {
    for path in paths {
        if let Some(found) = extract_i64(value.get(*path)) {
            return found;
        }
    }
    default
}

fn extract_i64_from_paths(value: &Value, paths: &[&[&str]]) -> Option<i64> {
    for path in paths {
        let mut cursor = value;
        let mut found = true;
        for segment in *path {
            let Some(next) = cursor.get(*segment) else {
                found = false;
                break;
            };
            cursor = next;
        }
        if found {
            if let Some(number) = extract_i64(Some(cursor)) {
                return Some(number);
            }
        }
    }
    None
}

fn truthy(value: Option<&Value>) -> bool {
    match value {
        Some(Value::Bool(flag)) => *flag,
        Some(Value::Number(number)) => number.as_i64().unwrap_or(0) != 0,
        Some(Value::String(text)) => {
            let lower = text.trim().to_lowercase();
            lower == "true" || lower == "1"
        }
        _ => false,
    }
}
