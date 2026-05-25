import type {
  ExportBundleFile,
  GuildRosters,
  GuildSummary,
  OpsDefinitions,
  PersistedPlannerState,
  PlannerDayResult,
  PlannerOpsAssignmentEntry,
  PlannerOptimizationResponse,
  PlannerPlanetDefinition,
  PlannerProjectionResponse,
  PlannerSettings,
  PlatoonAnalysisMap,
} from "../../lib/plannerApi";
import { formatMillions, formatNumber } from "./runtimeViewModels";

export type PlanExportMode = "all" | "separate";
export type PlanExportDetailMode = "detailed" | "condensed";

export type PlannerSnapshotPayload = PersistedPlannerState & {
  version: number;
  savedAt: string;
  guildSummary: GuildSummary | null;
  guildRosters: GuildRosters;
  opsDefinitions: OpsDefinitions | null;
  opsAnalysis: PlatoonAnalysisMap | null;
  plannerProjection: PlannerProjectionResponse | null;
  plannerResult: PlannerOptimizationResponse | null;
};

type ExportBuilderParams = {
  plannerResult: PlannerOptimizationResponse;
  guildSummary: GuildSummary | null;
  guildRosters: GuildRosters;
  plannerReference: { planets: PlannerPlanetDefinition[] } | null;
  opsDefinitions: OpsDefinitions | null;
  opsAnalysis: PlatoonAnalysisMap | null;
  plannerSettings: PlannerSettings;
  mode: PlanExportMode;
  detailMode: PlanExportDetailMode;
};

type SnapshotBuilderParams = PersistedPlannerState & {
  guildSummary: GuildSummary | null;
  guildRosters: GuildRosters;
  opsDefinitions: OpsDefinitions | null;
  opsAnalysis: PlatoonAnalysisMap | null;
  plannerProjection: PlannerProjectionResponse | null;
  plannerResult: PlannerOptimizationResponse | null;
};

type DocumentParams = {
  plannerResult: PlannerOptimizationResponse;
  guildSummary: GuildSummary | null;
  guildRosters: GuildRosters;
  planetMap: Map<string, PlannerPlanetDefinition>;
  planetOrder: Map<string, number>;
  opsDefinitions: OpsDefinitions | null;
  opsAnalysis: PlatoonAnalysisMap | null;
  plannerSettings: PlannerSettings;
  dayNumbers?: number[];
  docTitle: string;
  autoPrint?: boolean;
  detailMode: PlanExportDetailMode;
};

type RequirementLike = {
  defId: string;
  name: string;
  minRarity: number;
  minRelic: number;
};

type SlotSnapshot = {
  requirement: RequirementLike;
  reqIdx: number;
  assignmentToDay: PlannerOpsAssignmentEntry | null;
  assignmentToday: PlannerOpsAssignmentEntry | null;
  availableCount: number;
};

type PlatoonSnapshot = {
  platoonIdx: number;
  totalFilled: number;
  totalSlots: number;
  completedDay: number;
  completedByDay: boolean;
  assignedTodayCount: number;
  daysRemaining: number;
  impossible: boolean;
  slotStates: SlotSnapshot[];
  reqStates: Array<{
    requirement: RequirementLike;
    reqIdx: number;
    slotIndexes: number[];
    filledToDay: PlannerOpsAssignmentEntry[];
    filledToday: PlannerOpsAssignmentEntry[];
    availableCount: number;
    remaining: number;
  }>;
};

type ShortfallEntry = {
  requirement: RequirementLike;
  availableCount: number;
  needed: number;
  missing: number;
};

type ExportBundle = {
  folderName: string;
  openFileName: string;
  files: ExportBundleFile[];
};

export type ExportPreviewBundle = {
  title: string;
  initialDocumentId: string;
  documents: Array<{
    id: string;
    title: string;
    html: string;
  }>;
};

const CHAIN_NAMES = {
  ds: "Dark Side",
  mx: "Mixed",
  ls: "Light Side",
} as const;

