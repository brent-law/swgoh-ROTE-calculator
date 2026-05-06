mod backend;
mod commands;
mod error;
pub mod models;
pub mod planner;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .manage(backend::BackendState::default())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            commands::get_bootstrap_state,
            commands::refresh_comlink_status,
            commands::start_comlink,
            commands::stop_comlink,
            commands::fetch_guild_by_allycode,
            commands::scan_roster,
            commands::scan_guild_rosters,
            commands::load_ops_definitions,
            commands::analyze_platoons,
            commands::get_guide_tb_omicrons,
            commands::get_guide_unit_catalog,
            commands::get_planner_reference,
            commands::write_export_bundle,
            commands::open_export_preview,
            commands::get_export_preview,
            commands::release_export_preview,
            commands::build_planner_projection,
            commands::run_planner_optimization,
            commands::load_app_state,
            commands::save_app_state,
            commands::import_session_state,
            commands::reset_scan_session
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| match event {
        tauri::RunEvent::WindowEvent {
            event: tauri::WindowEvent::CloseRequested { .. } | tauri::WindowEvent::Destroyed,
            ..
        } => {
            tauri::async_runtime::block_on(backend::shutdown_backend(app_handle));
        }
        tauri::RunEvent::ExitRequested { .. } => {
            tauri::async_runtime::block_on(backend::shutdown_backend(app_handle));
        }
        tauri::RunEvent::Exit => {
            tauri::async_runtime::block_on(backend::shutdown_backend(app_handle));
        }
        _ => {}
    });
}
