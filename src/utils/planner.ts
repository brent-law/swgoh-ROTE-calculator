import type { SessionStatus } from "../state/plannerStoreCore";

const syncDateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

const sessionStatusLabels: Record<SessionStatus, string> = {
  idle: "Idle",
  syncing: "Scanning",
  ready: "Ready",
};

export function formatSyncTimestamp(value: string | null) {
  return value ? syncDateFormatter.format(new Date(value)) : "No sync yet";
}

export function formatSessionStatus(value: SessionStatus) {
  return sessionStatusLabels[value];
}
