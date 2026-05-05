import { usePlannerStore } from "../../state/plannerStoreCore";
import { formatSyncTimestamp } from "../../utils/planner";
import styles from "./RostersPage.module.scss";

const phases = [1, 2, 3, 4, 5, 6];

export function RostersPage() {
  const guildName = usePlannerStore((state) => state.guildName);
  const activePhase = usePlannerStore((state) => state.activePhase);
  const lastSyncAt = usePlannerStore((state) => state.lastSyncAt);
  const setGuildName = usePlannerStore((state) => state.setGuildName);
  const setActivePhase = usePlannerStore((state) => state.setActivePhase);

  return (
    <section className={styles.page}>
      <article className={styles.panel}>
        <p className={styles.kicker}>Roster inputs</p>
        <h2 className={styles.title}>Shared guild state updates instantly</h2>
        <p className={styles.copy}>
          Change the guild name or active phase here and you will see the shell
          and overview route reflect it immediately through the Zustand store.
        </p>

        <label className={styles.fieldGroup}>
          <span className={styles.label}>Guild name</span>
          <input
            type="text"
            value={guildName}
            onChange={(event) => setGuildName(event.currentTarget.value)}
            placeholder="Enter guild name"
          />
        </label>

        <div className={styles.phaseSection}>
          <span className={styles.label}>Active phase</span>
          <div className={styles.phaseGrid}>
            {phases.map((phase) => (
              <button
                key={phase}
                type="button"
                className={
                  phase === activePhase
                    ? `${styles.phaseButton} ${styles.phaseButtonActive}`
                    : styles.phaseButton
                }
                onClick={() => setActivePhase(phase)}
              >
                Phase {phase}
              </button>
            ))}
          </div>
        </div>
      </article>

      <article className={styles.panel}>
        <p className={styles.kicker}>Migration hints</p>
        <div className={styles.checklist}>
          <div className={styles.checkItem}>
            <span className={styles.checkTitle}>Route-bound workspace</span>
            <p className={styles.checkCopy}>
              Each future planner surface can own its route and load only the
              state it needs.
            </p>
          </div>
          <div className={styles.checkItem}>
            <span className={styles.checkTitle}>Centralized roster context</span>
            <p className={styles.checkCopy}>
              The next step can be replacing mock data with imported guild,
              roster, and platoon payloads.
            </p>
          </div>
          <div className={styles.checkItem}>
            <span className={styles.checkTitle}>Latest sync stamp</span>
            <p className={styles.checkCopy}>
              {formatSyncTimestamp(lastSyncAt)}
            </p>
          </div>
        </div>
      </article>
    </section>
  );
}
