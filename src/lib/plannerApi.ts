import { invoke } from "@tauri-apps/api/core";

export type CommandError = {
  kind: string;
  message: string;
};

export type GuildMember = {
  playerId: string;
  allyCode: string;
  displayName: string;
  galacticPower: number;
};

export type GuildSummary = {
  name: string;
  gp: number;
  members: GuildMember[];
};

export type SimplifiedSkillRow = {
  id: string;
  skillId: string;
  name: string;
  tier: number;
  level: number;
  maxTier: number;
  kind: string;
  isZeta: boolean;
  isOmicron: boolean;
  omicronArea: number;
  hasZeta: boolean;
  hasOmicron: boolean;
  unlocked: boolean;
};

export type SimplifiedRosterUnit = {
  defId: string;
  name: string;
  rarity: number;
  gear: number;
  relic: number;
  combatType: number;
  modsPresent: boolean;
  speed: number;
  power: number;
  zetas: number;
  omicrons: number;
  skills: SimplifiedSkillRow[];
};

export type GuildRosters = Record<string, SimplifiedRosterUnit[]>;

export type PlatoonRequirement = {
  defId: string;
  name: string;
  minRarity: number;
  minRelic: number;
};

export type OpsDefinitions = Record<string, PlatoonRequirement[][]>;

export type PlatoonSlotAnalysis = {
  defId: string;
  name: string;
  need: number;
  have: number;
  minRarity: number;
  minRelic: number;
  ok: boolean;
};

export type PlatoonAnalysisEntry = {
  fillable: boolean;
  slots: PlatoonSlotAnalysis[];
};

export type PlatoonAnalysisMap = Record<string, PlatoonAnalysisEntry[]>;

export type GuideTbOmicron = {
  skillId: string;
  name: string;
  kind: string;
  omicronArea: number;
};

export type GuideTbOmicronMap = Record<string, GuideTbOmicron[]>;

export type GuideTbOmicronRequirement = {
  unitDefId: string;
  unitName: string;
  skillId: string;
  skillName: string;
};

export type GuideSquad = {
  id: string;
  leader: string;
  leaderDefId: string;
  members: string[];
  memberDefIds: string[];
  notes: string;
  videoUrl: string;
  requiredTbOmicrons: GuideTbOmicronRequirement[];
  difficulty: string;
  order: number;
};

export type GuideDataSnapshot = {
  version: number;
  squads: Record<string, GuideSquad[]>;
};

export type PlannerPlanetState = {
  cmRateOverride: number | null;
  fleetRateOverride: number | null;
  cmCountOverride: number | null;
  fleetCountOverride: number | null;
  preloaded: number;
  smReady: boolean;
  smCount: number;
  missionOverrides: Record<string, PlannerMissionOverrideState>;
};

export type PlannerMissionOverrideState = {
  rateOverride: number | null;
  countOverride: number | null;
};

export type PlannerPlanetHoldConfig = {
  planetId: string;
  days: number;
};

export type PlannerSettings = {
  guildGp: number;
  guildMembers: number;
  activeMembers: number;
  cmMode: string;
  undepMode: string;
  cmBase: number;
  cmFalloff: number;
  fleetBase: number;
  fleetFalloff: number;
  dailyUndep: number[];
  planetState: Record<string, PlannerPlanetState>;
  planetHold: PlannerPlanetHoldConfig | null;
};

export type PersistedPlannerMissionOverrideState = {
  rateOverride: number | null;
  countOverride: number | null;
};

export type PersistedPlannerPlanetState = {
  cmRateOverride: number | null;
  fleetRateOverride: number | null;
  cmCountOverride: number | null;
  fleetCountOverride: number | null;
  smReady: boolean;
  smCount: number;
  missionOverrides: Record<string, PersistedPlannerMissionOverrideState>;
};

export type PersistedPlannerSettings = {
  cmMode: string;
  undepMode: string;
  cmBase: number;
  cmFalloff: number;
  fleetBase: number;
  fleetFalloff: number;
  dailyUndep: number[];
  planetState: Record<string, PersistedPlannerPlanetState>;
};

