use crate::backend;
use crate::error::CommandResult;
use crate::models::{
    BootstrapResponse, BulkRosterScanResponse, BulkScanGuildRostersRequest, ComlinkStatusResponse,
    ExportPreviewResponse, ExportPreviewTokenRequest, GuildImportRequest, GuildImportResponse,
    GuideTbOmicronResponse, GuideUnitCatalogResponse, ImportSessionRequest, ImportSessionResponse,
    LoadAppStateResponse, OpenExportPreviewRequest, OpenExportPreviewResponse,
    OpsDefinitionsResponse, PlannerOptimizationRequest, PlannerOptimizationResponse,
    PlannerProjectionRequest, PlannerProjectionResponse, PlannerReferenceResponse,
    PlatoonAnalysisResponse, ReleaseExportPreviewResponse, ResetScanSessionResponse,
    RosterScanResponse, SaveAppStateRequest, SaveAppStateResponse, ScanRosterRequest,
    WriteExportBundleRequest, WriteExportBundleResponse,
};

#[tauri::command]
pub async fn get_bootstrap_state(app_handle: tauri::AppHandle) -> CommandResult<BootstrapResponse> {
    backend::get_bootstrap_state(app_handle).await
}

#[tauri::command]
pub async fn refresh_comlink_status(
    app_handle: tauri::AppHandle,
) -> CommandResult<ComlinkStatusResponse> {
    backend::refresh_comlink_status(app_handle).await
}

#[tauri::command]
pub async fn start_comlink(app_handle: tauri::AppHandle) -> CommandResult<ComlinkStatusResponse> {
    backend::start_comlink(app_handle).await
}

#[tauri::command]
pub async fn stop_comlink(app_handle: tauri::AppHandle) -> CommandResult<ComlinkStatusResponse> {
    backend::stop_comlink(app_handle).await
}

#[tauri::command]
pub async fn fetch_guild_by_allycode(
    app_handle: tauri::AppHandle,
    request: GuildImportRequest,
) -> CommandResult<GuildImportResponse> {
    backend::fetch_guild_by_allycode(app_handle, request).await
}

#[tauri::command]
pub async fn scan_roster(
    app_handle: tauri::AppHandle,
    request: ScanRosterRequest,
) -> CommandResult<RosterScanResponse> {
    backend::scan_roster(app_handle, request).await
}

#[tauri::command]
pub async fn scan_guild_rosters(
    app_handle: tauri::AppHandle,
    request: BulkScanGuildRostersRequest,
) -> CommandResult<BulkRosterScanResponse> {
    backend::scan_guild_rosters(app_handle, request).await
}

#[tauri::command]
pub async fn load_ops_definitions(
    app_handle: tauri::AppHandle,
) -> CommandResult<OpsDefinitionsResponse> {
    backend::load_ops_definitions(app_handle).await
}

#[tauri::command]
pub async fn analyze_platoons(
    app_handle: tauri::AppHandle,
) -> CommandResult<PlatoonAnalysisResponse> {
    backend::analyze_platoons(app_handle).await
}

#[tauri::command]
pub async fn get_guide_tb_omicrons(
    app_handle: tauri::AppHandle,
) -> CommandResult<GuideTbOmicronResponse> {
    backend::get_guide_tb_omicrons(app_handle).await
}

#[tauri::command]
pub async fn get_guide_unit_catalog(
    app_handle: tauri::AppHandle,
) -> CommandResult<GuideUnitCatalogResponse> {
    backend::get_guide_unit_catalog(app_handle).await
}

#[tauri::command]
pub async fn get_planner_reference() -> CommandResult<PlannerReferenceResponse> {
    backend::get_planner_reference().await
}

#[tauri::command]
pub async fn write_export_bundle(
    app_handle: tauri::AppHandle,
    request: WriteExportBundleRequest,
) -> CommandResult<WriteExportBundleResponse> {
    backend::write_export_bundle(app_handle, request).await
}

#[tauri::command]
pub async fn open_export_preview(
    app_handle: tauri::AppHandle,
    request: OpenExportPreviewRequest,
) -> CommandResult<OpenExportPreviewResponse> {
    backend::open_export_preview(app_handle, request).await
}

#[tauri::command]
pub async fn get_export_preview(
    app_handle: tauri::AppHandle,
    request: ExportPreviewTokenRequest,
) -> CommandResult<ExportPreviewResponse> {
    backend::get_export_preview(app_handle, request).await
}

#[tauri::command]
pub async fn release_export_preview(
    app_handle: tauri::AppHandle,
    request: ExportPreviewTokenRequest,
) -> CommandResult<ReleaseExportPreviewResponse> {
    backend::release_export_preview(app_handle, request).await
}

#[tauri::command]
pub async fn build_planner_projection(
    app_handle: tauri::AppHandle,
    request: PlannerProjectionRequest,
) -> CommandResult<PlannerProjectionResponse> {
    backend::build_planner_projection(app_handle, request).await
}

#[tauri::command]
pub async fn run_planner_optimization(
    app_handle: tauri::AppHandle,
    request: PlannerOptimizationRequest,
) -> CommandResult<PlannerOptimizationResponse> {
    backend::run_planner_optimization(app_handle, request).await
}

#[tauri::command]
pub async fn load_app_state(app_handle: tauri::AppHandle) -> CommandResult<LoadAppStateResponse> {
    backend::load_app_state(app_handle).await
}

#[tauri::command]
pub async fn save_app_state(
    app_handle: tauri::AppHandle,
    request: SaveAppStateRequest,
) -> CommandResult<SaveAppStateResponse> {
    backend::save_app_state(app_handle, request).await
}

#[tauri::command]
pub async fn import_session_state(
    app_handle: tauri::AppHandle,
    request: ImportSessionRequest,
) -> CommandResult<ImportSessionResponse> {
    backend::import_session_state(app_handle, request).await
}

#[tauri::command]
pub async fn reset_scan_session(
    app_handle: tauri::AppHandle,
) -> CommandResult<ResetScanSessionResponse> {
    backend::reset_scan_session(app_handle).await
}
