import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { create } from "zustand";
import {
  plannerApi,
  type ComlinkStatus,
  type GuideDataSnapshot,
  type GuideSquad,
  type GuideUnitCatalogEntry,
  type GuideTbOmicronRequirement,
  type GuideTbOmicronMap,
  type GuildRosters,
  type GuildSummary,
  type OpsDefinitions,
  type PersistedAppState,
  type PersistedPlannerMissionOverrideState,
  type PersistedPlannerPlanetState,
  type PersistedPlannerSettings,
  type PlannerAlgorithmScore,
  type PlannerOptimizationProgressEvent,
  type PlannerMissionOverrideState,
  type PlannerOptimizationResponse,
  type PlannerPlanetState,
  type PlannerProjectionResponse,
  type PlannerReferenceResponse,
  type PlannerSettings,
  type PlatoonAnalysisMap,
} from "../lib/plannerApi";
import {
  type ChainKey,
  type GuideDifficulty,
} from "../features/rotePlanner/mockData";

export type SessionStatus = "idle" | "syncing" | "ready";

const GUIDE_MISSION_LIMIT = 20;

type GuideMutationResult = {
  ok: boolean;
  count: number;
  reason?: string;
};

const offlineComlinkStatus: ComlinkStatus = {
  comlink: "offline",
  port: 3000,
  version: "?",
  binaryPath: null,
  managedProcess: false,
  message: null,
};

type GuildScanProgressPayload = {
  phase: string;
  totalMembers: number;
  completedMembers: number;
  successfulMembers: number;
  failedMembers: number;
  currentKey?: string | null;
  currentDisplayName?: string | null;
  lastError?: string | null;
};

const guildScanProgressEvent = "guild-scan-progress";
let guildScanProgressListener: Promise<UnlistenFn> | null = null;
const plannerOptimizationProgressEvent = "planner-optimization-progress";
let plannerOptimizationProgressListener: Promise<UnlistenFn> | null = null;
let optimizationResetTimer: ReturnType<typeof globalThis.setTimeout> | null = null;
let plannerProjectionRequestSequence = 0;
let hydrationPromise: Promise<void> | null = null;

export type PlannerStore = {
  guildName: string;
  activePhase: number;
  sessionStatus: SessionStatus;
  lastSyncAt: string | null;
  sidebarCollapsed: boolean;
  selectedChain: ChainKey;
  selectedOperationsDay: number;
  selectedOperationsPlanetId: string;
  selectedGuideMember: string;
  selectedGuideMission: {
    planetId: string;
    missionId: string;
  };
  expandedGuidePlanets: string[];
  guideData: GuideDataSnapshot;
  guideEditorOpen: boolean;
  guideEditorDifficulty: GuideDifficulty;
  selectedRosterMemberId: string;
  rosterSearch: string;
  rosterFilter: string;
  rosterSortKey: string;
  primaryAllyCode: string;
  selectedAlgorithm: string;
  optimizerAcknowledged: boolean;
  optimizerDirty: boolean;
  isHydrated: boolean;
  isFetchingGuild: boolean;
  isScanningRosters: boolean;
  isLoadingOps: boolean;
  isLoadingPlanner: boolean;
  isRunningOptimization: boolean;
  optimizationProgress: number;
  isPersisting: boolean;
  optimizerStatusMessage: string;
  statusMessage: string;
  lastError: string | null;
  comlinkStatus: ComlinkStatus;
  guildSummary: GuildSummary | null;
  guildRosters: GuildRosters;
  opsDefinitions: OpsDefinitions | null;
  opsAnalysis: PlatoonAnalysisMap | null;
  guideTbOmicrons: GuideTbOmicronMap;
  guideUnitCatalog: GuideUnitCatalogEntry[];
  plannerReference: PlannerReferenceResponse | null;
  plannerSettings: PlannerSettings;
  plannerProjection: PlannerProjectionResponse | null;
  plannerResult: PlannerOptimizationResponse | null;
  hydrateFromBackend: () => Promise<void>;
  refreshComlinkStatus: () => Promise<void>;
  retryComlink: () => Promise<void>;
  stopComlink: () => Promise<void>;
  fetchGuildByAllyCode: (allyCode: string) => Promise<void>;
  scanGuildRosters: () => Promise<void>;
  loadOpsDefinitions: () => Promise<void>;
  analyzePlatoons: () => Promise<void>;
  refreshPlannerProjection: () => Promise<void>;
  runPlannerOptimization: () => Promise<void>;
  persistAppState: () => Promise<void>;
  importPlannerSnapshot: (snapshot: unknown) => Promise<void>;
  setPrimaryAllyCode: (primaryAllyCode: string) => void;
  setGuildName: (guildName: string) => void;
  setActivePhase: (activePhase: number) => void;
  advancePhase: () => void;
  setSessionStatus: (sessionStatus: SessionStatus) => void;
  markSyncComplete: () => void;
  toggleSidebar: () => void;
  setSelectedAlgorithm: (selectedAlgorithm: string) => void;
  acknowledgeOptimizerWarning: () => void;
  setPlannerMode: (key: "cmMode" | "undepMode", value: string) => void;
  setPlannerNumber: (
    key:
      | "guildGp"
      | "guildMembers"
      | "activeMembers"
      | "cmBase"
      | "cmFalloff"
      | "fleetBase"
      | "fleetFalloff",
    value: number,
  ) => void;
  setDailyUndep: (dayIndex: number, value: number) => void;
  fillDailyUndepFromDayOne: () => void;
  setPlanetPlannerState: (
    planetId: string,
    patch: Partial<PlannerPlanetState>,
  ) => void;
  setPlanetMissionOverride: (
    planetId: string,
    missionId: string,
    patch: Partial<PlannerMissionOverrideState>,
  ) => void;
  setPlanetHold: (planetId: string | null) => void;
  setPlanetHoldDays: (days: number) => void;
  applyMissionEstimatesToPlanner: () => void;
  resetWorkspace: () => Promise<void>;
  setSelectedChain: (selectedChain: ChainKey) => void;
  setSelectedOperationsDay: (selectedOperationsDay: number) => void;
  setSelectedOperationsPlanetId: (selectedOperationsPlanetId: string) => void;
  setSelectedGuideMember: (selectedGuideMember: string) => void;
  setSelectedGuideMission: (planetId: string, missionId: string) => void;
  toggleGuidePlanet: (planetId: string) => void;
  saveGuideSquad: (
    planetId: string,
    missionId: string,
    squad: Omit<GuideSquad, "order">,
  ) => GuideMutationResult;
  copyGuideSquad: (
    sourcePlanetId: string,
    sourceMissionId: string,
    squadId: string,
    targetPlanetId: string,
    targetMissionId: string,
  ) => GuideMutationResult;
  moveGuideSquad: (planetId: string, missionId: string, squadId: string, delta: number) => void;
  deleteGuideSquad: (planetId: string, missionId: string, squadId: string) => void;
  importGuideData: (guideData: unknown) => Promise<void>;
  openGuideEditor: (difficulty?: GuideDifficulty) => void;
  closeGuideEditor: () => void;
  setGuideEditorDifficulty: (guideEditorDifficulty: GuideDifficulty) => void;
  setSelectedRosterMemberId: (selectedRosterMemberId: string) => void;
  setRosterSearch: (rosterSearch: string) => void;
  setRosterFilter: (rosterFilter: string) => void;
  setRosterSortKey: (rosterSortKey: string) => void;
};

function defaultPlannerSettings(): PlannerSettings {
  return {
    guildGp: 0,
    guildMembers: 0,
    activeMembers: 0,
    cmMode: "pct",
    undepMode: "pct",
    cmBase: 0,
    cmFalloff: 0,
    fleetBase: 0,
    fleetFalloff: 0,
    dailyUndep: [0, 0, 0, 0, 0, 0],
    planetState: {},
    planetHold: null,
  };
}

function defaultPlanetPlannerState(): PlannerPlanetState {
  return {
    cmRateOverride: null,
    fleetRateOverride: null,
    cmCountOverride: null,
    fleetCountOverride: null,
    preloaded: 0,
    smReady: false,
    smCount: 0,
    missionOverrides: {},
  };
}