export type PlannerMissionDefinition = {
  id: string;
  label: string;
  missionType: string;
  pointsSingle?: number | null;
  points?: number | null;
  rewardText?: string | null;
  unitsText: string;
  note?: string | null;
  unlocks?: string | null;
};

export type PlannerPlanetDefinition = {
  id: string;
  name: string;
  align: string;
  chain: string;
  zone: number;
  phase: number;
  cmPoints: number;
  fleetPoints: number;
  opsVal: number;
  stars: number[];
  minRelic: number;
  unlockedBy?: string | null;
  unlockedAt?: number | null;
  smLabel?: string | null;
  smThreshold?: number | null;
  missions: PlannerMissionDefinition[];
};

export type PlannerAlgorithmMeta = {
  id: string;
  label: string;
  quality: string;
  complexity: string;
  runtime: string;
  description: string;
};

export type PlannerReferenceResponse = {
  planets: PlannerPlanetDefinition[];
  algorithms: PlannerAlgorithmMeta[];
};

export type PlannerMissionEstimate = {
  id: string;
  label: string;
  completion: string;
  points: number;
};

export type PlannerPlanetCard = {
  id: string;
  name: string;
  align: string;
  chain: string;
  zone: number;
  phase: number;
  status: string;
  capability: string;
  estimate: number;
  target: number;
  progress: number;
  note: string;
  bonusLocked: boolean;
  capabilityCount: number;
  capabilityTotal: number;
  recommendedCmRate: number;
  recommendedFleetRate: number;
  operationsFilled: number;
  operationsTotal: number;
  operationsNote: string;
  combatMissions: PlannerMissionEstimate[];
  fleetMissions: PlannerMissionEstimate[];
  specialMissions: PlannerMissionDefinition[];
};

export type PlannerSummary = {
  estimatedStars: number;
  maxPossibleStars: number;
  bonusEligibleCount: number;
  bonusActiveCount: number;
  opsFilled: number;
  opsTotal: number;
  opsPoints: number;
  scannedMembers: number;
  rosterCoverage: string;
};

export type PlannerProjectionResponse = {
  summary: PlannerSummary;
  planetCards: Record<string, PlannerPlanetCard>;
};

export type PlannerChainDayResult = {
  key: string;
  status: string;
  planetId?: string | null;
  planetName?: string | null;
  align?: string | null;
  pts: number;
  gpDeployed: number;
  stars: number;
  pctOf3: number;
  banked: number;
  tomorrowEst: number;
  threshold1star: number;
  carryInPts: number;
  missionPts: number;
  opsPts: number;
};

export type PlannerBonusPlanetDayResult = {
  planetId: string;
  planetName: string;
  align: string;
  pts: number;
  stars: number;
  carryInPts: number;
  missionPts: number;
  opsPts: number;
  gpDeployed: number;
  carryOver: number;
  activeFromDay: number;
  unlockedOnDay: number;
};

export type PlannerCompletedPlatoon = {
  pid: string;
  platoonIdx: number;
  points: number;
};

export type PlannerOpsAssignmentEntry = {
  day: number;
  reqIdx: number;
  defId: string;
  name: string;
  minRelic: number;
  minRarity: number;
  allyCode: string;
  unitKey: string;
};

export type PlannerOpsAssignmentGroup = {
  platoonIdx: number;
  completed: boolean;
  pointsEarned: number;
  entries: PlannerOpsAssignmentEntry[];
};

export type PlannerOpsPlanetDaySummary = {
  priority: number;
  label: string;
  completedToday: number;
  slotsFilled: number;
  pointsEarned: number;
  assignments: PlannerOpsAssignmentGroup[];
};

export type PlannerOpsPlanetStats = {
  completedPlatoons: number;
  totalPlatoons: number;
  totalSlots: number;
  slotsFilled: number;
  points: number;
};

