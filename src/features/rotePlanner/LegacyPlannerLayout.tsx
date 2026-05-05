import { NavLink, Outlet } from "react-router-dom";
import { usePlannerStore } from "../../state/plannerStoreCore";
import { plannerTabs } from "./mockData";
import styles from "./PlannerUi.module.scss";

export function LegacyPlannerLayout() {
  const comlinkStatus = usePlannerStore((state) => state.comlinkStatus);
  const retryComlink = usePlannerStore((state) => state.retryComlink);
  const statusOnline = comlinkStatus.comlink === "online";
  const binaryName =
    comlinkStatus.binaryPath?.split(/[\\/]/).pop() ?? "No local binary found yet";

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.headerTopRow}>
          <div>
            <h1 className={styles.appTitle}>Rise of the Empire - TB Planner</h1>
            <p className={styles.subtitle}>
              Star Wars: Galaxy of Heroes | Territory Battle Calculator
            </p>
          </div>

          <div className={styles.comlinkPanel}>
            <div className={styles.comlinkLabel}>swgoh-comlink</div>
            <div className={styles.comlinkRow}>
              <div className={styles.comlinkStatus}>
                <span
                  className={`${styles.statusDot} ${
                    statusOnline ? styles.statusOnline : styles.statusOffline
                  }`}
                />
                <span>
                  {statusOnline
                    ? `online${comlinkStatus.version !== "?" ? ` v${comlinkStatus.version}` : ""}`
                    : "offline"}
                </span>
              </div>
              <button
                type="button"
                className={styles.retryButton}
                onClick={() => void retryComlink()}
              >
                Start / Retry
              </button>
            </div>
            <div className={styles.comlinkMeta}>{binaryName}</div>
            {comlinkStatus.message ? (
              <div className={styles.comlinkMessage}>{comlinkStatus.message}</div>
            ) : null}
          </div>
        </div>

        <nav className={styles.navTabs} aria-label="Planner sections">
          {plannerTabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) =>
                isActive
                  ? `${styles.navTab} ${styles.navTabActive}`
                  : styles.navTab
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}
