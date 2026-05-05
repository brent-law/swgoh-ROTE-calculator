import { create } from "zustand";
import {
  plannerApi,
  type ComlinkStatus,
  type GuideTbOmicronMap,
  type GuildRosters,
  type GuildSummary,
  type OpsDefinitions,
  type PersistedPlannerState,
  type PlatoonAnalysisMap,
} from "../lib/plannerApi";
import {
  type ChainKey,
  type GuideDifficulty,
  guideMembers,
  guideMissionKey,
  operationsDayPickers,
  rosterMembers,
} from "../features/rotePlanner/mockData";

export type SessionStatus = "idle" | "syncing" | "ready";

const offlineComlinkStatus: ComlinkStatus = {
  comlink: "offline",
  port: 3000,
  version: "?",
  binaryPath: null,
  managedProcess: false,
  message: null,
};

type PlannerState = {
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
  guideEditorOpen: boolean;
  guideEditorDifficulty: GuideDifficulty;
  selectedRosterMemberId: string;
  rosterSearch: string;
  rosterFilter: string;
  rosterSortKey: string;
  primaryAllyCode: string;
  isHydrated: boolean;
  isFetchingGuild: boolean;
  isScanningRosters: boolean;
  isLoadingOps: boolean;
  isPersisting: boolean;
  statusMessage: string;
  lastError: string | null;
  comlinkStatus: ComlinkStatus;
  guildSummary: GuildSummary | null;
  guildRosters: GuildRosters;
  opsDefinitions: OpsDefinitions | null;
  opsAnalysis: PlatoonAnalysisMap | null;
  guideTbOmicrons: GuideTbOmicronMap;
  hydrateFromBackend: () => Promise<void>;
  refreshComlinkStatus: () => Promise<void>;
  retryComlink: () => Promise<void>;
  stopComlink: () => Promise<void>;
  fetchGuildByAllyCode: (allyCode: string) => Promise<void>;
  scanGuildRosters: () => Promise<void>;
  loadOpsDefinitions: () => Promise<void>;
  analyzePlatoons: () => Promise<void>;
  persistAppState: () => Promise<void>;
  setPrimaryAllyCode: (primaryAllyCode: string) => void;
  setGuildName: (guildName: string) => void;
  setActivePhase: (activePhase: number) => void;
  advancePhase: () => void;
  setSessionStatus: (sessionStatus: SessionStatus) => void;
  markSyncComplete: () => void;
  toggleSidebar: () => void;
  resetWorkspace: () => Promise<void>;
  setSelectedChain: (selectedChain: ChainKey) => void;
  setSelectedOperationsDay: (selectedOperationsDay: number) => void;
  setSelectedOperationsPlanetId: (selectedOperationsPlanetId: string) => void;
  setSelectedGuideMember: (selectedGuideMember: string) => void;
  setSelectedGuideMission: (planetId: string, missionId: string) => void;
  toggleGuidePlanet: (planetId: string) => void;
  openGuideEditor: (difficulty?: GuideDifficulty) => void;
  closeGuideEditor: () => void;
  setGuideEditorDifficulty: (guideEditorDifficulty: GuideDifficulty) => void;
  setSelectedRosterMemberId: (selectedRosterMemberId: string) => void;
  setRosterSearch: (rosterSearch: string) => void;
  setRosterFilter: (rosterFilter: string) => void;
  setRosterSortKey: (rosterSortKey: string) => void;
};

function getDefaultOperationsPlanet(day: number) {
  return (
    operationsDayPickers.find((entry) => entry.day === day)?.planetIds[0] ??
    operationsDayPickers[0].planetIds[0]
  );
}

function createInitialState() {
  return {
    guildName: "Crimson Order",
    activePhase: 1,
    sessionStatus: "idle" as SessionStatus,
    lastSyncAt: null,
    sidebarCollapsed: false,
    selectedChain: "ds" as ChainKey,
    selectedOperationsDay: operationsDayPickers[0].day,
    selectedOperationsPlanetId: operationsDayPickers[0].planetIds[0],
    selectedGuideMember: guideMembers[0],
    selectedGuideMission: {
      planetId: "mustafar",
      missionId: "cm1",
    },
    expandedGuidePlanets: ["mustafar", "corellia", "coruscant"],
    guideEditorOpen: false,
    guideEditorDifficulty: "auto" as GuideDifficulty,
    selectedRosterMemberId: rosterMembers[0].id,
    rosterSearch: "",
    rosterFilter: "all",
    rosterSortKey: "name",
    primaryAllyCode: "",
    isHydrated: false,
    isFetchingGuild: false,
    isScanningRosters: false,
    isLoadingOps: false,
    isPersisting: false,
    statusMessage: "Ready to import a guild.",
    lastError: null,
    comlinkStatus: offlineComlinkStatus,
    guildSummary: null as GuildSummary | null,
    guildRosters: {} as GuildRosters,
    opsDefinitions: null as OpsDefinitions | null,
    opsAnalysis: null as PlatoonAnalysisMap | null,
    guideTbOmicrons: {} as GuideTbOmicronMap,
  };
}