export type PlannerOpsDaySummary = {
  day: number;
  pointsEarned: number;
  slotsFilled: number;
  completedPlatoons: PlannerCompletedPlatoon[];
  planets: Record<string, PlannerOpsPlanetDaySummary>;
};

export type PlannerOpsSummary = {
  totalCompleted: number;
  totalPlatoons: number;
  totalPoints: number;
  planetStats: Record<string, PlannerOpsPlanetStats>;
  days: PlannerOpsDaySummary[];
};

export type PlannerDayResult = {
  day: number;
  gpAvail: number;
  gpUsed: number;
  starsDay: number;
  chains: Record<string, PlannerChainDayResult>;
  notices: string[];
  bonusPlanets: PlannerBonusPlanetDayResult[];
  opsPoints: number;
  opsCompleted: PlannerCompletedPlatoon[];
  opsPlanets: Record<string, PlannerOpsPlanetDaySummary>;
};

export type PlannerAlgorithmScore = {
  algorithm: string;
  label: string;
  score: number;
};

export type PlannerOptimizationResponse = {
  selectedAlgorithm: string;
  bestAlgorithm: string;
  totalStars: number;
  summary: PlannerSummary;
  algorithmScores: PlannerAlgorithmScore[];
  dayPlan: PlannerDayResult[];
  opsSummary: PlannerOpsSummary;
};

export type PlannerOptimizationProgressEvent = {
  phase: string;
  selectedAlgorithm: string;
  algorithm: string;
  overallFraction: number;
  algorithmFraction: number;
  bestScore: number;
  message: string;
};

export type ComlinkStatus = {
  comlink: "online" | "offline" | string;
  port: number;
  version: string;
  binaryPath: string | null;
  managedProcess: boolean;
  message: string | null;
};

export type BootstrapState = {
  appState: Record<string, unknown>;
  comlinkStatus: ComlinkStatus;
  session: {
    guildSummary: GuildSummary | null;
    guildRosters: GuildRosters;
    opsSource: string | null;
  };
};

export type BulkRosterScanResponse = {
  scannedMembers: number;
  failedMembers: Array<{
    key: string;
    displayName: string;
    error: string;
  }>;
  guildRosters: GuildRosters;
  powerReady: boolean;
  powerError: string;
};

export type PlatoonAnalysisResponse = {
  status: string;
  analysis: PlatoonAnalysisMap;
  planetCount: number;
  rosterCount: number;
};

export type GuideTbOmicronResponse = {
  status: string;
  units: GuideTbOmicronMap;
  omicronArea: number;
  areaLabel: string;
};

export type GuideUnitCatalogEntry = {
  defId: string;
  name: string;
  combatType: number;
};

export type GuideUnitCatalogResponse = {
  status: string;
  units: GuideUnitCatalogEntry[];
};

export type OpsDefinitionsResponse = {
  status: string;
  defs: OpsDefinitions;
  count: number;
  source: string;
  sourceLabel: string;
};

export type ExportBundleFile = {
  name: string;
  contents: string;
};

export type WriteExportBundleResponse = {
  directory: string;
  openPath: string;
  filesWritten: number;
};

export type ExportPreviewDocument = {
  id: string;
  title: string;
  html: string;
};

export type ExportPreviewResponse = {
  title: string;
  initialDocumentId: string;
  documents: ExportPreviewDocument[];
};

export type OpenExportPreviewResponse = {
  token: string;
  windowLabel: string;
};

export type PersistedAppState = {
  primaryAllyCode?: string;
  plannerSettings?: PersistedPlannerSettings;
  guideData?: GuideDataSnapshot;
};

export type PersistedPlannerState = {
  primaryAllyCode?: string;
  plannerSettings?: PlannerSettings;
  selectedAlgorithm?: string;
  optimizerAcknowledged?: boolean;
  selectedChain?: string;
  selectedOperationsDay?: number;
  selectedOperationsPlanetId?: string;
  selectedGuideMember?: string;
  selectedGuideMission?: {
    planetId: string;
    missionId: string;
  };
  expandedGuidePlanets?: string[];
  guideData?: GuideDataSnapshot;
  guideEditorDifficulty?: string;
  selectedRosterMemberId?: string;
  rosterSearch?: string;
  rosterFilter?: string;
  rosterSortKey?: string;
};

