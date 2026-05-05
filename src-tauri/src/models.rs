use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

pub type GuildRosters = HashMap<String, Vec<SimplifiedRosterUnit>>;
pub type OpsDefinitions = HashMap<String, Vec<Vec<PlatoonRequirement>>>;
pub type PlatoonAnalysisMap = HashMap<String, Vec<PlatoonAnalysisEntry>>;
pub type GuideTbOmicronMap = HashMap<String, Vec<GuideTbOmicron>>;
pub type PlannerPlanetCardMap = HashMap<String, PlannerPlanetCard>;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct GuildImportRequest {
    pub ally_code: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ScanRosterRequest {
    pub ally_code: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct GuildScanMember {
    pub key: String,
    pub display_name: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct BulkScanGuildRostersRequest {
    pub members: Vec<GuildScanMember>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct SaveAppStateRequest {
    pub snapshot: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ImportSessionRequest {
    pub guild_rosters: GuildRosters,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerPlanetState {
    pub cm_rate_override: Option<f64>,
    pub fleet_rate_override: Option<f64>,
    pub cm_count_override: Option<f64>,
    pub fleet_count_override: Option<f64>,
    pub preloaded: i64,
    pub sm_ready: bool,
    pub sm_count: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerSettings {
    pub guild_gp: i64,
    pub guild_members: i64,
    pub active_members: i64,
    pub cm_mode: String,
    pub undep_mode: String,
    pub cm_base: f64,
    pub cm_falloff: f64,
    pub fleet_base: f64,
    pub fleet_falloff: f64,
    pub daily_undep: Vec<f64>,
    pub planet_state: HashMap<String, PlannerPlanetState>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerProjectionRequest {
    pub settings: PlannerSettings,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerOptimizationRequest {
    pub settings: PlannerSettings,
    pub algorithm: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct GuildMember {
    pub player_id: String,
    pub ally_code: String,
    pub display_name: String,
    pub galactic_power: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct GuildSummary {
    pub name: String,
    pub gp: i64,
    pub members: Vec<GuildMember>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GuildImportResponse {
    pub summary: GuildSummary,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct SimplifiedSkillRow {
    pub id: String,
    pub skill_id: String,
    pub name: String,
    pub tier: i64,
    pub level: i64,
    pub max_tier: i64,
    pub kind: String,
    pub is_zeta: bool,
    pub is_omicron: bool,
    pub omicron_area: i64,
    pub has_zeta: bool,
    pub has_omicron: bool,
    pub unlocked: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct SimplifiedRosterUnit {
    pub def_id: String,
    pub name: String,
    pub rarity: i64,
    pub gear: i64,
    pub relic: i64,
    pub combat_type: i64,
    pub mods_present: bool,
    pub speed: i64,
    pub power: i64,
    pub zetas: i64,
    pub omicrons: i64,
    pub skills: Vec<SimplifiedSkillRow>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RosterScanResponse {
    pub ally_code: String,
    pub roster: Vec<SimplifiedRosterUnit>,
    pub units: usize,
    pub skipped: usize,
    pub power_ready: bool,
    pub power_error: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ScanFailure {
    pub key: String,
    pub display_name: String,
    pub error: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct BulkRosterScanResponse {
    pub scanned_members: usize,
    pub failed_members: Vec<ScanFailure>,
    pub guild_rosters: GuildRosters,
    pub power_ready: bool,
    pub power_error: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct GuildScanProgressEvent {
    pub phase: String,
    pub total_members: usize,
    pub completed_members: usize,
    pub successful_members: usize,
    pub failed_members: usize,
    pub current_key: Option<String>,
    pub current_display_name: Option<String>,
    pub last_error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerOptimizationProgressEvent {
    pub phase: String,
    pub selected_algorithm: String,
    pub algorithm: String,
    pub overall_fraction: f64,
    pub algorithm_fraction: f64,
    pub best_score: i64,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerMissionDefinition {
    pub id: String,
    pub label: String,
    pub mission_type: String,
    pub points_single: Option<i64>,
    pub points: Option<i64>,
    pub reward_text: Option<String>,
    pub units_text: String,
    pub note: Option<String>,
    pub unlocks: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerPlanetDefinition {
    pub id: String,
    pub name: String,
    pub align: String,
    pub chain: String,
    pub zone: i64,
    pub phase: i64,
    pub cm_points: i64,
    pub fleet_points: i64,
    pub ops_val: i64,
    pub stars: Vec<i64>,
    pub min_relic: i64,
    pub unlocked_by: Option<String>,
    pub unlocked_at: Option<i64>,
    pub sm_label: Option<String>,
    pub sm_threshold: Option<i64>,
    pub missions: Vec<PlannerMissionDefinition>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerAlgorithmMeta {
    pub id: String,
    pub label: String,
    pub quality: String,
    pub complexity: String,
    pub runtime: String,
    pub description: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerReferenceResponse {
    pub planets: Vec<PlannerPlanetDefinition>,
    pub algorithms: Vec<PlannerAlgorithmMeta>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerMissionEstimate {
    pub id: String,
    pub label: String,
    pub completion: String,
    pub points: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerPlanetCard {
    pub id: String,
    pub name: String,
    pub align: String,
    pub chain: String,
    pub zone: i64,
    pub phase: i64,
    pub status: String,
    pub capability: String,
    pub estimate: i64,
    pub target: i64,
    pub progress: f64,
    pub note: String,
    pub bonus_locked: bool,
    pub capability_count: i64,
    pub capability_total: i64,
    pub recommended_cm_rate: i64,
    pub recommended_fleet_rate: i64,
    pub operations_filled: i64,
    pub operations_total: i64,
    pub operations_note: String,
    pub combat_missions: Vec<PlannerMissionEstimate>,
    pub fleet_missions: Vec<PlannerMissionEstimate>,
    pub special_missions: Vec<PlannerMissionDefinition>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerSummary {
    pub estimated_stars: i64,
    pub max_possible_stars: i64,
    pub bonus_eligible_count: i64,
    pub bonus_active_count: i64,
    pub ops_filled: i64,
    pub ops_total: i64,
    pub ops_points: i64,
    pub scanned_members: i64,
    pub roster_coverage: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerProjectionResponse {
    pub summary: PlannerSummary,
    pub planet_cards: PlannerPlanetCardMap,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerChainDayResult {
    pub key: String,
    pub status: String,
    pub planet_id: Option<String>,
    pub planet_name: Option<String>,
    pub align: Option<String>,
    pub pts: i64,
    pub gp_deployed: i64,
    pub stars: i64,
    pub pct_of3: i64,
    pub banked: i64,
    pub tomorrow_est: i64,
    pub threshold1star: i64,
    pub carry_in_pts: i64,
    pub mission_pts: i64,
    pub ops_pts: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerBonusPlanetDayResult {
    pub planet_id: String,
    pub planet_name: String,
    pub align: String,
    pub pts: i64,
    pub stars: i64,
    pub carry_in_pts: i64,
    pub mission_pts: i64,
    pub ops_pts: i64,
    pub gp_deployed: i64,
    pub carry_over: i64,
    pub active_from_day: i64,
    pub unlocked_on_day: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerCompletedPlatoon {
    pub pid: String,
    pub platoon_idx: i64,
    pub points: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerOpsAssignmentEntry {
    pub day: i64,
    pub req_idx: i64,
    pub def_id: String,
    pub name: String,
    pub min_relic: i64,
    pub min_rarity: i64,
    pub ally_code: String,
    pub unit_key: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerOpsAssignmentGroup {
    pub platoon_idx: i64,
    pub completed: bool,
    pub points_earned: i64,
    pub entries: Vec<PlannerOpsAssignmentEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerOpsPlanetDaySummary {
    pub priority: i64,
    pub label: String,
    pub completed_today: i64,
    pub slots_filled: i64,
    pub points_earned: i64,
    pub assignments: Vec<PlannerOpsAssignmentGroup>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerOpsPlanetStats {
    pub completed_platoons: i64,
    pub total_platoons: i64,
    pub total_slots: i64,
    pub slots_filled: i64,
    pub points: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerOpsDaySummary {
    pub day: i64,
    pub points_earned: i64,
    pub slots_filled: i64,
    pub completed_platoons: Vec<PlannerCompletedPlatoon>,
    pub planets: HashMap<String, PlannerOpsPlanetDaySummary>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerOpsSummary {
    pub total_completed: i64,
    pub total_platoons: i64,
    pub total_points: i64,
    pub planet_stats: HashMap<String, PlannerOpsPlanetStats>,
    pub days: Vec<PlannerOpsDaySummary>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerDayResult {
    pub day: i64,
    pub gp_avail: i64,
    pub gp_used: i64,
    pub stars_day: i64,
    pub chains: HashMap<String, PlannerChainDayResult>,
    pub notices: Vec<String>,
    pub bonus_planets: Vec<PlannerBonusPlanetDayResult>,
    pub ops_points: i64,
    pub ops_completed: Vec<PlannerCompletedPlatoon>,
    pub ops_planets: HashMap<String, PlannerOpsPlanetDaySummary>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerAlgorithmScore {
    pub algorithm: String,
    pub label: String,
    pub score: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlannerOptimizationResponse {
    pub selected_algorithm: String,
    pub best_algorithm: String,
    pub total_stars: i64,
    pub summary: PlannerSummary,
    pub algorithm_scores: Vec<PlannerAlgorithmScore>,
    pub day_plan: Vec<PlannerDayResult>,
    pub ops_summary: PlannerOpsSummary,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlatoonRequirement {
    pub def_id: String,
    pub name: String,
    pub min_rarity: i64,
    pub min_relic: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlatoonSlotAnalysis {
    pub def_id: String,
    pub name: String,
    pub need: i64,
    pub have: i64,
    pub min_rarity: i64,
    pub min_relic: i64,
    pub ok: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlatoonAnalysisEntry {
    pub fillable: bool,
    pub slots: Vec<PlatoonSlotAnalysis>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OpsDefinitionsResponse {
    pub status: String,
    pub defs: OpsDefinitions,
    pub count: usize,
    pub source: String,
    pub source_label: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlatoonAnalysisResponse {
    pub status: String,
    pub analysis: PlatoonAnalysisMap,
    pub planet_count: usize,
    pub roster_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct GuideTbOmicron {
    pub skill_id: String,
    pub name: String,
    pub kind: String,
    pub omicron_area: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GuideTbOmicronResponse {
    pub status: String,
    pub units: GuideTbOmicronMap,
    pub omicron_area: i64,
    pub area_label: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ComlinkStatusResponse {
    pub comlink: String,
    pub port: u16,
    pub version: String,
    pub binary_path: Option<String>,
    pub managed_process: bool,
    pub message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct SessionSnapshot {
    pub guild_summary: Option<GuildSummary>,
    pub guild_rosters: GuildRosters,
    pub ops_source: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BootstrapResponse {
    pub app_state: Value,
    pub comlink_status: ComlinkStatusResponse,
    pub session: SessionSnapshot,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LoadAppStateResponse {
    pub state: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SaveAppStateResponse {
    pub saved: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ImportSessionResponse {
    pub imported: bool,
    pub members: usize,
    pub units: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ResetScanSessionResponse {
    pub reset: bool,
}
