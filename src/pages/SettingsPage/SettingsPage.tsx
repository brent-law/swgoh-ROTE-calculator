import { usePlannerStore } from "../../state/plannerStoreCore";
import styles from "./SettingsPage.module.scss";

export function SettingsPage() {
  const sidebarCollapsed = usePlannerStore((state) => state.sidebarCollapsed);
  const toggleSidebar = usePlannerStore((state) => state.toggleSidebar);
  const resetWorkspace = usePlannerStore((state) => state.resetWorkspace);
  const snapshot = usePlannerStore((state) => ({
    guildName: state.guildName,
    activePhase: state.activePhase,
    sessionStatus: state.sessionStatus,
    lastSyncAt: state.lastSyncAt,
    sidebarCollapsed: state.sidebarCollapsed,
  }));

  return (
    <section className={styles.page}>
      <article className={styles.panel}>
        <p className={styles.kicker}>Store actions</p>
        <div className={styles.row}>
          <div>
            <h2 className={styles.rowTitle}>Sidebar layout</h2>
            <p className={styles.rowCopy}>
              This toggles a shell-level UI preference from inside a child
              route.
            </p>
          </div>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={toggleSidebar}
          >
            {sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          </button>
        </div>

        <div className={styles.row}>
          <div>
            <h2 className={styles.rowTitle}>Workspace reset</h2>
            <p className={styles.rowCopy}>
              Resets the shared demo state so we can quickly sanity-check route
              wiring from a clean baseline.
            </p>
          </div>
          <button
            type="button"
            className={styles.dangerButton}
            onClick={resetWorkspace}
          >
            Reset store
          </button>
        </div>
      </article>

      <article className={styles.panel}>
        <p className={styles.kicker}>Current snapshot</p>
        <pre className={styles.snapshot}>
          {JSON.stringify(snapshot, null, 2)}
        </pre>
      </article>
    </section>
  );
}