function escapeHtml(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function normalizeDefId(value: string) {
  return value.trim().toUpperCase().split(":")[0] ?? "";
}

function formatExportPercent(value: number) {
  if (!Number.isFinite(value)) return "n/a";
  const rounded = Math.round(value * 10) / 10;
  const whole = Math.round(rounded);
  return `${Math.abs(rounded - whole) < 0.05 ? whole : rounded.toFixed(1)}%`;
}

function averageNumber(values: number[]) {
  const usable = values.filter((value) => Number.isFinite(value));
  if (!usable.length) return 0;
  return usable.reduce((sum, value) => sum + value, 0) / usable.length;
}

function safeStamp(value: Date) {
  return value.toISOString().replace(/:/g, "-").replace(/\..+$/, "");
}

function titleizePlanetId(value: string) {
  return value
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
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

function completionCountLimit(plannerSettings: PlannerSettings) {
  return Math.min(50, Math.max(1, Math.round(plannerSettings.guildMembers || 50)));
}

function completionCountToPercent(plannerSettings: PlannerSettings, value: number) {
  const memberCount = completionCountLimit(plannerSettings);
  const count = Math.min(memberCount, Math.max(0, value));
  return Math.max(0, Math.min(100, (count / memberCount) * 100));
}

function clampPercent(value: number) {
  return Math.max(0, Math.min(100, value));
}

function effectivePlanetRate(
  plannerSettings: PlannerSettings,
  planetId: string,
  missionType: "cm" | "fleet",
) {
  const state = plannerSettings.planetState[planetId];
  const depth = plannerChainDepth(planetId);
  if (plannerSettings.cmMode === "count") {
    const defaultCount =
      missionType === "cm"
        ? plannerSettings.cmBase - plannerSettings.cmFalloff * depth
        : plannerSettings.fleetBase - plannerSettings.fleetFalloff * depth;
    const overrideCount =
      missionType === "cm" ? state?.cmCountOverride : state?.fleetCountOverride;
    return completionCountToPercent(
      plannerSettings,
      typeof overrideCount === "number" ? overrideCount : defaultCount,
    );
  }

  if (missionType === "cm") {
    if (typeof state?.cmRateOverride === "number") {
      return clampPercent(state.cmRateOverride);
    }
    if (typeof state?.cmCountOverride === "number") {
      return completionCountToPercent(plannerSettings, state.cmCountOverride);
    }
    return clampPercent(plannerSettings.cmBase - plannerSettings.cmFalloff * depth);
  }
  if (typeof state?.fleetRateOverride === "number") {
    return clampPercent(state.fleetRateOverride);
  }
  if (typeof state?.fleetCountOverride === "number") {
    return completionCountToPercent(plannerSettings, state.fleetCountOverride);
  }
  return clampPercent(plannerSettings.fleetBase - plannerSettings.fleetFalloff * depth);
}

function getUndeployedGpForDay(plannerSettings: PlannerSettings, dayNumber: number) {
  const value = plannerSettings.dailyUndep[Math.max(0, dayNumber - 1)] ?? 0;
  if (plannerSettings.undepMode === "flat") {
    return Math.max(0, value);
  }
  return Math.max(0, plannerSettings.guildGp * (value / 100));
}

function getUndeployedPctForDay(plannerSettings: PlannerSettings, dayNumber: number) {
  if (plannerSettings.guildGp <= 0) return 0;
  return Math.max(
    0,
    Math.min(100, (getUndeployedGpForDay(plannerSettings, dayNumber) / plannerSettings.guildGp) * 100),
  );
}

function buildPlanetMaps(plannerReference: { planets: PlannerPlanetDefinition[] } | null) {
  const planets = plannerReference?.planets ?? [];
  return {
    planetMap: new Map(planets.map((planet) => [planet.id, planet])),
    planetOrder: new Map(planets.map((planet, index) => [planet.id, index])),
  };
}

function uniqueBonusPlanetCount(plannerResult: PlannerOptimizationResponse) {
  return new Set(
    plannerResult.dayPlan.flatMap((dayPlan) => dayPlan.bonusPlanets.map((planet) => planet.planetId)),
  ).size;
}

export function plannerSummaryForExport(
  plannerResult: PlannerOptimizationResponse,
  guildRosters: GuildRosters,
) {
  return {
    totalStars: plannerResult.totalStars,
    maxPossibleStars: plannerResult.summary.maxPossibleStars,
    bonusCount: uniqueBonusPlanetCount(plannerResult),
    opsCompleted: plannerResult.opsSummary.totalCompleted,
    opsTotal: plannerResult.opsSummary.totalPlatoons,
    opsPoints: plannerResult.opsSummary.totalPoints,
    scannedMembers: Object.keys(guildRosters).filter((key) => guildRosters[key]?.length).length,
  };
}

function getActivePlanetIdsForPlanDay(
  dayPlan: PlannerDayResult,
  opsDefinitions: OpsDefinitions | null,
  planetOrder: Map<string, number>,
) {
  const ids = [
    dayPlan.chains.ds?.planetId,
    dayPlan.chains.mx?.planetId,
    dayPlan.chains.ls?.planetId,
    ...dayPlan.bonusPlanets.map((planet) => planet.planetId),
  ]
    .filter((value): value is string => typeof value === "string" && value.length > 0)
    .filter((value) => Boolean(opsDefinitions?.[value]));
  return Array.from(new Set(ids)).sort(
    (left, right) => (planetOrder.get(left) ?? 999) - (planetOrder.get(right) ?? 999),
  );
}

function countPlanetActiveDaysRemaining(
  plannerResult: PlannerOptimizationResponse,
  planetId: string,
  fromDay: number,
  opsDefinitions: OpsDefinitions | null,
  planetOrder: Map<string, number>,
) {
  return plannerResult.dayPlan.filter(
    (dayPlan) =>
      dayPlan.day >= fromDay &&
      getActivePlanetIdsForPlanDay(dayPlan, opsDefinitions, planetOrder).includes(planetId),
  ).length;
}

function getOperationsDayBundle(
  plannerResult: PlannerOptimizationResponse,
  dayNumber: number,
  opsDefinitions: OpsDefinitions | null,
  planetOrder: Map<string, number>,
) {
  const dayPlan = plannerResult.dayPlan.find((entry) => entry.day === dayNumber) ?? null;
  const opsDay = plannerResult.opsSummary.days.find((entry) => entry.day === dayNumber) ?? null;
  const activePlanetIds = dayPlan
    ? getActivePlanetIdsForPlanDay(dayPlan, opsDefinitions, planetOrder)
    : [];
  return { dayPlan, opsDay, activePlanetIds };
}

function getPlanetLabelForSelectedDay(dayPlan: PlannerDayResult, planetId: string) {
  const chainEntry = Object.values(dayPlan.chains).find((entry) => entry?.planetId === planetId);
  if (chainEntry) {
    if (chainEntry.status === "preload") return "Preload focus";
    if (chainEntry.status === "commit") {
      return chainEntry.stars >= 3 ? "3-star push" : chainEntry.stars === 2 ? "2-star push" : "1-star push";
    }
    if (chainEntry.status === "building") return "Still building";
  }
  if (dayPlan.bonusPlanets.some((entry) => entry.planetId === planetId)) {
    return "Bonus planet";
  }
  return "Active planet";
}

function getDayExportEstimateSummary(
  dayPlan: PlannerDayResult,
  plannerSettings: PlannerSettings,
  planetMap: Map<string, PlannerPlanetDefinition>,
  opsDefinitions: OpsDefinitions | null,
  planetOrder: Map<string, number>,
) {
  const activePlanetIds = getActivePlanetIdsForPlanDay(dayPlan, opsDefinitions, planetOrder);
  const cmAvgPct = averageNumber(
    activePlanetIds.map((planetId) => effectivePlanetRate(plannerSettings, planetId, "cm")),
  );
  const fleetRelevant = activePlanetIds.filter((planetId) =>
    planetMap
      .get(planetId)
      ?.missions.some((mission) => mission.missionType === "fleet"),
  );
  const fleetIds = fleetRelevant.length ? fleetRelevant : activePlanetIds;
  const fleetAvgPct = averageNumber(
    fleetIds.map((planetId) => effectivePlanetRate(plannerSettings, planetId, "fleet")),
  );
  const undeployedGp = getUndeployedGpForDay(plannerSettings, dayPlan.day);
  const gpParticipationPct = 100 - getUndeployedPctForDay(plannerSettings, dayPlan.day);
  return {
    cmAvgPct,
    fleetAvgPct,
    undeployedGp,
    gpParticipationPct,
  };
}

function buildDayExportEstimateLine(
  dayPlan: PlannerDayResult,
  plannerSettings: PlannerSettings,
  planetMap: Map<string, PlannerPlanetDefinition>,
  opsDefinitions: OpsDefinitions | null,
  planetOrder: Map<string, number>,
) {
  const summary = getDayExportEstimateSummary(
    dayPlan,
    plannerSettings,
    planetMap,
    opsDefinitions,
    planetOrder,
  );
  return `Estimated GP participation: ${formatExportPercent(summary.gpParticipationPct)} | Avg CM ${formatExportPercent(summary.cmAvgPct)} | Avg Fleet ${formatExportPercent(summary.fleetAvgPct)} | Undeployed GP ${formatMillions(summary.undeployedGp)}`;
}

function buildProjectedPointsBreakdownHtml(
  missionPoints: number,
  opsPoints: number,
  gpDeployed: number,
) {
  return `<div class="day-action">Mission ${escapeHtml(formatMillions(missionPoints))} | Ops ${escapeHtml(formatMillions(opsPoints))} | GP ${escapeHtml(formatMillions(gpDeployed))}</div>`;
}

function buildMainDayChainCardHtml(
  chainKey: keyof typeof CHAIN_NAMES,
  chainEntry: PlannerDayResult["chains"][string] | undefined,
  planetMap: Map<string, PlannerPlanetDefinition>,
) {
  if (!chainEntry || chainEntry.status === "complete") {
    return `<div class="day-chain ${chainKey}"><div class="day-chain-title">${escapeHtml(CHAIN_NAMES[chainKey])}</div><div class="day-locked">Complete</div></div>`;
  }

  const planet = chainEntry.planetId ? planetMap.get(chainEntry.planetId) : null;
  const planetName = chainEntry.planetName ?? planet?.name ?? chainEntry.planetId ?? "Unknown Planet";
  let inner = "";

  if (chainEntry.status === "preload") {
    const tomorrowEstimate = formatMillions(chainEntry.tomorrowEst || chainEntry.banked);
    const capNote = chainEntry.threshold1star
      ? `<div class="day-advance" style="color:#73829d">Capped at ${escapeHtml(formatMillions(chainEntry.threshold1star - 1))} (1-star threshold: ${escapeHtml(formatMillions(chainEntry.threshold1star))})</div>`
      : "";
    inner = `
      <div class="day-stars" style="color:#c39bd3">Preloading</div>
      <div class="day-action">Projected total: ${escapeHtml(formatMillions(chainEntry.banked))} pts</div>
      ${buildProjectedPointsBreakdownHtml(chainEntry.missionPts, chainEntry.opsPts, chainEntry.gpDeployed)}
      <div class="day-advance">Banking below 1-star for tomorrow | Tomorrow est. base: ${escapeHtml(tomorrowEstimate)}</div>
      ${capNote}
    `;
  } else if (chainEntry.status === "commit") {
    const advanceNote =
      chainEntry.stars === 3
        ? `<div class="day-advance" style="color:#3ea87a">3-star! Next planet unlocks tomorrow</div>`
        : `<div class="day-advance">${escapeHtml(formatNumber(chainEntry.pctOf3))}% of 3-star | next planet unlocks tomorrow</div>`;
    inner = `
      <div class="day-stars">${escapeHtml(String(chainEntry.stars))} stars</div>
      <div class="day-action">Projected total: ${escapeHtml(formatMillions(chainEntry.pts))} pts</div>
      ${buildProjectedPointsBreakdownHtml(chainEntry.missionPts, chainEntry.opsPts, chainEntry.gpDeployed)}
      ${advanceNote}
    `;
  } else {
    const threshold = planet?.stars?.[0] ?? chainEntry.threshold1star ?? 0;
    inner = `
      <div class="day-stars" style="color:#cc5b5b">Below 1-star</div>
      <div class="day-action">Projected total: ${escapeHtml(formatMillions(chainEntry.pts))} pts</div>
      ${buildProjectedPointsBreakdownHtml(chainEntry.missionPts, chainEntry.opsPts, chainEntry.gpDeployed)}
      <div class="day-advance">${escapeHtml(formatMillions(chainEntry.pts))} / ${escapeHtml(formatMillions(threshold))} for 1-star - needs more GP or preloading</div>
    `;
  }

  return `
    <div class="day-chain ${chainKey}">
      <div class="day-chain-title">${escapeHtml(CHAIN_NAMES[chainKey])}</div>
      <div class="day-planet-name">${escapeHtml(planetName)}</div>
      ${inner}
    </div>
  `;
}

function buildBonusDayChainCardHtml(
  bonusEntry: PlannerDayResult["bonusPlanets"][number],
  planetMap: Map<string, PlannerPlanetDefinition>,
) {
  const planet = planetMap.get(bonusEntry.planetId);
  const planetName = bonusEntry.planetName ?? planet?.name ?? bonusEntry.planetId;
  const unlockSource =
    (planet?.unlockedBy ? planetMap.get(planet.unlockedBy)?.name : null) ??
    planet?.unlockedBy ??
    "its unlock planet";
  const unlockNote = bonusEntry.unlockedOnDay
    ? `<div class="day-advance">Unlocked after ${escapeHtml(unlockSource)} hit 1-star on Day ${escapeHtml(String(bonusEntry.unlockedOnDay))}</div>`
    : "";

  let inner = "";
  if ((bonusEntry.stars || 0) >= 1) {
    inner = `
      <div class="day-stars">${escapeHtml(String(bonusEntry.stars))} stars</div>
      <div class="day-action">Projected total: ${escapeHtml(formatMillions(bonusEntry.pts))} pts</div>
      ${buildProjectedPointsBreakdownHtml(bonusEntry.missionPts, bonusEntry.opsPts, bonusEntry.gpDeployed)}
      <div class="day-advance" style="color:#c39bd3">Locks tomorrow after earning stars</div>
      ${unlockNote}
    `;
  } else {
    const threshold = planet?.stars?.[0] ?? 0;
    inner = `
      <div class="day-stars" style="color:#c39bd3">Active</div>
      <div class="day-action">Projected total: ${escapeHtml(formatMillions(bonusEntry.pts))} pts</div>
      ${buildProjectedPointsBreakdownHtml(bonusEntry.missionPts, bonusEntry.opsPts, bonusEntry.gpDeployed)}
      <div class="day-advance">Carryover into tomorrow: ${escapeHtml(formatMillions(bonusEntry.carryOver || 0))}</div>
      ${unlockNote}
      <div class="day-advance">${escapeHtml(formatMillions(bonusEntry.pts))} / ${escapeHtml(formatMillions(threshold))} for 1-star</div>
    `;
  }

  return `
    <div class="day-chain bonus">
      <div class="day-chain-title">Bonus Planet</div>
      <div class="day-planet-name">${escapeHtml(planetName)}</div>
      ${inner}
    </div>
  `;
}

function buildDayPlanCardsHtml(
  dayPlan: PlannerDayResult,
  planetMap: Map<string, PlannerPlanetDefinition>,
) {
  const cards = (Object.keys(CHAIN_NAMES) as Array<keyof typeof CHAIN_NAMES>).map((chainKey) =>
    buildMainDayChainCardHtml(chainKey, dayPlan.chains[chainKey], planetMap),
  );
  dayPlan.bonusPlanets.forEach((bonusPlanet) => {
    cards.push(buildBonusDayChainCardHtml(bonusPlanet, planetMap));
  });
  return cards.join("");
}

function buildExportDayOverviewHtml(
  dayPlans: PlannerDayResult[],
  planetMap: Map<string, PlannerPlanetDefinition>,
  plannerSettings: PlannerSettings,
  opsDefinitions: OpsDefinitions | null,
  planetOrder: Map<string, number>,
) {
  const cards = dayPlans
    .map((dayPlan) => {
      const activePlanetIds = getActivePlanetIdsForPlanDay(dayPlan, opsDefinitions, planetOrder);
      const targetChips = activePlanetIds
        .map((planetId) => {
          const planetName = planetMap.get(planetId)?.name ?? titleizePlanetId(planetId);
          return `<span class="export-target-chip">${escapeHtml(planetName)} | ${escapeHtml(getPlanetLabelForSelectedDay(dayPlan, planetId))}</span>`;
        })
        .join("");
      return `
        <div class="export-overview-card">
          <div class="export-overview-day">Day ${escapeHtml(String(dayPlan.day))}</div>
          <div class="export-overview-stars">${escapeHtml(String(dayPlan.starsDay))} stars planned</div>
          <div class="export-overview-label">Target planets</div>
          <div class="export-target-chip-row">${targetChips || '<span class="export-target-chip muted">No active targets</span>'}</div>
          <div class="export-overview-estimate">${escapeHtml(buildDayExportEstimateLine(dayPlan, plannerSettings, planetMap, opsDefinitions, planetOrder))}</div>
        </div>
      `;
    })
    .join("");

  if (!cards) return "";
  return `
    <section class="export-overview-section">
      <div class="export-overview-title">Day-by-Day Overview</div>
      <div class="export-overview-grid">${cards}</div>
    </section>
  `;
}

function buildGuildMemberNameMap(guildSummary: GuildSummary | null) {
  const out = new Map<string, string>();
  guildSummary?.members.forEach((member) => {
    if (member.allyCode) out.set(member.allyCode, member.displayName);
    if (member.playerId) out.set(member.playerId, member.displayName);
  });
  return out;
}

function inferRequirementCombatType(requirement: RequirementLike) {
  return requirement.minRelic > 0 ? 1 : 2;
}

function operationsRequirementText(requirement: RequirementLike) {
  return inferRequirementCombatType(requirement) === 2
    ? `${requirement.minRarity}* ship`
    : `${requirement.minRarity}* | R${requirement.minRelic}+`;
}

function matchesRequirement(
  requirement: RequirementLike,
  compareTo: RequirementLike,
) {
  return (
    normalizeDefId(requirement.defId) === normalizeDefId(compareTo.defId) &&
    Math.round(requirement.minRarity || 0) === Math.round(compareTo.minRarity || 0) &&
    Math.round(requirement.minRelic || 0) === Math.round(compareTo.minRelic || 0)
  );
}

function requirementAvailabilityFromRosters(
  guildRosters: GuildRosters,
  requirement: RequirementLike,
) {
  const requirementDefId = normalizeDefId(requirement.defId);
  return Object.values(guildRosters).reduce((count, roster) => {
    const hasUnit = (roster ?? []).some((unit) => {
      if (normalizeDefId(unit.defId) !== requirementDefId) return false;
      if ((unit.rarity ?? 0) < requirement.minRarity) return false;
      if (inferRequirementCombatType(requirement) === 1) {
        return (unit.relic ?? 0) >= requirement.minRelic;
      }
      return true;
    });
    return count + (hasUnit ? 1 : 0);
  }, 0);
}

function getRequirementAvailabilityCount(
  planetId: string,
  platoonIdx: number,
  requirement: RequirementLike,
  opsAnalysis: PlatoonAnalysisMap | null,
  guildRosters: GuildRosters,
) {
  const baseline = opsAnalysis?.[planetId]?.[platoonIdx]?.slots ?? [];
  const match = baseline.find((slot) =>
    matchesRequirement(requirement, {
      defId: slot.defId,
      name: slot.name,
      minRarity: slot.minRarity,
      minRelic: slot.minRelic,
    }),
  );
  if (match && Number.isFinite(match.have)) {
    return Math.max(0, Math.round(match.have));
  }
  return requirementAvailabilityFromRosters(guildRosters, requirement);
}

function groupPlatoonRequirements(slotDefs: RequirementLike[]) {
  const groups: Array<{
    requirement: RequirementLike;
    slotIndexes: number[];
  }> = [];
  const groupIndexByKey = new Map<string, number>();

  slotDefs.forEach((slot, reqIdx) => {
    const key = [
      normalizeDefId(slot.defId),
      Math.round(slot.minRarity || 0),
      Math.round(slot.minRelic || 0),
    ].join("|");
    const existingIndex = groupIndexByKey.get(key);
    if (typeof existingIndex === "number") {
      groups[existingIndex]?.slotIndexes.push(reqIdx);
      return;
    }
    groupIndexByKey.set(key, groups.length);
    groups.push({
      requirement: {
        defId: slot.defId,
        name: slot.name,
        minRarity: slot.minRarity,
        minRelic: slot.minRelic,
      },
      slotIndexes: [reqIdx],
    });
  });

  return groups;
}

function numberOperationsSlotNames(slotNames: string[]) {
  const counts = new Map<string, number>();
  slotNames.forEach((name) => {
    counts.set(name, (counts.get(name) ?? 0) + 1);
  });

  const seen = new Map<string, number>();
  return slotNames.map((name) => {
    const total = counts.get(name) ?? 0;
    const next = (seen.get(name) ?? 0) + 1;
    seen.set(name, next);
    return total > 1 ? `${name} ${next}` : name;
  });
}

function getOpsRequirementShortfallKey(requirement: RequirementLike) {
  return [
    normalizeDefId(requirement.defId),
    Math.round(requirement.minRarity || 0),
    Math.round(requirement.minRelic || 0),
  ].join("|");
}

function summarizeOpsRequirementShortfalls(entries: Array<{
  requirement: RequirementLike;
  availableCount: number;
  needed: number;
}>) {
  const grouped = new Map<string, ShortfallEntry>();

  entries.forEach((entry) => {
    if (!entry.requirement || entry.needed <= 0) return;
    const key = getOpsRequirementShortfallKey(entry.requirement);
    const existing =
      grouped.get(key) ??
      ({
        requirement: entry.requirement,
        availableCount: 0,
        needed: 0,
        missing: 0,
      } satisfies ShortfallEntry);
    existing.needed += entry.needed;
    existing.availableCount = Math.max(existing.availableCount, entry.availableCount);
    grouped.set(key, existing);
  });

  return Array.from(grouped.values())
    .map((entry) => ({
      ...entry,
      missing: Math.max(0, entry.needed - entry.availableCount),
    }))
    .filter((entry) => entry.missing > 0)
    .sort(
      (left, right) =>
        right.missing - left.missing ||
        left.requirement.name.localeCompare(right.requirement.name),
    );
}

function formatOpsShortfallText(entry: ShortfallEntry) {
  return `${entry.requirement.name} x${entry.missing} (${operationsRequirementText(entry.requirement)})`;
}

function buildOperationsPlatoonSnapshot(
  plannerResult: PlannerOptimizationResponse,
  planetId: string,
  platoonIdx: number,
  dayNumber: number,
  opsDefinitions: OpsDefinitions | null,
  opsAnalysis: PlatoonAnalysisMap | null,
  guildRosters: GuildRosters,
  planetOrder: Map<string, number>,
) {
  const platoonDefs = opsDefinitions?.[planetId]?.[platoonIdx] ?? [];
  if (!platoonDefs.length) return null;

  const assignmentByReqIdx = new Map<number, PlannerOpsAssignmentEntry>();
  const assignmentTodayByReqIdx = new Map<number, PlannerOpsAssignmentEntry>();
  let completedDay = 0;

  plannerResult.dayPlan
    .filter((dayPlan) => dayPlan.day <= dayNumber)
    .forEach((dayPlan) => {
      const planetDay = dayPlan.opsPlanets[planetId];
      if (!planetDay) return;
      planetDay.assignments
        .filter((group) => group.platoonIdx === platoonIdx)
        .forEach((group) => {
          group.entries.forEach((entry) => {
            assignmentByReqIdx.set(entry.reqIdx, entry);
            if (dayPlan.day === dayNumber) {
              assignmentTodayByReqIdx.set(entry.reqIdx, entry);
            }
          });
          if (group.completed && !completedDay) {
            completedDay = dayPlan.day;
          }
        });
    });

  const slotStates = platoonDefs.map((slot, reqIdx) => {
    const requirement = {
      defId: slot.defId,
      name: slot.name,
      minRarity: slot.minRarity,
      minRelic: slot.minRelic,
    };
    return {
      requirement,
      reqIdx,
      assignmentToDay: assignmentByReqIdx.get(reqIdx) ?? null,
      assignmentToday: assignmentTodayByReqIdx.get(reqIdx) ?? null,
      availableCount: getRequirementAvailabilityCount(
        planetId,
        platoonIdx,
        requirement,
        opsAnalysis,
        guildRosters,
      ),
    } satisfies SlotSnapshot;
  });

  const reqStates = groupPlatoonRequirements(platoonDefs).map((group, index) => {
    const filledToDay = group.slotIndexes
      .map((slotIndex) => assignmentByReqIdx.get(slotIndex))
      .filter((entry): entry is PlannerOpsAssignmentEntry => Boolean(entry));
    const filledToday = group.slotIndexes
      .map((slotIndex) => assignmentTodayByReqIdx.get(slotIndex))
      .filter((entry): entry is PlannerOpsAssignmentEntry => Boolean(entry));
    const availableCount = getRequirementAvailabilityCount(
      planetId,
      platoonIdx,
      group.requirement,
      opsAnalysis,
      guildRosters,
    );
    return {
      requirement: group.requirement,
      reqIdx: index,
      slotIndexes: group.slotIndexes,
      filledToDay,
      filledToday,
      availableCount,
      remaining: Math.max(0, group.slotIndexes.length - filledToDay.length),
    };
  });

  const totalFilled = slotStates.reduce(
    (sum, slot) => sum + (slot.assignmentToDay ? 1 : 0),
    0,
  );
  const totalSlots = platoonDefs.length;
  const daysRemaining = countPlanetActiveDaysRemaining(
    plannerResult,
    planetId,
    dayNumber,
    opsDefinitions,
    planetOrder,
  );
  const completedByDay = completedDay > 0 && completedDay <= dayNumber;
  const assignedTodayCount = slotStates.reduce(
    (sum, slot) => sum + (slot.assignmentToday ? 1 : 0),
    0,
  );
  const impossible =
    !completedByDay &&
    reqStates.some(
      (state) =>
        state.remaining > 0 &&
        state.availableCount * Math.max(1, daysRemaining) < state.remaining,
    );

  return {
    platoonIdx,
    totalFilled,
    totalSlots,
    completedDay,
    completedByDay,
    assignedTodayCount,
    daysRemaining,
    impossible,
    slotStates,
    reqStates,
  } satisfies PlatoonSnapshot;
}

function getOperationsPlanetShortfallSummary(
  plannerResult: PlannerOptimizationResponse,
  planetId: string,
  dayNumber: number,
  opsDefinitions: OpsDefinitions | null,
  opsAnalysis: PlatoonAnalysisMap | null,
  guildRosters: GuildRosters,
  planetOrder: Map<string, number>,
) {
  const planetPlatoons = opsDefinitions?.[planetId] ?? [];
  const snapshots = planetPlatoons
    .map((_, platoonIdx) =>
      buildOperationsPlatoonSnapshot(
        plannerResult,
        planetId,
        platoonIdx,
        dayNumber,
        opsDefinitions,
        opsAnalysis,
        guildRosters,
        planetOrder,
      ),
    )
    .filter((entry): entry is PlatoonSnapshot => Boolean(entry));

  const remainingEntries = snapshots
    .filter((snapshot) => !snapshot.completedByDay)
    .flatMap((snapshot) =>
      snapshot.reqStates.map((entry) => ({
        requirement: entry.requirement,
        availableCount: entry.availableCount,
        needed: entry.remaining,
      })),
    );

  const planetShortfalls = summarizeOpsRequirementShortfalls(remainingEntries);
  const impossiblePlatoons = snapshots
    .filter((snapshot) => snapshot.impossible)
    .map((snapshot) => ({
      platoonIdx: snapshot.platoonIdx,
      totalFilled: snapshot.totalFilled,
      totalSlots: snapshot.totalSlots,
      shortfalls: summarizeOpsRequirementShortfalls(
        snapshot.reqStates.map((entry) => ({
          requirement: entry.requirement,
          availableCount: entry.availableCount,
          needed: entry.remaining,
        })),
      ),
    }))
    .filter((entry) => entry.shortfalls.length);

  return {
    snapshots,
    planetShortfalls,
    impossiblePlatoons,
  };
}

function buildOpsMissingSummaryHtml(
  plannerResult: PlannerOptimizationResponse,
  planetId: string,
  dayNumber: number,
  opsDefinitions: OpsDefinitions | null,
  opsAnalysis: PlatoonAnalysisMap | null,
  guildRosters: GuildRosters,
  planetOrder: Map<string, number>,
) {
  const summary = getOperationsPlanetShortfallSummary(
    plannerResult,
    planetId,
    dayNumber,
    opsDefinitions,
    opsAnalysis,
    guildRosters,
    planetOrder,
  );
  if (!summary.planetShortfalls.length && !summary.impossiblePlatoons.length) {
    return "";
  }

  const planetLine = summary.planetShortfalls.length
    ? summary.planetShortfalls.map((entry) => escapeHtml(formatOpsShortfallText(entry))).join(" · ")
    : "None";
  const impossibleLines = summary.impossiblePlatoons.length
    ? summary.impossiblePlatoons
        .map(
          (entry) => `
            <div class="export-missing-line">
              <strong>Platoon ${escapeHtml(String(entry.platoonIdx + 1))}</strong>: ${entry.shortfalls
                .map((shortfall) => escapeHtml(formatOpsShortfallText(shortfall)))
                .join(" · ")}
            </div>
          `,
        )
        .join("")
    : '<div class="export-missing-line">No impossible platoons on this planet by this day.</div>';

  return `
    <div class="export-missing-card">
      <div class="export-missing-title">Missing units summary</div>
      <div class="export-missing-text">To complete all remaining platoons on this planet in one day, the guild is still short: ${planetLine}</div>
      <div class="export-missing-subtitle">Impossible platoon blockers</div>
      ${impossibleLines}
    </div>
  `;
}

function buildOperationsPlanetExportHtml(
  plannerResult: PlannerOptimizationResponse,
  dayNumber: number,
  planetId: string,
  detailMode: PlanExportDetailMode,
  planetMap: Map<string, PlannerPlanetDefinition>,
  planetOrder: Map<string, number>,
  opsDefinitions: OpsDefinitions | null,
  opsAnalysis: PlatoonAnalysisMap | null,
  guildSummary: GuildSummary | null,
  guildRosters: GuildRosters,
) {
  const planetPlatoons = opsDefinitions?.[planetId];
  if (!planetPlatoons?.length) return "";

  const { dayPlan, opsDay } = getOperationsDayBundle(
    plannerResult,
    dayNumber,
    opsDefinitions,
    planetOrder,
  );
  if (!dayPlan) return "";

  const planetMeta = planetMap.get(planetId);
  const planetName = planetMeta?.name ?? titleizePlanetId(planetId);
  const planetToday = opsDay?.planets[planetId] ?? dayPlan.opsPlanets[planetId] ?? null;
  const memberNameMap = buildGuildMemberNameMap(guildSummary);
  const daysRemaining = countPlanetActiveDaysRemaining(
    plannerResult,
    planetId,
    dayNumber,
    opsDefinitions,
    planetOrder,
  );
  const summaryInfo = getOperationsPlanetShortfallSummary(
    plannerResult,
    planetId,
    dayNumber,
    opsDefinitions,
    opsAnalysis,
    guildRosters,
    planetOrder,
  );

  const detailedSnapshots = summaryInfo.snapshots.filter(
    (snapshot) =>
      !snapshot.impossible &&
      (snapshot.completedByDay || snapshot.assignedTodayCount > 0 || snapshot.totalFilled > 0),
  );

  const renderPlatoonCard = (snapshot: PlatoonSnapshot) => {
    const statusClass = snapshot.completedByDay
      ? "complete"
      : snapshot.totalFilled > 0
        ? "partial"
        : "ready";
    const statusLabel = snapshot.completedByDay
      ? snapshot.completedDay === dayNumber
        ? "Completed today"
        : `Completed on Day ${snapshot.completedDay}`
      : snapshot.assignedTodayCount > 0
        ? "Partial today"
        : snapshot.totalFilled > 0
          ? "Preloaded"
          : "Open";
    const slotDisplayNames = numberOperationsSlotNames(
      snapshot.slotStates.map((slot, slotIndex) => slot.requirement.name || `Slot ${slotIndex + 1}`),
    );
    const slotHtml = snapshot.slotStates
      .map((slot, slotIndex) => {
        const assignment = slot.assignmentToDay;
        const assignee = assignment
          ? `${memberNameMap.get(assignment.allyCode) ?? assignment.allyCode}${
              assignment.day === dayNumber ? " (today)" : ` (Day ${assignment.day})`
            }`
          : "Unassigned";
        return `
          <div class="export-slot-card">
            <div class="export-slot-name">${escapeHtml(slotDisplayNames[slotIndex] ?? slot.requirement.name)}</div>
            <div class="export-slot-assignee${assignment ? "" : " unassigned"}">- ${escapeHtml(assignee)}</div>
            <div class="export-slot-meta">Players available: ${escapeHtml(String(slot.availableCount))} | Requirement: ${escapeHtml(operationsRequirementText(slot.requirement))}</div>
          </div>
        `;
      })
      .join("");
    return `
      <div class="export-platoon-card ${statusClass}">
        <div class="export-platoon-head">
          <div>
            <div class="export-platoon-title">Platoon ${escapeHtml(String(snapshot.platoonIdx + 1))}</div>
            <div class="export-platoon-sub">${escapeHtml(String(snapshot.totalFilled))}/${escapeHtml(String(snapshot.totalSlots))} slots filled</div>
          </div>
          <div class="export-platoon-badge ${statusClass}">${escapeHtml(statusLabel)}</div>
        </div>
        <div class="export-slot-list">${slotHtml}</div>
      </div>
    `;
  };

  const condensedGroups = {
    complete: [] as Array<{ label: string; meta: string }>,
    preload: [] as Array<{ label: string; meta: string }>,
    ignore: [] as Array<{ label: string; meta: string }>,
  };

  summaryInfo.snapshots.forEach((snapshot) => {
    const label = `Platoon ${snapshot.platoonIdx + 1}`;
    if (snapshot.completedByDay) {
      condensedGroups.complete.push({
        label,
        meta: snapshot.completedDay === dayNumber ? "Finished today" : `Finished Day ${snapshot.completedDay}`,
      });
      return;
    }
    if (snapshot.assignedTodayCount > 0 || snapshot.totalFilled > 0) {
      condensedGroups.preload.push({
        label,
        meta: `${snapshot.totalFilled}/${snapshot.totalSlots} filled`,
      });
      return;
    }
    condensedGroups.ignore.push({
      label,
      meta: snapshot.impossible ? "Blocked" : "Hold",
    });
  });

  const condensedHtml = (["complete", "preload", "ignore"] as const)
    .map((status) => {
      const entries = condensedGroups[status];
      if (!entries.length) return "";
      const title =
        status === "complete" ? "Complete" : status === "preload" ? "Preload" : "Ignore";
      const chips = entries
        .map(
          (entry) => `
            <div class="export-status-chip ${status}">
              <div class="export-status-chip-label">${escapeHtml(entry.label)}</div>
              <div class="export-status-chip-meta">${escapeHtml(entry.meta)}</div>
            </div>
          `,
        )
        .join("");
      return `
        <div class="export-status-group ${status}">
          <div class="export-status-group-title">${title}</div>
          <div class="export-status-chip-grid">${chips}</div>
        </div>
      `;
    })
    .join("");

  const splitCards = detailedSnapshots.map(renderPlatoonCard);
  const leftColumn = splitCards.slice(0, 3).join("");
  const rightColumn = splitCards.slice(3).join("");
  const detailedHtml = splitCards.length
    ? `
      <div class="export-platoon-columns">
        <div class="export-platoon-column">${leftColumn}</div>
        <div class="export-platoon-column">${rightColumn}</div>
      </div>
    `
    : '<div class="export-empty">No platoons were completed or partially filled for this planet by this day.</div>';

  const missingSummaryHtml = buildOpsMissingSummaryHtml(
    plannerResult,
    planetId,
    dayNumber,
    opsDefinitions,
    opsAnalysis,
    guildRosters,
    planetOrder,
  );

  return `
    <section class="export-planet-section">
      <div class="export-planet-head">
        <div>
          <div class="export-planet-title">${escapeHtml(planetName)}</div>
          <div class="export-planet-sub">${escapeHtml(getPlanetLabelForSelectedDay(dayPlan, planetId))} | Zone ${escapeHtml(String(planetMeta?.zone ?? "?"))} | ${escapeHtml(String(daysRemaining))} day${daysRemaining === 1 ? "" : "s"} remaining active</div>
        </div>
        <div class="export-planet-metrics">
          <div>Today: ${planetToday ? `${planetToday.slotsFilled} slots | ${formatMillions(planetToday.pointsEarned)}` : "No new slots"}</div>
          <div>Completed today: ${planetToday?.completedToday ?? 0}</div>
        </div>
      </div>
      ${detailMode === "condensed" ? condensedHtml || '<div class="export-empty">No platoons were assigned to this planet by this day.</div>' : detailedHtml}
      ${missingSummaryHtml}
    </section>
  `;
}

function buildPlanExportDocumentHtml({
  plannerResult,
  guildSummary,
  guildRosters,
  planetMap,
  planetOrder,
  opsDefinitions,
  opsAnalysis,
  plannerSettings,
  dayNumbers,
  docTitle,
  autoPrint = false,
  detailMode,
}: DocumentParams) {
  const requestedDays = Array.isArray(dayNumbers) && dayNumbers.length ? new Set(dayNumbers) : null;
  const guildName = guildSummary?.name ?? "Current Guild";
  const generatedAt = new Date().toLocaleString();
  const filteredDays = plannerResult.dayPlan.filter(
    (dayPlan) => !requestedDays || requestedDays.has(dayPlan.day),
  );
  const overviewHtml = buildExportDayOverviewHtml(
    filteredDays,
    planetMap,
    plannerSettings,
    opsDefinitions,
    planetOrder,
  );
  const exportSummary = plannerSummaryForExport(plannerResult, guildRosters);

  const daySections = filteredDays
    .map((dayPlan) => {
      const cards = buildDayPlanCardsHtml(dayPlan, planetMap);
      const estimateLine = buildDayExportEstimateLine(
        dayPlan,
        plannerSettings,
        planetMap,
        opsDefinitions,
        planetOrder,
      );
      let notesHtml = dayPlan.notices
        .map((note) => `<div class="export-note">${escapeHtml(note)}</div>`)
        .join("");
      const opsDay = plannerResult.opsSummary.days.find((entry) => entry.day === dayPlan.day) ?? null;
      if (
        dayPlan.opsPoints ||
        Object.values(dayPlan.opsPlanets).some((planet) => planet.slotsFilled > 0)
      ) {
        const opsLines = Object.entries(dayPlan.opsPlanets)
          .filter(([, planet]) => planet.completedToday > 0 || planet.slotsFilled > 0)
          .sort((left, right) => (right[1].priority - left[1].priority) || left[0].localeCompare(right[0]))
          .map(([planetId, planet]) => {
            const planetName = planetMap.get(planetId)?.name ?? titleizePlanetId(planetId);
            return `<div class="export-note"><strong>${escapeHtml(planetName)}</strong>: ${escapeHtml(String(planet.slotsFilled))} slots${
              planet.completedToday
                ? ` | ${escapeHtml(String(planet.completedToday))} platoon${planet.completedToday === 1 ? "" : "s"} completed`
                : ""
            }</div>`;
          })
          .join("");
        notesHtml += `<div class="export-note"><strong>Operations</strong>: ${dayPlan.opsPoints ? `+${escapeHtml(formatMillions(dayPlan.opsPoints))}` : "preloading only"}</div>${opsLines}`;
      }

      const activePlanetIds = getActivePlanetIdsForPlanDay(dayPlan, opsDefinitions, planetOrder);
      const opsSections = activePlanetIds.length
        ? activePlanetIds
            .map((planetId) =>
              buildOperationsPlanetExportHtml(
                plannerResult,
                dayPlan.day,
                planetId,
                detailMode,
                planetMap,
                planetOrder,
                opsDefinitions,
                opsAnalysis,
                guildSummary,
                guildRosters,
              ),
            )
            .join("")
        : '<div class="export-empty">No active planets were planned for operations on this day.</div>';

      return `
        <section class="export-day-section">
          <div class="export-day-header">
            <div>
              <div class="export-day-title">Day ${escapeHtml(String(dayPlan.day))}</div>
              <div class="export-day-sub">Available GP: ${escapeHtml(formatMillions(dayPlan.gpAvail))} | Used GP: ${escapeHtml(formatMillions(dayPlan.gpUsed))}</div>
            </div>
            <div class="export-day-stars">${escapeHtml(String(dayPlan.starsDay))} stars</div>
          </div>
          <div class="export-estimate-band">${escapeHtml(estimateLine)}</div>
          <div class="export-subtitle">Day Plan</div>
          <div class="export-day-grid">${cards}</div>
          ${notesHtml ? `<div class="export-note-block">${notesHtml}</div>` : ""}
          <div class="export-subtitle" style="margin-top:18px">Operations</div>
          <div class="export-ops-summary">Ops points today: ${escapeHtml(formatMillions(opsDay?.pointsEarned ?? 0))} | Slots planned: ${escapeHtml(
            String(
              Object.values(opsDay?.planets ?? {}).reduce(
                (sum, planet) => sum + (planet.slotsFilled || 0),
                0,
              ),
            ),
          )} | Platoons completed today: ${escapeHtml(
            String(
              Object.values(opsDay?.planets ?? {}).reduce(
                (sum, planet) => sum + (planet.completedToday || 0),
                0,
              ),
            ),
          )} | Layout: ${detailMode === "condensed" ? "Condensed" : "Detailed"}</div>
          ${opsSections}
        </section>
      `;
    })
    .join("");

  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>${escapeHtml(docTitle)}</title>
    <style>
      @page { size: auto; margin: .45in; }
      html, body { margin: 0; padding: 0; background: #f4f6fb; color: #142033; font-family: "Segoe UI", Arial, sans-serif; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      body { padding: 18px 20px 26px; }
      .export-header { border: 1px solid #d7deed; border-radius: 14px; background: #fff; padding: 18px 20px; margin-bottom: 18px; }
      .export-title { font: 700 24px Orbitron, "Segoe UI", Arial, sans-serif; color: #cc9e22; letter-spacing: .04em; margin-bottom: 6px; }
      .export-subhead { font-size: 13px; color: #5f6f8f; line-height: 1.5; }
      .export-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 14px; }
      .export-metric { border: 1px solid #d7deed; border-radius: 12px; padding: 10px 12px; background: #fafcff; }
      .export-metric-label { font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: #6f7f9c; margin-bottom: 5px; }
      .export-metric-value { font: 700 20px Orbitron, "Segoe UI", Arial, sans-serif; color: #142033; }
      .export-overview-section { border: 1px solid #d7deed; border-radius: 14px; background: #fff; padding: 16px 18px; margin-bottom: 18px; }
      .export-overview-title { font: 700 15px Orbitron, "Segoe UI", Arial, sans-serif; letter-spacing: .08em; text-transform: uppercase; color: #51627f; margin-bottom: 12px; }
      .export-overview-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
      .export-overview-card { border: 1px solid #d7deed; border-radius: 14px; background: #fafcff; padding: 14px; }
      .export-overview-day { font: 700 18px Orbitron, "Segoe UI", Arial, sans-serif; color: #cc9e22; margin-bottom: 4px; }
      .export-overview-stars { font-size: 13px; color: #22324c; font-weight: 700; margin-bottom: 10px; }
      .export-overview-label { font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: #73829d; margin-bottom: 7px; }
      .export-target-chip-row { display: flex; flex-wrap: wrap; gap: 7px; }
      .export-target-chip { display: inline-flex; align-items: center; padding: 5px 9px; border-radius: 999px; border: 1px solid #d7deed; background: #fff; color: #22324c; font-size: 11px; line-height: 1.35; }
      .export-target-chip.muted { color: #73829d; background: #f8faff; }
      .export-overview-estimate { margin-top: 10px; font-size: 12px; color: #556886; line-height: 1.5; }
      .export-day-section { page-break-before: always; break-before: page; padding-top: 4px; }
      .export-day-section:first-of-type { page-break-before: auto; break-before: auto; }
      .export-day-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 14px; margin-bottom: 10px; padding: 16px 18px; border-radius: 16px; background: linear-gradient(135deg, #17253f 0%, #314c7c 100%); border: 1px solid #203152; box-shadow: inset 0 0 0 1px rgba(255,255,255,.06); }
      .export-day-title { font: 700 24px Orbitron, "Segoe UI", Arial, sans-serif; color: #f4c64d; }
      .export-day-sub { font-size: 12px; color: #d6def1; margin-top: 5px; }
      .export-day-stars { font: 700 22px Orbitron, "Segoe UI", Arial, sans-serif; color: #f4c64d; white-space: nowrap; padding: 8px 12px; border-radius: 999px; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.14); }
      .export-estimate-band { margin-bottom: 12px; padding: 10px 12px; border: 1px solid #d7deed; border-radius: 12px; background: #fffaf0; color: #5d512f; font-size: 12px; line-height: 1.55; font-weight: 600; }
      .export-subtitle { font: 700 13px Orbitron, "Segoe UI", Arial, sans-serif; letter-spacing: .08em; text-transform: uppercase; color: #6f7f9c; margin-bottom: 10px; }
      .export-day-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
      .day-chain { border: 1px solid #d7deed; border-radius: 14px; background: #fff; padding: 14px; min-height: 118px; box-sizing: border-box; }
      .day-chain.ds { border-left: 6px solid #cc5b5b; }
      .day-chain.mx { border-left: 6px solid #3ea87a; }
      .day-chain.ls { border-left: 6px solid #4685d9; }
      .day-chain.bonus { border-left: 6px solid #9b6bd3; }
      .day-chain-title { font-size: 10px; letter-spacing: .14em; text-transform: uppercase; color: #73829d; margin-bottom: 8px; font-family: Orbitron, "Segoe UI", Arial, sans-serif; }
      .day-planet-name { font: 700 16px Rajdhani, "Segoe UI", Arial, sans-serif; color: #142033; margin-bottom: 6px; }
      .day-stars { font: 700 18px Orbitron, "Segoe UI", Arial, sans-serif; color: #cc9e22; margin-bottom: 5px; }
      .day-action { font-size: 13px; color: #22324c; margin-bottom: 4px; font-weight: 600; }
      .day-advance { font-size: 12px; color: #62718f; line-height: 1.45; }
      .day-locked { font-size: 13px; color: #73829d; }
      .export-note-block { border: 1px solid #d7deed; border-radius: 12px; background: #fff; padding: 10px 12px; margin-top: 12px; }
      .export-note { font-size: 12px; color: #4c5d7b; line-height: 1.5; margin: 4px 0; }
      .export-ops-summary { font-size: 12px; color: #4c5d7b; margin-bottom: 12px; }
      .export-planet-section { border: 1px solid #d7deed; border-radius: 14px; background: #fff; padding: 14px 14px 12px; margin-bottom: 14px; }
      .export-planet-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 12px; }
      .export-planet-title { font: 700 18px Rajdhani, "Segoe UI", Arial, sans-serif; color: #142033; }
      .export-planet-sub { font-size: 12px; color: #62718f; line-height: 1.45; margin-top: 3px; }
      .export-planet-metrics { font-size: 12px; color: #4c5d7b; line-height: 1.45; text-align: right; white-space: nowrap; }
      .export-platoon-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-items: start; }
      .export-platoon-column { display: flex; flex-direction: column; gap: 12px; }
      .export-platoon-card { border: 1px solid #d7deed; border-left: 6px solid #9aa7c0; border-radius: 12px; padding: 12px; background: #fbfcff; }
      .export-platoon-card.complete { border-left-color: #27ae60; }
      .export-platoon-card.partial { border-left-color: #2980b9; }
      .export-platoon-card.impossible { border-left-color: #c0392b; }
      .export-platoon-card.ready { border-left-color: #8c98b3; }
      .export-platoon-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 10px; }
      .export-platoon-title { font: 700 14px Orbitron, "Segoe UI", Arial, sans-serif; color: #142033; }
      .export-platoon-sub { font-size: 11px; color: #73829d; margin-top: 2px; }
      .export-platoon-badge { font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 999px; border: 1px solid #d7deed; color: #4c5d7b; background: #fff; white-space: nowrap; }
      .export-platoon-badge.complete { color: #1f8a53; border-color: #9cddbb; background: #f2fcf6; }
      .export-platoon-badge.partial { color: #216aaf; border-color: #a6ccef; background: #f3f8fe; }
      .export-platoon-badge.impossible { color: #b1312f; border-color: #efb2af; background: #fff5f5; }
      .export-status-group { border: 1px solid #d7deed; border-radius: 12px; padding: 12px; background: #fbfcff; margin-bottom: 10px; }
      .export-status-group.complete { border-left: 6px solid #27ae60; }
      .export-status-group.preload { border-left: 6px solid #2980b9; }
      .export-status-group.ignore { border-left: 6px solid #8c98b3; }
      .export-status-group-title { font: 700 12px Orbitron, "Segoe UI", Arial, sans-serif; letter-spacing: .08em; text-transform: uppercase; color: #51627f; margin-bottom: 8px; }
      .export-status-chip-grid { display: flex; flex-wrap: wrap; gap: 8px; }
      .export-status-chip { min-width: 128px; border: 1px solid #d7deed; border-radius: 10px; background: #fff; padding: 8px 10px; }
      .export-status-chip.complete { background: #f2fcf6; border-color: #b4e0c6; }
      .export-status-chip.preload { background: #f3f8fe; border-color: #b7d5f3; }
      .export-status-chip.ignore { background: #f8f9fc; border-color: #d6ddeb; }
      .export-status-chip-label { font: 700 12px Rajdhani, "Segoe UI", Arial, sans-serif; color: #142033; }
      .export-status-chip-meta { font-size: 11px; color: #667891; margin-top: 3px; }
      .export-slot-list { display: grid; grid-template-columns: 1fr; gap: 8px; }
      .export-slot-card { border: 1px solid #e1e7f2; border-radius: 10px; padding: 8px 10px; background: #fff; }
      .export-slot-name { font: 700 13px Rajdhani, "Segoe UI", Arial, sans-serif; color: #142033; }
      .export-slot-assignee { font-size: 12px; color: #22324c; margin-top: 2px; }
      .export-slot-assignee.unassigned { color: #9b5a5a; }
      .export-slot-meta { font-size: 11px; color: #73829d; margin-top: 3px; line-height: 1.4; }
      .export-missing-card { margin-top: 12px; border: 1px dashed #e7b4b2; border-radius: 12px; padding: 10px 12px; background: #fff6f6; }
      .export-missing-title { font: 700 12px Orbitron, "Segoe UI", Arial, sans-serif; letter-spacing: .08em; text-transform: uppercase; color: #9b4542; margin-bottom: 6px; }
      .export-missing-text { font-size: 12px; color: #6a4a4a; line-height: 1.5; }
      .export-missing-subtitle { font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: #9b4542; margin-top: 10px; margin-bottom: 4px; }
      .export-missing-line { font-size: 12px; color: #6a4a4a; line-height: 1.45; padding: 2px 0; }
      .export-empty { border: 1px dashed #c7d0e1; border-radius: 12px; padding: 14px; color: #73829d; background: #fff; font-size: 12px; }
      @media print { body { padding: 0; } .export-header, .export-planet-section, .export-note-block, .day-chain, .export-platoon-card, .export-missing-card { break-inside: avoid; } }
    </style>
  </head>
  <body>
    <section class="export-header">
      <div class="export-title">${escapeHtml(docTitle)}</div>
      <div class="export-subhead"><strong>${escapeHtml(guildName)}</strong><br />Generated ${escapeHtml(generatedAt)}<br />Use your browser's <strong>Save as PDF</strong> destination to share this document.</div>
      <div class="export-metrics">
        <div class="export-metric"><div class="export-metric-label">Total Est. Stars</div><div class="export-metric-value">${escapeHtml(String(exportSummary.totalStars))}</div></div>
        <div class="export-metric"><div class="export-metric-label">Ops Filled</div><div class="export-metric-value">${escapeHtml(String(exportSummary.opsCompleted))}/${escapeHtml(String(exportSummary.opsTotal))}</div></div>
        <div class="export-metric"><div class="export-metric-label">Ops Points</div><div class="export-metric-value">${escapeHtml(formatMillions(exportSummary.opsPoints))}</div></div>
        <div class="export-metric"><div class="export-metric-label">Bonus Planets</div><div class="export-metric-value">${escapeHtml(String(exportSummary.bonusCount))}/2</div></div>
      </div>
    </section>
    ${overviewHtml}
    ${daySections}
    ${autoPrint ? '<script>window.addEventListener("load",function(){setTimeout(function(){try{window.focus();window.print();}catch(error){}},320);});<\/script>' : ""}
  </body>
</html>`;
}

function buildSeparatePlanExportHubHtml(
  days: number[],
  detailMode: PlanExportDetailMode,
) {
  const cards = days
    .map(
      (dayNumber) => `
        <a class="export-hub-btn" href="./day-${dayNumber}.html" target="_blank" rel="noreferrer">
          Open Day ${escapeHtml(String(dayNumber))} print view
        </a>
      `,
    )
    .join("");

  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>ROTE Separate Day Exports</title>
    <style>
      body { margin: 0; padding: 24px; background: #0b1220; color: #e8eaf0; font-family: "Segoe UI", Arial, sans-serif; }
      .wrap { max-width: 720px; margin: 0 auto; }
      .title { font: 700 24px Orbitron, "Segoe UI", Arial, sans-serif; color: #f0c040; margin-bottom: 8px; }
      .sub { font-size: 14px; line-height: 1.6; color: #a9b4c8; margin-bottom: 18px; }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
      .export-hub-btn { display: block; width: 100%; box-sizing: border-box; padding: 14px 16px; border-radius: 12px; border: 1px solid rgba(240,192,64,.3); background: #162033; color: #f0c040; font: 600 14px "Segoe UI", Arial, sans-serif; text-decoration: none; text-align: center; }
      .export-hub-btn:hover { background: #1b2942; }
      .note { margin-top: 18px; font-size: 13px; color: #7f8da8; line-height: 1.55; }
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="title">Separate Day Exports</div>
      <div class="sub">Browsers usually block multiple print windows from one click. Use the buttons below to open each day as its own printable document. Current layout: <strong>${escapeHtml(
        detailMode === "condensed" ? "Condensed" : "Detailed",
      )}</strong>.</div>
      <div class="grid">${cards}</div>
      <div class="note">Each day opens in its own window and triggers the print dialog automatically. Choose <strong>Save as PDF</strong> in each print dialog.</div>
    </div>
  </body>
</html>`;
}

export function buildPlannerSnapshotPayload(
  params: SnapshotBuilderParams,
): PlannerSnapshotPayload {
  return {
    version: 1,
    savedAt: new Date().toISOString(),
    primaryAllyCode: params.primaryAllyCode,
    plannerSettings: params.plannerSettings,
    selectedAlgorithm: params.selectedAlgorithm,
    optimizerAcknowledged: params.optimizerAcknowledged,
    selectedChain: params.selectedChain,
    selectedOperationsDay: params.selectedOperationsDay,
    selectedOperationsPlanetId: params.selectedOperationsPlanetId,
    selectedGuideMember: params.selectedGuideMember,
    selectedGuideMission: params.selectedGuideMission,
    expandedGuidePlanets: params.expandedGuidePlanets,
    guideData: params.guideData,
    guideEditorDifficulty: params.guideEditorDifficulty,
    selectedRosterMemberId: params.selectedRosterMemberId,
    rosterSearch: params.rosterSearch,
    rosterFilter: params.rosterFilter,
    rosterSortKey: params.rosterSortKey,
    guildSummary: params.guildSummary,
    guildRosters: params.guildRosters,
    opsDefinitions: params.opsDefinitions,
    opsAnalysis: params.opsAnalysis,
    plannerProjection: params.plannerProjection,
    plannerResult: params.plannerResult,
  };
}

export function buildPlanExportBundle({
  plannerResult,
  guildSummary,
  guildRosters,
  plannerReference,
  opsDefinitions,
  opsAnalysis,
  plannerSettings,
  mode,
  detailMode,
}: ExportBuilderParams): ExportBundle {
  const { planetMap, planetOrder } = buildPlanetMaps(plannerReference);
  const stamp = safeStamp(new Date());
  const folderName = `rote_plan_export_${stamp}`;

  if (mode === "separate") {
    const dayFiles = plannerResult.dayPlan.map((dayPlan) => ({
      name: `day-${dayPlan.day}.html`,
      contents: buildPlanExportDocumentHtml({
        plannerResult,
        guildSummary,
        guildRosters,
        planetMap,
        planetOrder,
        opsDefinitions,
        opsAnalysis,
        plannerSettings,
        dayNumbers: [dayPlan.day],
        docTitle: `Rise of the Empire - Day ${dayPlan.day} Export`,
        autoPrint: true,
        detailMode,
      }),
    }));

    return {
      folderName,
      openFileName: "index.html",
      files: [
        {
          name: "index.html",
          contents: buildSeparatePlanExportHubHtml(
            plannerResult.dayPlan.map((dayPlan) => dayPlan.day),
            detailMode,
          ),
        },
        ...dayFiles,
      ],
    };
  }

  return {
    folderName,
    openFileName: "index.html",
    files: [
      {
        name: "index.html",
        contents: buildPlanExportDocumentHtml({
          plannerResult,
          guildSummary,
          guildRosters,
          planetMap,
          planetOrder,
          opsDefinitions,
          opsAnalysis,
          plannerSettings,
          docTitle: "Rise of the Empire - Full Plan Export",
          autoPrint: true,
          detailMode,
        }),
      },
    ],
  };
}

export function buildPlanExportPreview({
  plannerResult,
  guildSummary,
  guildRosters,
  plannerReference,
  opsDefinitions,
  opsAnalysis,
  plannerSettings,
  mode,
  detailMode,
}: ExportBuilderParams): ExportPreviewBundle {
  const { planetMap, planetOrder } = buildPlanetMaps(plannerReference);

  if (mode === "separate") {
    const documents = plannerResult.dayPlan.map((dayPlan) => ({
      id: `day-${dayPlan.day}`,
      title: `Day ${dayPlan.day}`,
      html: buildPlanExportDocumentHtml({
        plannerResult,
        guildSummary,
        guildRosters,
        planetMap,
        planetOrder,
        opsDefinitions,
        opsAnalysis,
        plannerSettings,
        dayNumbers: [dayPlan.day],
        docTitle: `Rise of the Empire - Day ${dayPlan.day} Export`,
        autoPrint: false,
        detailMode,
      }),
    }));

    return {
      title: "Rise of the Empire - Day Export Preview",
      initialDocumentId: documents[0]?.id ?? "",
      documents,
    };
  }

  return {
    title: "Rise of the Empire - Full Plan Export",
    initialDocumentId: "full-plan",
    documents: [
      {
        id: "full-plan",
        title: "Full Plan",
        html: buildPlanExportDocumentHtml({
          plannerResult,
          guildSummary,
          guildRosters,
          planetMap,
          planetOrder,
          opsDefinitions,
          opsAnalysis,
          plannerSettings,
          docTitle: "Rise of the Empire - Full Plan Export",
          autoPrint: false,
          detailMode,
        }),
      },
    ],
  };
}