async function invokeCommand<T>(command: string, args?: Record<string, unknown>) {
  return invoke<T>(command, args);
}

export const plannerApi = {
  getBootstrapState() {
    return invokeCommand<BootstrapState>("get_bootstrap_state");
  },
  refreshComlinkStatus() {
    return invokeCommand<ComlinkStatus>("refresh_comlink_status");
  },
  startComlink() {
    return invokeCommand<ComlinkStatus>("start_comlink");
  },
  stopComlink() {
    return invokeCommand<ComlinkStatus>("stop_comlink");
  },
  fetchGuildByAllyCode(allyCode: string) {
    return invokeCommand<{ summary: GuildSummary }>("fetch_guild_by_allycode", {
      request: { allyCode },
    });
  },
  scanRoster(allyCode: string) {
    return invokeCommand<{
      allyCode: string;
      roster: SimplifiedRosterUnit[];
      units: number;
      skipped: number;
      powerReady: boolean;
      powerError: string;
    }>("scan_roster", {
      request: { allyCode },
    });
  },
  scanGuildRosters(members: Array<{ key: string; displayName?: string }>) {
    return invokeCommand<BulkRosterScanResponse>("scan_guild_rosters", {
      request: { members },
    });
  },
  loadOpsDefinitions() {
    return invokeCommand<OpsDefinitionsResponse>("load_ops_definitions");
  },
  analyzePlatoons() {
    return invokeCommand<PlatoonAnalysisResponse>("analyze_platoons");
  },
  getGuideTbOmicrons() {
    return invokeCommand<GuideTbOmicronResponse>("get_guide_tb_omicrons");
  },
  getGuideUnitCatalog() {
    return invokeCommand<GuideUnitCatalogResponse>("get_guide_unit_catalog");
  },
  getPlannerReference() {
    return invokeCommand<PlannerReferenceResponse>("get_planner_reference");
  },
  writeExportBundle(
    folderName: string,
    openFileName: string,
    files: ExportBundleFile[],
  ) {
    return invokeCommand<WriteExportBundleResponse>("write_export_bundle", {
      request: { folderName, openFileName, files },
    });
  },
  openExportPreview(
    title: string,
    initialDocumentId: string,
    documents: ExportPreviewDocument[],
  ) {
    return invokeCommand<OpenExportPreviewResponse>("open_export_preview", {
      request: { title, initialDocumentId, documents },
    });
  },
  getExportPreview(token: string) {
    return invokeCommand<ExportPreviewResponse>("get_export_preview", {
      request: { token },
    });
  },
  releaseExportPreview(token: string) {
    return invokeCommand<{ released: boolean }>("release_export_preview", {
      request: { token },
    });
  },
  buildPlannerProjection(settings: PlannerSettings) {
    return invokeCommand<PlannerProjectionResponse>("build_planner_projection", {
      request: { settings },
    });
  },
  runPlannerOptimization(settings: PlannerSettings, algorithm: string) {
    return invokeCommand<PlannerOptimizationResponse>(
      "run_planner_optimization",
      {
        request: { settings, algorithm },
      },
    );
  },
  loadAppState() {
    return invokeCommand<{ state: PersistedAppState }>("load_app_state");
  },
  saveAppState(snapshot: PersistedAppState) {
    return invokeCommand<{ saved: boolean }>("save_app_state", {
      request: { snapshot },
    });
  },
  importSessionState(guildRosters: GuildRosters) {
    return invokeCommand<{ imported: boolean; members: number; units: number }>(
      "import_session_state",
      {
        request: { guildRosters },
      },
    );
  },
  resetScanSession() {
    return invokeCommand<{ reset: boolean }>("reset_scan_session");
  },
};