function toPersistedAppState(state: PlannerState): PersistedPlannerState {
  return {
    primaryAllyCode: state.primaryAllyCode,
    selectedChain: state.selectedChain,
    selectedOperationsDay: state.selectedOperationsDay,
    selectedOperationsPlanetId: state.selectedOperationsPlanetId,
    selectedGuideMember: state.selectedGuideMember,
    selectedGuideMission: state.selectedGuideMission,
    expandedGuidePlanets: state.expandedGuidePlanets,
    guideEditorDifficulty: state.guideEditorDifficulty,
    selectedRosterMemberId: state.selectedRosterMemberId,
    rosterSearch: state.rosterSearch,
    rosterFilter: state.rosterFilter,
    rosterSortKey: state.rosterSortKey,
  };
}

function firstGuildMember(summary: GuildSummary | null) {
  return summary?.members[0]?.displayName ?? guideMembers[0];
}

function firstRosterMember(summary: GuildSummary | null, guildRosters: GuildRosters) {
  return (
    Object.keys(guildRosters)[0] ??
    summary?.members[0]?.allyCode ??
    rosterMembers[0].id
  );
}

function resolvePlanetSelection(
  selectedPlanetId: string,
  opsAnalysis: PlatoonAnalysisMap | null,
  selectedOperationsDay: number,
) {
  if (!opsAnalysis) return selectedPlanetId;
  const analysisKeys = Object.keys(opsAnalysis);
  if (analysisKeys.includes(selectedPlanetId)) return selectedPlanetId;
  return analysisKeys[0] ?? getDefaultOperationsPlanet(selectedOperationsDay);
}

