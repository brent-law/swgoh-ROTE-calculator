import { NavLink, Outlet, useLocation } from "react-router-dom";
import { usePlannerStore } from "../../state/plannerStoreCore";
import {
  formatSessionStatus,
  formatSyncTimestamp,
} from "../../utils/planner";
import styles from "./AppShell.module.scss";

const navigation = [
  {
    to: "/",
    label: "Overview",
    hint: "Project foundation",
    end: true,
  },
  {
    to: "/rosters",
    label: "Rosters",
    hint: "Shared guild inputs",
    end: false,
  },
  {
    to: "/settings",
    label: "Settings",
    hint: "Workspace controls",
    end: false,
  },
];

const routeMeta: Record<
  string,
  {
    eyebrow: string;
    title: string;
    description: string;
  }
> = {
  "/": {
    eyebrow: "Foundation",
    title: "Planner cockpit ready for the ROTE migration",
    description:
      "React Router, SCSS modules, and Zustand are connected so the desktop shell now has a solid front-end baseline.",
  },
  "/rosters": {
    eyebrow: "Shared inputs",
    title: "Roster-facing state can move across routes",
    description:
      "Use this space to shape guild-facing inputs now, then plug the Python-era planner data into the same store later.",
  },
  "/settings": {
    eyebrow: "Workspace controls",
    title: "Session controls are centralized",
    description:
      "Shared shell state lives in one place, which makes future Tauri persistence and feature flags much easier to layer in.",
  },
};

export function AppShell() {
  const location = useLocation();
  const guildName = usePlannerStore((state) => state.guildName);
  const activePhase = usePlannerStore((state) => state.activePhase);
  const sessionStatus = usePlannerStore((state) => state.sessionStatus);
  const lastSyncAt = usePlannerStore((state) => state.lastSyncAt);
  const sidebarCollapsed = usePlannerStore((state) => state.sidebarCollapsed);
  const toggleSidebar = usePlannerStore((state) => state.toggleSidebar);

  const currentRoute = routeMeta[location.pathname] ?? routeMeta["/"];
  const shellClassName = sidebarCollapsed
    ? `${styles.shell} ${styles.shellCollapsed}`
    : styles.shell;
  const sidebarClassName = sidebarCollapsed
    ? `${styles.sidebar} ${styles.sidebarCollapsed}`
    : styles.sidebar;

  return (
    <div className={shellClassName}>
      <aside className={sidebarClassName}>
        <div className={styles.brandBlock}>
          <div className={styles.brandBadge}>ROTE</div>
          <div className={styles.brandCopy}>
            <p className={styles.eyebrow}>SWGOH Toolkit</p>
            <h2 className={styles.brandTitle}>Territory Battle Planner</h2>
            <p className={styles.brandNote}>
              The starter shell is now organized for multi-page app growth.
            </p>
          </div>
        </div>

        <button
          type="button"
          className={styles.collapseButton}
          onClick={toggleSidebar}
        >
          {sidebarCollapsed ? "Expand nav" : "Collapse nav"}
        </button>

        <nav className={styles.nav} aria-label="Primary navigation">
          {navigation.map((item, index) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                isActive
                  ? `${styles.navLink} ${styles.navLinkActive}`
                  : styles.navLink
              }
            >
              <span className={styles.navIndex}>
                {(index + 1).toString().padStart(2, "0")}
              </span>
              <span className={styles.navCopy}>
                <span className={styles.navLabel}>{item.label}</span>
                <span className={styles.navHint}>{item.hint}</span>
              </span>
            </NavLink>
          ))}
        </nav>

        <div className={styles.sidebarFooter}>
          <span className={styles.footerLabel}>Live workspace</span>
          <div className={styles.footerCopy}>
            <h3 className={styles.footerHeading}>{guildName}</h3>
            <p className={styles.footerMeta}>
              {formatSessionStatus(sessionStatus)} · Phase {activePhase}
            </p>
            <p className={styles.footerMeta}>
              {formatSyncTimestamp(lastSyncAt)}
            </p>
          </div>
        </div>
      </aside>

      <div className={styles.main}>
        <header className={styles.header}>
          <div className={styles.headerCopy}>
            <p className={styles.eyebrow}>{currentRoute.eyebrow}</p>
            <h1 className={styles.headerTitle}>{currentRoute.title}</h1>
            <p className={styles.headerDescription}>
              {currentRoute.description}
            </p>
          </div>

          <div className={styles.headerMeta}>
            <div className={styles.metaCard}>
              <span className={styles.metaLabel}>Guild</span>
              <span className={styles.metaValue}>{guildName}</span>
            </div>
            <div className={styles.metaCard}>
              <span className={styles.metaLabel}>Phase</span>
              <span className={styles.metaValue}>P{activePhase}</span>
            </div>
            <div className={styles.metaCard}>
              <span className={styles.metaLabel}>Status</span>
              <span className={styles.metaValue}>
                {formatSessionStatus(sessionStatus)}
              </span>
            </div>
          </div>
        </header>

        <main className={styles.outlet}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
