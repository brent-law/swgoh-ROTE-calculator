import { usePlannerStore } from "../../state/plannerStoreCore";
import {
  formatSessionStatus,
  formatSyncTimestamp,
} from "../../utils/planner";
import styles from "./OverviewPage.module.scss";

export function OverviewPage() {
  const guildName = usePlannerStore((state) => state.guildName);
  const activePhase = usePlannerStore((state) => state.activePhase);
  const sessionStatus = usePlannerStore((state) => state.sessionStatus);
  const lastSyncAt = usePlannerStore((state) => state.lastSyncAt);
  const setSessionStatus = usePlannerStore((state) => state.setSessionStatus);
  const markSyncComplete = usePlannerStore((state) => state.markSyncComplete);
  const advancePhase = usePlannerStore((state) => state.advancePhase);

  return (
    <section className={styles.page}>
      <div className={styles.hero}>
        <article className={styles.panel}>
          <p className={styles.kicker}>Integration complete</p>
          <h2 className={styles.title}>
            The new shell can route, style locally, and share state globally.
          </h2>
          <p className={styles.copy}>
            This is the kind of scaffold we can plug the planner into as the
            Python-era features get migrated into React and Tauri.
          </p>

          <div className={styles.actions}>
            <button
              type="button"
              onClick={() => setSessionStatus("syncing")}
            >
              Start mock sync
            </button>
            <button
              type="button"
              className={styles.secondaryAction}
              onClick={markSyncComplete}
            >
              Mark sync complete
            </button>
            <button
              type="button"
              className={styles.ghostAction}
              onClick={advancePhase}
            >
              Advance to next phase
            </button>
          </div>
        </article>

        <article className={styles.panel}>
          <p className={styles.kicker}>Shared snapshot</p>
          <div className={styles.snapshotList}>
            <div className={styles.snapshotItem}>
              <span className={styles.snapshotLabel}>Guild</span>
              <span className={styles.snapshotValue}>{guildName}</span>
            </div>
            <div className={styles.snapshotItem}>
              <span className={styles.snapshotLabel}>Session status</span>
              <span className={styles.snapshotValue}>
                {formatSessionStatus(sessionStatus)}
              </span>
            </div>
            <div className={styles.snapshotItem}>
              <span className={styles.snapshotLabel}>Last sync</span>
              <span className={styles.snapshotValue}>
                {formatSyncTimestamp(lastSyncAt)}
              </span>
            </div>
          </div>
        </article>
      </div>

      <div className={styles.metrics}>
        <article className={styles.metricCard}>
          <p className={styles.metricLabel}>Current phase</p>
          <p className={styles.metricValue}>P{activePhase}</p>
          <p className={styles.metricNote}>
            Shared by the shell, overview, rosters, and settings pages.
          </p>
        </article>
        <article className={styles.metricCard}>
          <p className={styles.metricLabel}>Router mode</p>
          <p className={styles.metricValue}>Hash</p>
          <p className={styles.metricNote}>
            Safer for Tauri because it does not rely on server-side route
            rewrites.
          </p>
        </article>
        <article className={styles.metricCard}>
          <p className={styles.metricLabel}>Style strategy</p>
          <p className={styles.metricValue}>Modules</p>
          <p className={styles.metricNote}>
            Each page and layout owns its own SCSS scope without global leakage.
          </p>
        </article>
      </div>

      <div className={styles.foundation}>
        <article className={styles.foundationCard}>
          <h3 className={styles.foundationTitle}>React Router</h3>
          <p className={styles.foundationCopy}>
            The shell now has dedicated routes for overview, rosters, and
            settings, with a fallback redirect for unknown paths.
          </p>
        </article>
        <article className={styles.foundationCard}>
          <h3 className={styles.foundationTitle}>SCSS modules</h3>
          <p className={styles.foundationCopy}>
            Component styles are co-located and isolated, while a small global
            stylesheet handles variables, resets, and shared surface rules.
          </p>
        </article>
        <article className={styles.foundationCard}>
          <h3 className={styles.foundationTitle}>Zustand store</h3>
          <p className={styles.foundationCopy}>
            Guild name, phase, sync state, and shell controls now live in one
            store, ready for persistence and planner data.
          </p>
        </article>
      </div>
    </section>
  );
}