async function refreshGuideOmicrons() {
  try {
    const response = await plannerApi.getGuideTbOmicrons();
    return response.units;
  } catch {
    return {};
  }
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

export const usePlannerStore = create<PlannerState>()((set, get) => ({
  ...createInitialState(),
  hydrateFromBackend: async () => {
    if (get().isHydrated) return;
    set({ sessionStatus: "syncing", statusMessage: "Restoring planner state..." });
    try {
      const bootstrap = await plannerApi.getBootstrapState();
      const persisted = bootstrap.appState ?? {};
      const guildSummary = bootstrap.session.guildSummary;
      const guildRosters = bootstrap.session.guildRosters ?? {};
      const persistedGuideMission = isPersistedGuideMission(
        persisted.selectedGuideMission,
      )
        ? persisted.selectedGuideMission
        : undefined;

      set((state) => ({
        isHydrated: true,
        sessionStatus: "ready",
        guildName: guildSummary?.name ?? state.guildName,
        guildSummary,
        guildRosters,
        comlinkStatus: bootstrap.comlinkStatus,
        primaryAllyCode:
          typeof persisted.primaryAllyCode === "string"
            ? persisted.primaryAllyCode
            : state.primaryAllyCode,
        selectedChain:
          persisted.selectedChain === "ds" ||
          persisted.selectedChain === "mx" ||
          persisted.selectedChain === "ls"
            ? persisted.selectedChain
            : state.selectedChain,
        selectedOperationsDay:
          typeof persisted.selectedOperationsDay === "number"
            ? persisted.selectedOperationsDay
            : state.selectedOperationsDay,
        selectedOperationsPlanetId:
          typeof persisted.selectedOperationsPlanetId === "string"
            ? persisted.selectedOperationsPlanetId
            : resolvePlanetSelection(
                state.selectedOperationsPlanetId,
                state.opsAnalysis,
                state.selectedOperationsDay,
              ),
        selectedGuideMember:
          typeof persisted.selectedGuideMember === "string"
            ? persisted.selectedGuideMember
            : firstGuildMember(guildSummary),
        selectedGuideMission: persistedGuideMission ?? state.selectedGuideMission,
        expandedGuidePlanets: Array.isArray(persisted.expandedGuidePlanets)
          ? persisted.expandedGuidePlanets.filter(
              (entry): entry is string => typeof entry === "string",
            )
          : state.expandedGuidePlanets,
        guideEditorDifficulty:
          persisted.guideEditorDifficulty === "auto" ||
          persisted.guideEditorDifficulty === "easy" ||
          persisted.guideEditorDifficulty === "medium" ||
          persisted.guideEditorDifficulty === "hard"
            ? persisted.guideEditorDifficulty
            : state.guideEditorDifficulty,
        selectedRosterMemberId:
          typeof persisted.selectedRosterMemberId === "string"
            ? persisted.selectedRosterMemberId
            : firstRosterMember(guildSummary, guildRosters),
        rosterSearch:
          typeof persisted.rosterSearch === "string"
            ? persisted.rosterSearch
            : state.rosterSearch,
        rosterFilter:
          typeof persisted.rosterFilter === "string"
            ? persisted.rosterFilter
            : state.rosterFilter,
        rosterSortKey:
          typeof persisted.rosterSortKey === "string"
            ? persisted.rosterSortKey
            : state.rosterSortKey,
        statusMessage:
          bootstrap.comlinkStatus.comlink === "online"
            ? "Planner ready."
            : bootstrap.comlinkStatus.message ?? "Planner ready in offline mode.",
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      set({
        isHydrated: true,
        sessionStatus: "ready",
        lastError: message,
        statusMessage: `Restore skipped: ${message}`,
      });
    }
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
      set({
        comlinkStatus,
        statusMessage: "swgoh-comlink stopped.",
      });
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
      const guideMember = firstGuildMember(response.summary);
      set({
        isFetchingGuild: false,
        sessionStatus: "ready",
        guildSummary: response.summary,
        guildRosters: {},
        opsAnalysis: null,
        guildName: response.summary.name,
        primaryAllyCode: allyCode,
        selectedGuideMember: guideMember,
        selectedRosterMemberId: firstRosterMember(response.summary, {}),
        lastSyncAt: new Date().toISOString(),
        statusMessage: `Loaded ${response.summary.name} (${response.summary.members.length} members).`,
      });
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
    const guildSummary = get().guildSummary;
    if (!guildSummary?.members.length) {
      set({ statusMessage: "Fetch guild data first." });
      return;
    }

    set({
      isScanningRosters: true,
      sessionStatus: "syncing",
      statusMessage: "Scanning guild rosters through the Rust backend...",
      lastError: null,
    });

    try {
      const response = await plannerApi.scanGuildRosters(
        guildSummary.members.map((member) => ({
          key: member.allyCode || member.playerId,
          displayName: member.displayName,
        })),
      );
      const guideTbOmicrons = await refreshGuideOmicrons();
      set((state) => ({
        isScanningRosters: false,
        sessionStatus: "ready",
        guildRosters: response.guildRosters,
        opsAnalysis: null,
        guideTbOmicrons,
        selectedRosterMemberId: firstRosterMember(guildSummary, response.guildRosters),
        selectedGuideMember: state.selectedGuideMember || firstGuildMember(guildSummary),
        lastSyncAt: new Date().toISOString(),
        statusMessage:
          response.failedMembers.length === 0
            ? `Roster scan complete for ${response.scannedMembers} members.`
            : `Roster scan finished with ${response.failedMembers.length} failures.`,
      }));
      await get().loadOpsDefinitions();
      await get().analyzePlatoons();
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
      set((state) => ({
        isLoadingOps: false,
        opsDefinitions: response.defs,
        selectedOperationsPlanetId: resolvePlanetSelection(
          state.selectedOperationsPlanetId,
          state.opsAnalysis,
          state.selectedOperationsDay,
        ),
      }));
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
        selectedOperationsPlanetId: resolvePlanetSelection(
          state.selectedOperationsPlanetId,
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
  persistAppState: async () => {
    if (!get().isHydrated) return;
    set({ isPersisting: true });
    try {
      await plannerApi.saveAppState(toPersistedAppState(get()));
    } finally {
      set({ isPersisting: false });
    }
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
  resetWorkspace: async () => {
    await plannerApi.resetScanSession();
    const nextState = createInitialState();
    set({
      ...nextState,
      isHydrated: true,
      statusMessage: "Workspace reset.",
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
      selectedOperationsPlanetId: resolvePlanetSelection(
        getDefaultOperationsPlanet(selectedOperationsDay),
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
      guideEditorDifficulty:
        guideMissionKey(planetId, missionId) === guideMissionKey("mustafar", "cm1")
          ? "auto"
          : "easy",
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
  openGuideEditor: (guideEditorDifficulty = "auto") =>
    set({
      guideEditorOpen: true,
      guideEditorDifficulty,
    }),
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
}));