function defaultMissionOverrideState(): PlannerMissionOverrideState {
  return {
    rateOverride: null,
    countOverride: null,
  };
}

function defaultGuideData(): GuideDataSnapshot {
  return {
    version: 2,
    squads: {},
  };
}

function guideMissionKey(planetId: string, missionId: string) {
  return `${planetId}___${missionId}`;
}

function normalizeGuideDifficulty(value: unknown): GuideDifficulty {
  return value === "easy" || value === "medium" || value === "hard" ? value : "auto";
}

function normalizeGuideOmicronRequirement(
  value: unknown,
): GuideTbOmicronRequirement | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const unitDefId = String(record.unitDefId ?? "").trim();
  const skillId = String(record.skillId ?? "").trim();
  if (!unitDefId || !skillId) return null;
  return {
    unitDefId,
    unitName: String(record.unitName ?? "").trim(),
    skillId,
    skillName: String(record.skillName ?? record.name ?? "").trim() || skillId,
  };
}

function createGuideSquadId() {
  return `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function sortGuideSquads(squads: GuideSquad[]) {
  return squads
    .map((entry, index) => ({ ...entry, order: index }))
    .sort((left, right) => left.order - right.order || left.id.localeCompare(right.id));
}

function normalizeGuideSquad(value: unknown): GuideSquad {
  const record = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  const members = Array.isArray(record.members)
    ? record.members
        .slice(0, 7)
        .map((entry) => String(entry ?? "").trim())
    : [];
  const memberDefIds = Array.isArray(record.memberDefIds)
    ? record.memberDefIds.slice(0, 7).map((entry) => String(entry ?? "").trim())
    : [];

  return {
    id: String(record.id ?? "").trim() || createGuideSquadId(),
    leader: String(record.leader ?? "").trim(),
    leaderDefId: String(record.leaderDefId ?? "").trim(),
    members,
    memberDefIds,
    notes: String(record.notes ?? "").trim(),
    videoUrl: String(record.videoUrl ?? "").trim(),
    requiredTbOmicrons: Array.isArray(record.requiredTbOmicrons)
      ? record.requiredTbOmicrons
          .map((entry) => normalizeGuideOmicronRequirement(entry))
          .filter((entry): entry is GuideTbOmicronRequirement => Boolean(entry))
      : [],
    difficulty: normalizeGuideDifficulty(record.difficulty),
    order:
      typeof record.order === "number" && Number.isFinite(record.order)
        ? record.order
        : 0,
  };
}

function normalizeGuideData(value: unknown): GuideDataSnapshot {
  if (!value || typeof value !== "object") return defaultGuideData();
  const record = value as Record<string, unknown>;
  const squadsRecord =
    record.squads && typeof record.squads === "object"
      ? (record.squads as Record<string, unknown>)
      : {};
  const squads = Object.fromEntries(
    Object.entries(squadsRecord).map(([key, entries]) => [
      key,
      Array.isArray(entries)
        ? entries
            .map((entry) => normalizeGuideSquad(entry))
            .sort((left, right) => left.order - right.order || left.id.localeCompare(right.id))
        : [],
    ]),
  );
  return {
    version:
      typeof record.version === "number" && Number.isFinite(record.version)
        ? record.version
        : 2,
    squads,
  };
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function normalizeFiniteNumber(value: number, fallback = 0) {
  return Number.isFinite(value) ? value : fallback;
}

function missionEstimateFieldLimit(cmMode: string) {
  return cmMode === "count" ? 50 : 100;
}

function missionEstimateFallbackValue(
  key: "cmBase" | "cmFalloff" | "fleetBase" | "fleetFalloff",
  cmMode: string,
  guildMembers: number,
) {
  if (cmMode === "count") {
    const memberCount = clampNumber(Math.round(guildMembers) || 50, 1, 50);
    const multiplierMap = {
      cmBase: 0.7,
      cmFalloff: 0.1,
      fleetBase: 0.5,
      fleetFalloff: 0.15,
    } as const;
    return Math.round(memberCount * multiplierMap[key]);
  }

  const fallbackMap = {
    cmBase: 70,
    cmFalloff: 10,
    fleetBase: 50,
    fleetFalloff: 15,
  } as const;
  return fallbackMap[key];
}

function sanitizeMissionEstimateSetting(
  settings: PlannerSettings,
  key: "cmBase" | "cmFalloff" | "fleetBase" | "fleetFalloff",
  rawValue: number,
) {
  const limit = missionEstimateFieldLimit(settings.cmMode);
  const fallback = missionEstimateFallbackValue(key, settings.cmMode, settings.guildMembers);
  return clampNumber(normalizeFiniteNumber(rawValue, fallback), 0, limit);
}

function sanitizeDailyUndepValue(settings: PlannerSettings, rawValue: number) {
  const limit =
    settings.undepMode === "flat" ? Math.max(0, settings.guildGp) : 100;
  return clampNumber(normalizeFiniteNumber(rawValue, 0), 0, limit);
}

function plannerChainDepth(planetId: string) {
  switch (planetId) {
    case "mustafar":
    case "corellia":
    case "coruscant":
      return 0;
    case "geonosis":
    case "felucia":
    case "bracca":
      return 1;
    case "dathomir":
    case "tatooine":
    case "kashyyyk":
    case "zeffo":
      return 2;
    case "medstation":
    case "kessel":
    case "lothal":
    case "mandalore":
      return 3;
    case "malachor":
    case "vandor":
    case "kafrene":
      return 4;
    case "deathstar":
    case "hoth":
    case "scarif":
      return 5;
    default:
      return 3;
  }
}

function buildPlanetOverridePatch(
  settings: PlannerSettings,
  planetId: string,
): Partial<PlannerPlanetState> {
  const depth = plannerChainDepth(planetId);
  const cmValue = Math.max(0, settings.cmBase - settings.cmFalloff * depth);
  const fleetValue = Math.max(0, settings.fleetBase - settings.fleetFalloff * depth);

  if (settings.cmMode === "count") {
    const memberCount = clampNumber(settings.guildMembers, 1, 50);
    return {
      cmRateOverride: null,
      fleetRateOverride: null,
      cmCountOverride: clampNumber(Math.round((memberCount * cmValue) / 100), 0, 50),
      fleetCountOverride: clampNumber(Math.round((memberCount * fleetValue) / 100), 0, 50),
      missionOverrides: {},
    };
  }

  return {
    cmRateOverride: clampNumber(cmValue, 0, 100),
    fleetRateOverride: clampNumber(fleetValue, 0, 100),
    cmCountOverride: null,
    fleetCountOverride: null,
    missionOverrides: {},
  };
}

function sanitizeMissionOverridePatch(
  settings: PlannerSettings,
  patch: Partial<PlannerMissionOverrideState>,
): Partial<PlannerMissionOverrideState> {
  const nextPatch = { ...patch };

  if (typeof nextPatch.rateOverride === "number") {
    nextPatch.rateOverride = clampNumber(nextPatch.rateOverride, 0, 100);
  }
  if (typeof nextPatch.countOverride === "number") {
    nextPatch.countOverride = clampNumber(nextPatch.countOverride, 0, 50);
  }

  if (settings.cmMode === "pct") {
    if (typeof nextPatch.rateOverride === "number") {
      nextPatch.countOverride = null;
    }
  } else if (typeof nextPatch.countOverride === "number") {
    nextPatch.rateOverride = null;
  }

  return nextPatch;
}

function sanitizePlanetPlannerPatch(
  settings: PlannerSettings,
  patch: Partial<PlannerPlanetState>,
) {
  const nextPatch = { ...patch };

  if (typeof nextPatch.cmRateOverride === "number") {
    nextPatch.cmRateOverride = clampNumber(nextPatch.cmRateOverride, 0, 100);
  }
  if (typeof nextPatch.fleetRateOverride === "number") {
    nextPatch.fleetRateOverride = clampNumber(nextPatch.fleetRateOverride, 0, 100);
  }
  if (typeof nextPatch.cmCountOverride === "number") {
    nextPatch.cmCountOverride = clampNumber(nextPatch.cmCountOverride, 0, 50);
  }
  if (typeof nextPatch.fleetCountOverride === "number") {
    nextPatch.fleetCountOverride = clampNumber(nextPatch.fleetCountOverride, 0, 50);
  }
  if (typeof nextPatch.preloaded === "number") {
    nextPatch.preloaded = clampNumber(Math.round(nextPatch.preloaded), 0, Number.MAX_SAFE_INTEGER);
  }
  if (typeof nextPatch.smCount === "number") {
    nextPatch.smCount = clampNumber(Math.round(nextPatch.smCount), 0, Number.MAX_SAFE_INTEGER);
  }
  if (nextPatch.missionOverrides && typeof nextPatch.missionOverrides === "object") {
    nextPatch.missionOverrides = Object.fromEntries(
      Object.entries(nextPatch.missionOverrides).map(([missionId, missionPatch]) => [
        missionId,
        sanitizeMissionOverridePatch(
          settings,
          typeof missionPatch === "object" && missionPatch !== null
            ? (missionPatch as Partial<PlannerMissionOverrideState>)
            : {},
        ),
      ]),
    ) as Record<string, PlannerMissionOverrideState>;
  }

  if (settings.cmMode === "pct") {
    if (typeof nextPatch.cmRateOverride === "number") {
      nextPatch.cmCountOverride = null;
    }
    if (typeof nextPatch.fleetRateOverride === "number") {
      nextPatch.fleetCountOverride = null;
    }
  } else {
    if (typeof nextPatch.cmCountOverride === "number") {
      nextPatch.cmRateOverride = null;
    }
    if (typeof nextPatch.fleetCountOverride === "number") {
      nextPatch.fleetRateOverride = null;
    }
  }

  return nextPatch;
}

function normalizeMissionOverrideState(value: unknown): PlannerMissionOverrideState {
  const defaults = defaultMissionOverrideState();
  if (typeof value !== "object" || value === null) {
    return defaults;
  }

  const record = value as Partial<PlannerMissionOverrideState>;
  const normalizeOptionalNumber = (input: unknown) =>
    typeof input === "number" && Number.isFinite(input) ? input : null;

  return {
    rateOverride: normalizeOptionalNumber(record.rateOverride),
    countOverride: normalizeOptionalNumber(record.countOverride),
  };
}

function normalizeMissionOverrideMap(
  value: unknown,
): Record<string, PlannerMissionOverrideState> {
  if (typeof value !== "object" || value === null) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([missionId, state]) => [
      missionId,
      normalizeMissionOverrideState(state),
    ]),
  );
}

function normalizePlanetPlannerState(value: unknown): PlannerPlanetState {
  const defaults = defaultPlanetPlannerState();
  if (typeof value !== "object" || value === null) {
    return defaults;
  }

  const record = value as Partial<PlannerPlanetState>;
  const normalizeOptionalNumber = (input: unknown) =>
    typeof input === "number" && Number.isFinite(input) ? input : null;

  return {
    cmRateOverride: normalizeOptionalNumber(record.cmRateOverride),
    fleetRateOverride: normalizeOptionalNumber(record.fleetRateOverride),
    cmCountOverride: normalizeOptionalNumber(record.cmCountOverride),
    fleetCountOverride: normalizeOptionalNumber(record.fleetCountOverride),
    preloaded:
      typeof record.preloaded === "number" && Number.isFinite(record.preloaded)
        ? record.preloaded
        : defaults.preloaded,
    smReady: typeof record.smReady === "boolean" ? record.smReady : defaults.smReady,
    smCount:
      typeof record.smCount === "number" && Number.isFinite(record.smCount)
        ? record.smCount
        : defaults.smCount,
    missionOverrides: normalizeMissionOverrideMap(record.missionOverrides),
  };
}

function normalizePlanetPlannerStateMap(
  value: unknown,
): Record<string, PlannerPlanetState> {
  if (typeof value !== "object" || value === null) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([planetId, state]) => [
      planetId,
      normalizePlanetPlannerState(state),
    ]),
  );
}

function createInitialState() {
  return {
    guildName: "",
    activePhase: 1,
    sessionStatus: "idle" as SessionStatus,
    lastSyncAt: null,
    sidebarCollapsed: false,
    selectedChain: "ds" as ChainKey,
    selectedOperationsDay: 1,
    selectedOperationsPlanetId: "mustafar",
    selectedGuideMember: "",
    selectedGuideMission: {
      planetId: "mustafar",
      missionId: "nute",
    },
    expandedGuidePlanets: ["mustafar", "corellia", "coruscant"],
    guideData: defaultGuideData(),
    guideEditorOpen: false,
    guideEditorDifficulty: "auto" as GuideDifficulty,
    selectedRosterMemberId: "",
    rosterSearch: "",
    rosterFilter: "all",
    rosterSortKey: "name",
    primaryAllyCode: "",
    selectedAlgorithm: "",
    optimizerAcknowledged: false,
    optimizerDirty: false,
    isHydrated: false,
    isFetchingGuild: false,
    isScanningRosters: false,
    isLoadingOps: false,
    isLoadingPlanner: false,
    isRunningOptimization: false,
    optimizationProgress: 0,
    isPersisting: false,
    optimizerStatusMessage: "",
    statusMessage: "Ready to import a guild.",
    lastError: null,
    comlinkStatus: offlineComlinkStatus,
    guildSummary: null as GuildSummary | null,
    guildRosters: {} as GuildRosters,
    opsDefinitions: null as OpsDefinitions | null,
    opsAnalysis: null as PlatoonAnalysisMap | null,
    guideTbOmicrons: {} as GuideTbOmicronMap,
    guideUnitCatalog: [] as GuideUnitCatalogEntry[],
    plannerReference: null as PlannerReferenceResponse | null,
    plannerSettings: defaultPlannerSettings(),
    plannerProjection: null as PlannerProjectionResponse | null,
    plannerResult: null as PlannerOptimizationResponse | null,
  };
}

function firstRosterMember(guildRosters: GuildRosters) {
  return Object.keys(guildRosters).find((key) => guildRosters[key]?.length) ?? "";
}

function hasRosterSelection(selectedMemberId: string, guildRosters: GuildRosters) {
  return Boolean(selectedMemberId && guildRosters[selectedMemberId]?.length);
}

function isPersistedGuideMission(
  value: unknown,
): value is { planetId: string; missionId: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    "planetId" in value &&
    "missionId" in value &&
    typeof value.planetId === "string" &&
    typeof value.missionId === "string"
  );
}

function normalizeSnapshotGuildSummary(value: unknown) {
  return value && typeof value === "object" && Array.isArray((value as GuildSummary).members)
    ? (value as GuildSummary)
    : null;
}

function normalizeSnapshotGuildRosters(value: unknown) {
  return value && typeof value === "object" ? (value as GuildRosters) : ({} as GuildRosters);
}

function normalizeSnapshotOpsDefinitions(value: unknown) {
  return value && typeof value === "object" ? (value as OpsDefinitions) : null;
}

function normalizeSnapshotOpsAnalysis(value: unknown) {
  return value && typeof value === "object" ? (value as PlatoonAnalysisMap) : null;
}

function normalizeSnapshotPlannerProjection(value: unknown) {
  return value && typeof value === "object" ? (value as PlannerProjectionResponse) : null;
}

function normalizeSnapshotPlannerResult(value: unknown) {
  return value &&
    typeof value === "object" &&
    Array.isArray((value as PlannerOptimizationResponse).dayPlan)
    ? (value as PlannerOptimizationResponse)
    : null;
}

function normalizePlannerSettings(
  persisted: unknown,
  guildSummary: GuildSummary | null,
): PlannerSettings {
  const defaults = defaultPlannerSettings();
  const value = typeof persisted === "object" && persisted !== null ? persisted : {};
  const record = value as Partial<PlannerSettings>;
  const guildMembers = guildSummary?.members.length ?? defaults.guildMembers;
  const dailyUndep = Array.isArray(record.dailyUndep)
    ? Array.from({ length: 6 }, (_, index) => {
        const raw = record.dailyUndep?.[index];
        return typeof raw === "number" && Number.isFinite(raw)
          ? raw
          : defaults.dailyUndep[index];
      })
    : defaults.dailyUndep;
  return {
    guildGp: guildSummary?.gp ?? defaults.guildGp,
    guildMembers,
    activeMembers: guildMembers,
    cmMode: record.cmMode === "count" ? "count" : "pct",
    undepMode: record.undepMode === "flat" ? "flat" : "pct",
    cmBase: typeof record.cmBase === "number" ? record.cmBase : defaults.cmBase,
    cmFalloff:
      typeof record.cmFalloff === "number" ? record.cmFalloff : defaults.cmFalloff,
    fleetBase:
      typeof record.fleetBase === "number" ? record.fleetBase : defaults.fleetBase,
    fleetFalloff:
      typeof record.fleetFalloff === "number"
        ? record.fleetFalloff
        : defaults.fleetFalloff,
    dailyUndep,
    planetState: normalizePlanetPlannerStateMap(record.planetState),
    planetHold: null,
  };
}

function formatGuildScanStatus(payload: GuildScanProgressPayload) {
  const total = Math.max(payload.totalMembers, 0);
  const completed = Math.min(payload.completedMembers, total);
  const progress = `${completed}/${total}`;
  const loadedSummary = `${payload.successfulMembers} loaded`;
  const failureSummary = payload.failedMembers ? ` | ${payload.failedMembers} failed` : "";

  if (payload.phase === "starting") {
    return `Starting roster scan for ${total} members...`;
  }

  if (payload.phase === "recovering") {
    return `Comlink recovery in progress... ${progress} scanned | ${loadedSummary}${failureSummary}`;
  }

  if (payload.phase === "calculating-power") {
    return `Calculating unit power for scanned rosters... ${progress} scanned | ${loadedSummary}${failureSummary}`;
  }

  if (payload.phase === "complete") {
    return `Roster scan complete: ${payload.successfulMembers}/${total} loaded${failureSummary}`;
  }

  const currentLabel = payload.currentDisplayName || payload.currentKey || "guild member";
  return `Scanning ${currentLabel}... ${progress} scanned | ${loadedSummary}${failureSummary}`;
}

function clearOptimizationResetTimer() {
  if (optimizationResetTimer !== null) {
    globalThis.clearTimeout(optimizationResetTimer);
    optimizationResetTimer = null;
  }
}

function resetOptimizerState() {
  return {
    plannerResult: null as PlannerOptimizationResponse | null,
    optimizationProgress: 0,
    optimizerDirty: false,
    optimizerStatusMessage: "",
  };
}

function invalidateOptimizerState(
  state: Pick<PlannerStore, "plannerResult" | "optimizerDirty">,
) {
  return {
    plannerResult: null as PlannerOptimizationResponse | null,
    optimizationProgress: 0,
    optimizerDirty: state.optimizerDirty || Boolean(state.plannerResult),
    optimizerStatusMessage: "",
  };
}

function formatOptimizationScoreSummary(scores: PlannerAlgorithmScore[]) {
  return scores.map((entry) => `${entry.label}: ${entry.score} stars`).join(" | ");
}

function formatOptimizationCompletionStatus(plannerResult: PlannerOptimizationResponse) {
  const bestEntry =
    plannerResult.algorithmScores.find(
      (entry) => entry.algorithm === plannerResult.bestAlgorithm,
    ) ??
    plannerResult.algorithmScores[0];
  const bestLabel = bestEntry?.label ?? plannerResult.bestAlgorithm;
  const baseMessage = `Complete - Best: ${plannerResult.totalStars} stars (${bestLabel})`;
  if (plannerResult.algorithmScores.length <= 1) {
    return baseMessage;
  }
  const summary = formatOptimizationScoreSummary(plannerResult.algorithmScores);
  return summary ? `${baseMessage} | ${summary}` : baseMessage;
}

function toPersistedMissionOverrideState(
  missionState: PlannerMissionOverrideState,
): PersistedPlannerMissionOverrideState {
  return {
    rateOverride: missionState.rateOverride,
    countOverride: missionState.countOverride,
  };
}

function toPersistedPlanetPlannerState(
  planetState: PlannerPlanetState,
): PersistedPlannerPlanetState {
  return {
    cmRateOverride: planetState.cmRateOverride,
    fleetRateOverride: planetState.fleetRateOverride,
    cmCountOverride: planetState.cmCountOverride,
    fleetCountOverride: planetState.fleetCountOverride,
    smReady: planetState.smReady,
    smCount: planetState.smCount,
    missionOverrides: Object.fromEntries(
      Object.entries(planetState.missionOverrides).map(([missionId, missionState]) => [
        missionId,
        toPersistedMissionOverrideState(missionState),
      ]),
    ),
  };
}

function toPersistedPlannerSettings(
  plannerSettings: PlannerSettings,
): PersistedPlannerSettings {
  return {
    cmMode: plannerSettings.cmMode,
    undepMode: plannerSettings.undepMode,
    cmBase: plannerSettings.cmBase,
    cmFalloff: plannerSettings.cmFalloff,
    fleetBase: plannerSettings.fleetBase,
    fleetFalloff: plannerSettings.fleetFalloff,
    dailyUndep: plannerSettings.dailyUndep.slice(0, 6),
    planetState: Object.fromEntries(
      Object.entries(plannerSettings.planetState).map(([planetId, planetState]) => [
        planetId,
        toPersistedPlanetPlannerState(planetState),
      ]),
    ),
  };
}

function toPersistedAppState(state: PlannerStore): PersistedAppState {
  return {
    primaryAllyCode: state.primaryAllyCode,
    plannerSettings: toPersistedPlannerSettings(state.plannerSettings),
    guideData: state.guideData,
  };
}

async function refreshGuideOmicrons() {
  try {
    const response = await plannerApi.getGuideTbOmicrons();
    return response.units;
  } catch {
    return {};
  }
}

async function refreshGuideUnitCatalog() {
  try {
    const response = await plannerApi.getGuideUnitCatalog();
    return response.units;
  } catch {
    return [] as GuideUnitCatalogEntry[];
  }
}

function refreshGuideUnitCatalogInBackground(
  set: (partial: Partial<PlannerStore>) => void,
) {
  void refreshGuideUnitCatalog().then((guideUnitCatalog) => {
    set({ guideUnitCatalog });
  });
}

function planetIdsForDay(result: PlannerOptimizationResponse | null, day: number) {
  const dayPlan = result?.dayPlan.find((entry) => entry.day === day);
  if (!dayPlan) return [];
  const ids = [
    dayPlan.chains.ds?.planetId,
    dayPlan.chains.mx?.planetId,
    dayPlan.chains.ls?.planetId,
    ...dayPlan.bonusPlanets.map((planet) => planet.planetId),
  ].filter((value): value is string => typeof value === "string" && value.length > 0);
  return Array.from(new Set(ids));
}

function resolveOperationsPlanet(
  preferredPlanetId: string,
  result: PlannerOptimizationResponse | null,
  fallbackAnalysis: PlatoonAnalysisMap | null,
  day: number,
) {
  const dayPlanIds = planetIdsForDay(result, day);
  if (dayPlanIds.includes(preferredPlanetId)) return preferredPlanetId;
  if (dayPlanIds.length) return dayPlanIds[0];
  const analysisKeys = Object.keys(fallbackAnalysis ?? {});
  if (analysisKeys.includes(preferredPlanetId)) return preferredPlanetId;
  return analysisKeys[0] ?? preferredPlanetId;
}

export const usePlannerStore = create<PlannerStore>()((set, get) => {
  const ensureScanProgressListener = () => {
    if (guildScanProgressListener) return;
    guildScanProgressListener = listen<GuildScanProgressPayload>(
      guildScanProgressEvent,
      (event) => {
        const payload = event.payload;
        if (!get().isScanningRosters && payload.phase !== "complete") return;
        set(() => {
          const patch: Partial<PlannerStore> = {
            statusMessage: formatGuildScanStatus(payload),
          };
          if (payload.lastError) {
            patch.lastError = payload.lastError;
          }
          return patch;
        });
      },
    );
  };

  const ensureOptimizationProgressListener = () => {
    if (plannerOptimizationProgressListener) return;
    plannerOptimizationProgressListener = listen<PlannerOptimizationProgressEvent>(
      plannerOptimizationProgressEvent,
      (event) => {
        const payload = event.payload;
        if (!get().isRunningOptimization && payload.phase !== "complete") return;
        set(() => ({
          optimizationProgress: Math.round(
            clampNumber(payload.overallFraction * 100, 0, 100),
          ),
          optimizerStatusMessage: payload.message,
        }));
      },
    );
  };

  return {
  ...createInitialState(),
  hydrateFromBackend: async () => {
    ensureScanProgressListener();
    if (get().isHydrated) return;
    if (hydrationPromise) {
      return hydrationPromise;
    }
    hydrationPromise = (async () => {
      set({ sessionStatus: "syncing", statusMessage: "Restoring planner state..." });
      try {
        const [bootstrap, plannerReference] = await Promise.all([
          plannerApi.getBootstrapState(),
          plannerApi.getPlannerReference(),
        ]);
        const persisted = bootstrap.appState ?? {};
        const guildSummary = bootstrap.session.guildSummary;
        const guildRosters = bootstrap.session.guildRosters ?? {};
        const plannerSettings = normalizePlannerSettings(
          persisted.plannerSettings,
          guildSummary,
        );

        set((state) => {
          const firstScannedMember = firstRosterMember(guildRosters);

          return {
            isHydrated: true,
            sessionStatus: "ready",
            guildName: guildSummary?.name ?? state.guildName,
            guildSummary,
            guildRosters,
            comlinkStatus: bootstrap.comlinkStatus,
            plannerReference,
            plannerSettings,
            primaryAllyCode:
              typeof persisted.primaryAllyCode === "string"
                ? persisted.primaryAllyCode
                : state.primaryAllyCode,
            selectedGuideMember: firstScannedMember,
            selectedGuideMission: state.selectedGuideMission,
            expandedGuidePlanets: state.expandedGuidePlanets,
            guideData: normalizeGuideData(persisted.guideData),
            guideEditorDifficulty: "auto",
            selectedRosterMemberId: firstScannedMember,
            statusMessage:
              bootstrap.comlinkStatus.comlink === "online"
                ? "Planner ready."
                : bootstrap.comlinkStatus.message ?? "Planner ready in offline mode.",
          };
        });
        refreshGuideUnitCatalogInBackground((partial) => set(partial));
        await get().refreshPlannerProjection();
        if (bootstrap.comlinkStatus.comlink !== "online") {
          void get().retryComlink();
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        set({
          isHydrated: true,
          sessionStatus: "ready",
          lastError: message,
          statusMessage: `Restore skipped: ${message}`,
        });
      } finally {
        hydrationPromise = null;
      }
    })();
    return hydrationPromise;
  },
  refreshComlinkStatus: async () => {
    try {
      const comlinkStatus = await plannerApi.refreshComlinkStatus();
      set({
        comlinkStatus,
        statusMessage:
          comlinkStatus.comlink === "online"
            ? `swgoh-comlink online${comlinkStatus.version !== "?" ? ` v${comlinkStatus.version}` : ""}.`
            : comlinkStatus.message ?? "swgoh-comlink is offline.",
        lastError: null,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      set({ lastError: message, statusMessage: `Status check failed: ${message}` });
    }
  },
  retryComlink: async () => {
    set({ statusMessage: "Starting swgoh-comlink...", sessionStatus: "syncing" });
    try {
      const comlinkStatus = await plannerApi.startComlink();
      set({
        comlinkStatus,
        sessionStatus: "ready",
        statusMessage:
          comlinkStatus.comlink === "online"
            ? "swgoh-comlink is ready."
            : comlinkStatus.message ?? "swgoh-comlink is still offline.",
        lastError: null,
      });
      refreshGuideUnitCatalogInBackground((partial) => set(partial));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      set({
        sessionStatus: "ready",
        lastError: message,
        statusMessage: `Comlink start failed: ${message}`,
      });
    }
  },
  stopComlink: async () => {
    try {
      const comlinkStatus = await plannerApi.stopComlink();
      set({ comlinkStatus, statusMessage: "swgoh-comlink stopped." });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      set({ lastError: message, statusMessage: `Stop failed: ${message}` });
    }
  },
  fetchGuildByAllyCode: async (allyCode) => {
    set({
      isFetchingGuild: true,
      sessionStatus: "syncing",
      statusMessage: "Fetching guild from comlink...",
      lastError: null,
    });
    try {
      const response = await plannerApi.fetchGuildByAllyCode(allyCode);
      const memberCount = response.summary.members.length;
      clearOptimizationResetTimer();
      set((state) => ({
        isFetchingGuild: false,
        sessionStatus: "ready",
        guildName: response.summary.name,
        guildSummary: response.summary,
        guildRosters: {},
        opsAnalysis: null,
        guideTbOmicrons: {},
        ...resetOptimizerState(),
        primaryAllyCode: allyCode,
        selectedGuideMember: "",
        selectedRosterMemberId: "",
        plannerSettings: {
          ...state.plannerSettings,
          guildGp: response.summary.gp,
          guildMembers: memberCount,
          activeMembers: memberCount,
        },
        lastSyncAt: new Date().toISOString(),
        statusMessage: `Loaded ${response.summary.name} (${memberCount} members).`,
      }));
      refreshGuideUnitCatalogInBackground((partial) => set(partial));
      await get().refreshPlannerProjection();
      await get().persistAppState();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      set({
        isFetchingGuild: false,
        sessionStatus: "ready",
        lastError: message,
        statusMessage: `Guild import failed: ${message}`,
      });
    }
  },
  scanGuildRosters: async () => {
    ensureScanProgressListener();
    const guildSummary = get().guildSummary;
    if (!guildSummary?.members.length) {
      set({ statusMessage: "Fetch guild data first." });
      return;
    }
    set({
      isScanningRosters: true,
      sessionStatus: "syncing",
      statusMessage: `Starting roster scan for ${guildSummary.members.length} members...`,
      lastError: null,
    });
    try {
      const response = await plannerApi.scanGuildRosters(
        guildSummary.members.map((member) => ({
          key: member.allyCode || member.playerId,
          displayName: member.displayName,
        })),
      );
      const [guideTbOmicrons, guideUnitCatalog] = await Promise.all([
        refreshGuideOmicrons(),
        refreshGuideUnitCatalog(),
      ]);
      const firstScannedMember = firstRosterMember(response.guildRosters);
      clearOptimizationResetTimer();
      set((state) => ({
        isScanningRosters: false,
        sessionStatus: "ready",
        guildRosters: response.guildRosters,
        guideTbOmicrons,
        guideUnitCatalog,
        opsAnalysis: null,
        ...invalidateOptimizerState(state),
        selectedRosterMemberId: hasRosterSelection(
          state.selectedRosterMemberId,
          response.guildRosters,
        )
          ? state.selectedRosterMemberId
          : firstScannedMember,
        selectedGuideMember: hasRosterSelection(
          state.selectedGuideMember,
          response.guildRosters,
        )
          ? state.selectedGuideMember
          : firstScannedMember,
        lastSyncAt: new Date().toISOString(),
        statusMessage:
          response.failedMembers.length === 0
            ? response.powerReady
              ? `Roster scan complete for ${response.scannedMembers} members.`
              : `Roster scan complete for ${response.scannedMembers} members, but some unit power values are still missing.`
            : response.powerReady
              ? `Roster scan finished with ${response.failedMembers.length} failures.`
              : `Roster scan finished with ${response.failedMembers.length} failures and partial unit power data.`,
        lastError:
          !response.powerReady && response.powerError
            ? response.powerError
            : state.lastError,
      }));
      await get().loadOpsDefinitions();
      await get().analyzePlatoons();
      await get().refreshPlannerProjection();
      await get().persistAppState();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      set({
        isScanningRosters: false,
        sessionStatus: "ready",
        lastError: message,
        statusMessage: `Roster scan failed: ${message}`,
      });
    }
  },
  loadOpsDefinitions: async () => {
    set({ isLoadingOps: true });
    try {
      const response = await plannerApi.loadOpsDefinitions();
      set({ isLoadingOps: false, opsDefinitions: response.defs });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      set({
        isLoadingOps: false,
        lastError: message,
        statusMessage: `Operations load failed: ${message}`,
      });
    }
  },
  analyzePlatoons: async () => {
    if (!Object.keys(get().guildRosters).length) return;
    set({ isLoadingOps: true, statusMessage: "Analyzing platoons..." });
    try {
      const response = await plannerApi.analyzePlatoons();
      set((state) => ({
        isLoadingOps: false,
        opsAnalysis: response.analysis,
        selectedOperationsPlanetId: resolveOperationsPlanet(
          state.selectedOperationsPlanetId,
          state.plannerResult,
          response.analysis,
          state.selectedOperationsDay,
        ),
        statusMessage: `Operations refreshed for ${response.planetCount} planets.`,
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      set({
        isLoadingOps: false,
        lastError: message,
        statusMessage: `Platoon analysis failed: ${message}`,
      });
    }
  },
  refreshPlannerProjection: async () => {
    const { plannerReference, plannerSettings } = get();
    if (!plannerReference) return;
    const requestId = ++plannerProjectionRequestSequence;
    set({ isLoadingPlanner: true });
    try {
      const plannerProjection = await plannerApi.buildPlannerProjection(plannerSettings);
      if (requestId !== plannerProjectionRequestSequence) {
        return;
      }
      set({ isLoadingPlanner: false, plannerProjection });
    } catch (error) {
      if (requestId !== plannerProjectionRequestSequence) {
        return;
      }
      const message = error instanceof Error ? error.message : String(error);
      set({
        isLoadingPlanner: false,
        lastError: message,
        statusMessage: `Planner projection failed: ${message}`,
      });
    }
  },
  runPlannerOptimization: async () => {
    ensureOptimizationProgressListener();
    const {
      selectedAlgorithm,
      optimizerAcknowledged,
      isRunningOptimization,
      plannerReference,
      plannerSettings,
    } = get();
    if (isRunningOptimization) {
      return;
    }
    if (!optimizerAcknowledged) {
      const message =
        "Review and confirm the optimizer warning above before choosing an algorithm.";
      set({ optimizerStatusMessage: message, statusMessage: message });
      return;
    }
    if (!selectedAlgorithm) {
      const message = "Choose an algorithm to enable the optimizer.";
      set({ optimizerStatusMessage: message, statusMessage: message });
      return;
    }
    const algorithmLabel =
      plannerReference?.algorithms.find((algorithm) => algorithm.id === selectedAlgorithm)
        ?.label ?? selectedAlgorithm;
    clearOptimizationResetTimer();
    set({
      isRunningOptimization: true,
      optimizationProgress: 0,
      optimizerStatusMessage: "Preparing optimization run...",
      statusMessage: `Running ${algorithmLabel} optimization...`,
      lastError: null,
    });
    try {
      const plannerResult = await plannerApi.runPlannerOptimization(
        plannerSettings,
        selectedAlgorithm,
      );
      const completionMessage = formatOptimizationCompletionStatus(plannerResult);
      set((state) => ({
        isRunningOptimization: false,
        optimizationProgress: 100,
        optimizerDirty: false,
        optimizerStatusMessage: completionMessage,
        plannerResult,
        selectedOperationsDay: 1,
        selectedOperationsPlanetId: resolveOperationsPlanet(
          state.selectedOperationsPlanetId,
          plannerResult,
          state.opsAnalysis,
          1,
        ),
        statusMessage: completionMessage,
      }));
      optimizationResetTimer = globalThis.setTimeout(() => {
        optimizationResetTimer = null;
        if (!get().isRunningOptimization) {
          set({ optimizationProgress: 0 });
        }
      }, 3000);
      await get().persistAppState();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      set({
        isRunningOptimization: false,
        optimizationProgress: 0,
        optimizerStatusMessage: `Optimization failed: ${message}`,
        lastError: message,
        statusMessage: `Optimization failed: ${message}`,
      });
    }
  },
  persistAppState: async () => {
    if (!get().isHydrated) return;
    set({ isPersisting: true });
    try {
      await plannerApi.saveAppState(toPersistedAppState(get()));
    } finally {
      set({ isPersisting: false });
    }
  },
  importPlannerSnapshot: async (snapshot) => {
    const record =
      snapshot && typeof snapshot === "object"
        ? (snapshot as Record<string, unknown>)
        : null;
    if (!record) {
      throw new Error("Invalid snapshot format.");
    }

    const guildRosters = normalizeSnapshotGuildRosters(record.guildRosters);
    const plannerResult = normalizeSnapshotPlannerResult(record.plannerResult);
    if (!Object.keys(guildRosters).length || !plannerResult) {
      throw new Error("Snapshot is missing roster or plan data.");
    }

    await plannerApi.importSessionState(guildRosters);
    const [guideTbOmicrons, guideUnitCatalog] = await Promise.all([
      refreshGuideOmicrons(),
      refreshGuideUnitCatalog(),
    ]);

    const guildSummary = normalizeSnapshotGuildSummary(record.guildSummary);
    const plannerProjection = normalizeSnapshotPlannerProjection(record.plannerProjection);
    const opsDefinitions = normalizeSnapshotOpsDefinitions(record.opsDefinitions);
    const opsAnalysis = normalizeSnapshotOpsAnalysis(record.opsAnalysis);

    clearOptimizationResetTimer();
    set((state) => {
      const nextGuildSummary = guildSummary ?? state.guildSummary;
      const plannerSettings = normalizePlannerSettings(record.plannerSettings, nextGuildSummary);
      const firstScannedMember = firstRosterMember(guildRosters);
      const persistedGuideMember =
        typeof record.selectedGuideMember === "string" ? record.selectedGuideMember : "";
      const persistedRosterMember =
        typeof record.selectedRosterMemberId === "string"
          ? record.selectedRosterMemberId
          : "";
      const selectedOperationsDay =
        typeof record.selectedOperationsDay === "number" &&
        Number.isFinite(record.selectedOperationsDay)
          ? record.selectedOperationsDay
          : 1;

      return {
        isHydrated: true,
        isFetchingGuild: false,
        isScanningRosters: false,
        isLoadingOps: false,
        isLoadingPlanner: false,
        isRunningOptimization: false,
        optimizationProgress: 0,
        sessionStatus: "ready",
        guildName: nextGuildSummary?.name ?? state.guildName,
        guildSummary: nextGuildSummary,
        guildRosters,
        opsDefinitions,
        opsAnalysis,
        guideTbOmicrons,
        guideUnitCatalog,
        plannerProjection,
        plannerResult,
        plannerSettings,
        optimizerDirty: false,
        optimizerStatusMessage: formatOptimizationCompletionStatus(plannerResult),
        primaryAllyCode:
          typeof record.primaryAllyCode === "string"
            ? record.primaryAllyCode
            : state.primaryAllyCode,
        selectedAlgorithm:
          typeof record.selectedAlgorithm === "string"
            ? record.selectedAlgorithm
            : plannerResult.selectedAlgorithm || state.selectedAlgorithm,
        optimizerAcknowledged:
          typeof record.optimizerAcknowledged === "boolean"
            ? record.optimizerAcknowledged
            : true,
        selectedChain:
          record.selectedChain === "ds" ||
          record.selectedChain === "mx" ||
          record.selectedChain === "ls"
            ? record.selectedChain
            : state.selectedChain,
        selectedOperationsDay,
        selectedOperationsPlanetId: resolveOperationsPlanet(
          typeof record.selectedOperationsPlanetId === "string"
            ? record.selectedOperationsPlanetId
            : state.selectedOperationsPlanetId,
          plannerResult,
          opsAnalysis,
          selectedOperationsDay,
        ),
        selectedGuideMember: hasRosterSelection(persistedGuideMember, guildRosters)
          ? persistedGuideMember
          : firstScannedMember,
        selectedGuideMission: isPersistedGuideMission(record.selectedGuideMission)
          ? record.selectedGuideMission
          : state.selectedGuideMission,
        expandedGuidePlanets: Array.isArray(record.expandedGuidePlanets)
          ? record.expandedGuidePlanets.filter(
              (entry): entry is string => typeof entry === "string",
            )
          : state.expandedGuidePlanets,
        guideData: normalizeGuideData(record.guideData),
        selectedRosterMemberId: hasRosterSelection(persistedRosterMember, guildRosters)
          ? persistedRosterMember
          : firstScannedMember,
        rosterSearch:
          typeof record.rosterSearch === "string"
            ? record.rosterSearch
            : state.rosterSearch,
        rosterFilter:
          typeof record.rosterFilter === "string"
            ? record.rosterFilter
            : state.rosterFilter,
        rosterSortKey:
          typeof record.rosterSortKey === "string"
            ? record.rosterSortKey
            : state.rosterSortKey,
        lastSyncAt:
          typeof record.savedAt === "string"
            ? record.savedAt
            : new Date().toISOString(),
        lastError: null,
        statusMessage:
          typeof record.savedAt === "string"
            ? `Snapshot loaded from ${new Date(record.savedAt).toLocaleString()}.`
            : "Snapshot loaded.",
      };
    });

    if (!opsDefinitions) {
      await get().loadOpsDefinitions();
    }
    if (!opsAnalysis) {
      await get().analyzePlatoons();
    }
    if (!plannerProjection) {
      await get().refreshPlannerProjection();
    }
    await get().persistAppState();
  },
  setPrimaryAllyCode: (primaryAllyCode) => set({ primaryAllyCode }),
  setGuildName: (guildName) => set({ guildName }),
  setActivePhase: (activePhase) => set({ activePhase }),
  advancePhase: () =>
    set((state) => ({
      activePhase: state.activePhase === 6 ? 1 : state.activePhase + 1,
    })),
  setSessionStatus: (sessionStatus) => set({ sessionStatus }),
  markSyncComplete: () =>
    set({
      sessionStatus: "ready",
      lastSyncAt: new Date().toISOString(),
    }),
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setSelectedAlgorithm: (selectedAlgorithm) => {
    set({ selectedAlgorithm });
    void get().persistAppState();
  },
  acknowledgeOptimizerWarning: () => {
    set({ optimizerAcknowledged: true });
    void get().persistAppState();
  },
  setPlannerMode: (key, value) => {
    set((state) => {
      if (key === "cmMode") {
        const nextSettings = {
          ...state.plannerSettings,
          cmMode: value,
        };
        return {
          plannerSettings: {
            ...nextSettings,
            cmBase: missionEstimateFallbackValue(
              "cmBase",
              value,
              state.plannerSettings.guildMembers,
            ),
            cmFalloff: missionEstimateFallbackValue(
              "cmFalloff",
              value,
              state.plannerSettings.guildMembers,
            ),
            fleetBase: missionEstimateFallbackValue(
              "fleetBase",
              value,
              state.plannerSettings.guildMembers,
            ),
            fleetFalloff: missionEstimateFallbackValue(
              "fleetFalloff",
              value,
              state.plannerSettings.guildMembers,
            ),
          },
          ...invalidateOptimizerState(state),
        };
      }

      return {
        plannerSettings: {
          ...state.plannerSettings,
          undepMode: value,
          dailyUndep: state.plannerSettings.dailyUndep.map((entry) =>
            sanitizeDailyUndepValue(
              {
                ...state.plannerSettings,
                undepMode: value,
              },
              entry,
            ),
          ),
        },
        ...invalidateOptimizerState(state),
      };
    });
    void get().refreshPlannerProjection();
    void get().persistAppState();
  },
  setPlannerNumber: (key, value) => {
    set((state) => {
      const nextSettings = { ...state.plannerSettings };
      if (key === "guildGp") {
        nextSettings.guildGp = Math.max(0, Math.round(normalizeFiniteNumber(value, 0)));
      } else if (key === "guildMembers" || key === "activeMembers") {
        const nextMembers = clampNumber(
          Math.round(normalizeFiniteNumber(value, nextSettings.guildMembers)),
          1,
          50,
        );
        nextSettings.guildMembers = nextMembers;
        nextSettings.activeMembers = nextMembers;
      } else {
        nextSettings[key] = sanitizeMissionEstimateSetting(nextSettings, key, value);
      }

      if (nextSettings.undepMode === "flat") {
        nextSettings.dailyUndep = nextSettings.dailyUndep.map((entry) =>
          sanitizeDailyUndepValue(nextSettings, entry),
        );
      }

      return {
        plannerSettings: nextSettings,
        ...invalidateOptimizerState(state),
      };
    });
    void get().refreshPlannerProjection();
    void get().persistAppState();
  },
  setDailyUndep: (dayIndex, value) => {
    set((state) => ({
      plannerSettings: {
        ...state.plannerSettings,
        dailyUndep: state.plannerSettings.dailyUndep.map((entry, index) =>
          index === dayIndex
            ? sanitizeDailyUndepValue(state.plannerSettings, value)
            : entry,
        ),
      },
      ...invalidateOptimizerState(state),
    }));
    void get().refreshPlannerProjection();
    void get().persistAppState();
  },
  fillDailyUndepFromDayOne: () => {
    set((state) => {
      const dayOneValue = sanitizeDailyUndepValue(
        state.plannerSettings,
        state.plannerSettings.dailyUndep[0] ?? 0,
      );
      return {
        plannerSettings: {
          ...state.plannerSettings,
          dailyUndep: Array.from({ length: 6 }, (_, index) =>
            index === 0 ? dayOneValue : dayOneValue,
          ),
        },
        ...invalidateOptimizerState(state),
      };
    });
    void get().refreshPlannerProjection();
    void get().persistAppState();
  },
  setPlanetPlannerState: (planetId, patch) => {
    set((state) => {
      const sanitizedPatch = sanitizePlanetPlannerPatch(state.plannerSettings, patch);
      return {
        plannerSettings: {
          ...state.plannerSettings,
          planetState: {
            ...state.plannerSettings.planetState,
            [planetId]: {
              ...defaultPlanetPlannerState(),
              ...state.plannerSettings.planetState[planetId],
              ...sanitizedPatch,
            },
          },
        },
        ...invalidateOptimizerState(state),
      };
    });
    void get().refreshPlannerProjection();
    void get().persistAppState();
  },
  setPlanetMissionOverride: (planetId, missionId, patch) => {
    set((state) => {
      const sanitizedPatch = sanitizeMissionOverridePatch(state.plannerSettings, patch);
      const currentPlanetState = {
        ...defaultPlanetPlannerState(),
        ...state.plannerSettings.planetState[planetId],
      };
      const currentMissionState = {
        ...defaultMissionOverrideState(),
        ...currentPlanetState.missionOverrides[missionId],
      };
      return {
        plannerSettings: {
          ...state.plannerSettings,
          planetState: {
            ...state.plannerSettings.planetState,
            [planetId]: {
              ...currentPlanetState,
              missionOverrides: {
                ...currentPlanetState.missionOverrides,
                [missionId]: {
                  ...currentMissionState,
                  ...sanitizedPatch,
                },
              },
            },
          },
        },
        ...invalidateOptimizerState(state),
      };
    });
    void get().refreshPlannerProjection();
    void get().persistAppState();
  },
  setPlanetHold: (planetId) => {
    set((state) => ({
      plannerSettings: {
        ...state.plannerSettings,
        planetHold: planetId
          ? {
              planetId,
              days: state.plannerSettings.planetHold?.planetId === planetId
                ? state.plannerSettings.planetHold.days
                : 1,
            }
          : null,
      },
      ...invalidateOptimizerState(state),
    }));
    void get().persistAppState();
  },
  setPlanetHoldDays: (days) => {
    set((state) => {
      if (!state.plannerSettings.planetHold) {
        return state;
      }
      return {
        plannerSettings: {
          ...state.plannerSettings,
          planetHold: {
            ...state.plannerSettings.planetHold,
            days: clampNumber(Math.round(days || 1), 1, 6),
          },
        },
        ...invalidateOptimizerState(state),
      };
    });
    void get().persistAppState();
  },
  applyMissionEstimatesToPlanner: () => {
    set((state) => {
      const planets = state.plannerReference?.planets ?? [];
      const planetState = { ...state.plannerSettings.planetState };
      for (const planet of planets) {
        planetState[planet.id] = {
          ...defaultPlanetPlannerState(),
          ...planetState[planet.id],
          ...buildPlanetOverridePatch(state.plannerSettings, planet.id),
        };
      }
      return {
        plannerSettings: {
          ...state.plannerSettings,
          planetState,
        },
        ...invalidateOptimizerState(state),
        statusMessage: "Applied mission estimates to the planet planner.",
      };
    });
    void get().refreshPlannerProjection();
    void get().persistAppState();
  },
  resetWorkspace: async () => {
    await plannerApi.resetScanSession();
    clearOptimizationResetTimer();
    const nextState = createInitialState();
    set({
      ...nextState,
      isHydrated: true,
      statusMessage: "Workspace reset.",
      plannerReference: get().plannerReference,
    });
    await get().persistAppState();
  },
  setSelectedChain: (selectedChain) => {
    set({ selectedChain });
    void get().persistAppState();
  },
  setSelectedOperationsDay: (selectedOperationsDay) => {
    set((state) => ({
      selectedOperationsDay,
      selectedOperationsPlanetId: resolveOperationsPlanet(
        state.selectedOperationsPlanetId,
        state.plannerResult,
        state.opsAnalysis,
        selectedOperationsDay,
      ),
    }));
    void get().persistAppState();
  },
  setSelectedOperationsPlanetId: (selectedOperationsPlanetId) => {
    set({ selectedOperationsPlanetId });
    void get().persistAppState();
  },
  setSelectedGuideMember: (selectedGuideMember) => {
    set({ selectedGuideMember });
    void get().persistAppState();
  },
  setSelectedGuideMission: (planetId, missionId) => {
    set((state) => ({
      selectedGuideMission: { planetId, missionId },
      expandedGuidePlanets: state.expandedGuidePlanets.includes(planetId)
        ? state.expandedGuidePlanets
        : [...state.expandedGuidePlanets, planetId],
      guideEditorDifficulty: "auto",
    }));
    void get().persistAppState();
  },
  toggleGuidePlanet: (planetId) => {
    set((state) => ({
      expandedGuidePlanets: state.expandedGuidePlanets.includes(planetId)
        ? state.expandedGuidePlanets.filter((entry) => entry !== planetId)
        : [...state.expandedGuidePlanets, planetId],
    }));
    void get().persistAppState();
  },
  saveGuideSquad: (planetId, missionId, squad) => {
    let result: GuideMutationResult = {
      ok: false,
      count: 0,
      reason: "Guide squad could not be saved.",
    };
    set((state) => {
      const missionKey = guideMissionKey(planetId, missionId);
      const existing = state.guideData.squads[missionKey] ?? [];
      const existingIndex = existing.findIndex((entry) => entry.id === squad.id);
      if (existingIndex < 0 && existing.length >= GUIDE_MISSION_LIMIT) {
        result = {
          ok: false,
          count: existing.length,
          reason: `This mission has reached the ${GUIDE_MISSION_LIMIT}-guide limit.`,
        };
        return {
          statusMessage: result.reason,
        };
      }
      const order =
        existingIndex >= 0
          ? existing[existingIndex]?.order ?? existingIndex
          : existing.length;
      const normalized = normalizeGuideSquad({
        ...squad,
        order,
      });
      const nextMissionSquads =
        existingIndex >= 0
          ? existing.map((entry, index) => (index === existingIndex ? normalized : entry))
          : [...existing, normalized];
      const sortedSquads = sortGuideSquads(nextMissionSquads);
      result = {
        ok: true,
        count: sortedSquads.length,
      };

      return {
        guideData: {
          ...state.guideData,
          squads: {
            ...state.guideData.squads,
            [missionKey]: sortedSquads,
          },
        },
        statusMessage: "Guide squad saved.",
      };
    });
    if (result.ok) {
      void get().persistAppState();
    }
    return result;
  },
  copyGuideSquad: (sourcePlanetId, sourceMissionId, squadId, targetPlanetId, targetMissionId) => {
    let result: GuideMutationResult = {
      ok: false,
      count: 0,
      reason: "Guide squad could not be copied.",
    };
    set((state) => {
      const sourceMissionKey = guideMissionKey(sourcePlanetId, sourceMissionId);
      const targetMissionKey = guideMissionKey(targetPlanetId, targetMissionId);
      const sourceSquad =
        state.guideData.squads[sourceMissionKey]?.find((entry) => entry.id === squadId) ?? null;
      if (!sourceSquad) {
        result = {
          ok: false,
          count: state.guideData.squads[targetMissionKey]?.length ?? 0,
          reason: "The selected guide squad could not be found.",
        };
        return {
          statusMessage: result.reason,
        };
      }

      const existing = state.guideData.squads[targetMissionKey] ?? [];
      if (existing.length >= GUIDE_MISSION_LIMIT) {
        result = {
          ok: false,
          count: existing.length,
          reason: `The target mission has reached the ${GUIDE_MISSION_LIMIT}-guide limit.`,
        };
        return {
          statusMessage: result.reason,
        };
      }

      const copiedSquad = normalizeGuideSquad({
        ...sourceSquad,
        id: createGuideSquadId(),
        order: existing.length,
      });
      const sortedSquads = sortGuideSquads([...existing, copiedSquad]);
      result = {
        ok: true,
        count: sortedSquads.length,
      };

      return {
        guideData: {
          ...state.guideData,
          squads: {
            ...state.guideData.squads,
            [targetMissionKey]: sortedSquads,
          },
        },
        statusMessage: "Guide squad copied.",
      };
    });
    if (result.ok) {
      void get().persistAppState();
    }
    return result;
  },
  moveGuideSquad: (planetId, missionId, squadId, delta) => {
    set((state) => {
      const missionKey = guideMissionKey(planetId, missionId);
      const existing = [...(state.guideData.squads[missionKey] ?? [])].sort(
        (left, right) => left.order - right.order || left.id.localeCompare(right.id),
      );
      const fromIndex = existing.findIndex((entry) => entry.id === squadId);
      const toIndex = fromIndex + delta;
      if (fromIndex < 0 || toIndex < 0 || toIndex >= existing.length) {
        return state;
      }

      const [moved] = existing.splice(fromIndex, 1);
      existing.splice(toIndex, 0, moved);
      const nextMissionSquads = existing.map((entry, index) => ({ ...entry, order: index }));

      return {
        guideData: {
          ...state.guideData,
          squads: {
            ...state.guideData.squads,
            [missionKey]: nextMissionSquads,
          },
        },
        statusMessage: "Guide squad order updated.",
      };
    });
    void get().persistAppState();
  },
  deleteGuideSquad: (planetId, missionId, squadId) => {
    set((state) => {
      const missionKey = guideMissionKey(planetId, missionId);
      const existing = state.guideData.squads[missionKey] ?? [];
      const nextMissionSquads = existing
        .filter((entry) => entry.id !== squadId)
        .map((entry, index) => ({ ...entry, order: index }));

      return {
        guideData: {
          ...state.guideData,
          squads: {
            ...state.guideData.squads,
            [missionKey]: nextMissionSquads,
          },
        },
        statusMessage: "Guide squad deleted.",
      };
    });
    void get().persistAppState();
  },
  importGuideData: async (guideData) => {
    set({
      guideData: normalizeGuideData(guideData),
      statusMessage: "Guide file imported.",
    });
    await get().persistAppState();
  },
  openGuideEditor: (guideEditorDifficulty = "auto") =>
    set({ guideEditorOpen: true, guideEditorDifficulty }),
  closeGuideEditor: () => set({ guideEditorOpen: false }),
  setGuideEditorDifficulty: (guideEditorDifficulty) =>
    set({ guideEditorDifficulty }),
  setSelectedRosterMemberId: (selectedRosterMemberId) => {
    set({ selectedRosterMemberId });
    void get().persistAppState();
  },
  setRosterSearch: (rosterSearch) => set({ rosterSearch }),
  setRosterFilter: (rosterFilter) => set({ rosterFilter }),
  setRosterSortKey: (rosterSortKey) => set({ rosterSortKey }),
  };
});
