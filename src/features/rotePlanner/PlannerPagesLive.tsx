import {
  Fragment,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FocusEvent as ReactFocusEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type Ref,
} from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import type {
  ExportPreviewResponse,
  GuildSummary,
  GuideSquad,
  GuideUnitCatalogEntry,
  OpsDefinitions,
  PlannerMissionDefinition,
  PlannerOptimizationResponse,
  PlannerPlanetDefinition,
  PlannerPlanetState,
  PlannerSettings,
  SimplifiedRosterUnit,
} from "../../lib/plannerApi";
import { plannerApi } from "../../lib/plannerApi";
import { usePlannerStore } from "../../state/plannerStoreCore";
import {
  dayPlanAlgorithms,
  type ChainKey,
  type GuideDifficulty,
  type RosterAbility,
} from "./mockData";
import {
  buildPlanExportPreview,
  buildPlannerSnapshotPayload,
  type PlanExportDetailMode,
  type PlanExportMode,
} from "./planExport";
import {
  buildOperationsMetrics,
  buildOperationsStage,
  buildOverviewMembers,
  buildPlanetOptions,
  buildRosterMembers,
  buildRosterSummary,
  filterRosterUnits,
  formatMillions,
  formatNumber,
} from "./runtimeViewModels";
import styles from "./PlannerUi.module.scss";

function toneClassName(tone: "gold" | "green" | "purple" | "neutral") {
  if (tone === "gold") return styles.metricValueGold;
  if (tone === "green") return styles.metricValueGreen;
  if (tone === "purple") return styles.metricValuePurple;
  return styles.metricValue;
}

function alignBadgeClassName(align: string, bonusLocked?: boolean) {
  if (align === "bonus") {
    return bonusLocked
      ? `${styles.alignBadge} ${styles.alignBadgeBonusLocked}`
      : `${styles.alignBadge} ${styles.alignBadgeBonus}`;
  }
  return `${styles.alignBadge} ${
    align === "ds"
      ? styles.alignBadgeDs
      : align === "mx"
        ? styles.alignBadgeMx
      : styles.alignBadgeLs
  }`;
}

function dayChainClassName(align: string) {
  return `${styles.dayChain} ${
    align === "bonus"
      ? styles.dayChainBonus
      : align === "ds"
        ? styles.dayChainDs
        : align === "mx"
          ? styles.dayChainMx
          : styles.dayChainLs
  }`;
}

function operationsStatusClassName(status: string) {
  if (status === "complete") return `${styles.platoonCard} ${styles.platoonCardComplete}`;
  if (status === "partial") return `${styles.platoonCard} ${styles.platoonCardPartial}`;
  if (status === "impossible") return `${styles.platoonCard} ${styles.platoonCardImpossible}`;
  return `${styles.platoonCard} ${styles.platoonCardReady}`;
}

function isGuideBonusPlanet(planet: PlannerPlanetDefinition) {
  return planet.chain === "bonus" || planet.id === "zeffo" || planet.id === "mandalore";
}

function guideMissionTypeIcon(mission: PlannerMissionDefinition) {
  if (mission.unlocks || mission.missionType === "sm") return "\u2605";
  if (mission.missionType === "fleet") return "\u2693";
  return "\u2694";
}

function guideMissionTypeLabel(mission: PlannerMissionDefinition) {
  if (mission.unlocks) return "Special Unlock Mission";
  if (mission.missionType === "sm") return "Special Mission";
  if (mission.missionType === "fleet") return "Fleet Mission";
  return "Combat Mission";
}

function normalizeRosterAbility(ability: RosterAbility | string): RosterAbility {
  if (typeof ability === "string") {
    return { name: ability };
  }
  return ability;
}

function guideMissionRequirement(planet: PlannerPlanetDefinition, mission: PlannerMissionDefinition) {
  if (mission.missionType === "fleet") {
    return `Phase ${planet.phase} | 7-star ships required`;
  }
  return `Phase ${planet.phase} | R${planet.minRelic}+ required`;
}

function buildGuidePhasePlanets(planets: PlannerPlanetDefinition[]) {
  const alignOrder = { ds: 0, mx: 1, ls: 2, bonus: 3 } as const;
  return [1, 2, 3, 4, 5, 6].map((phase) => ({
    phase,
    planets: planets
      .filter((planet) => planet.phase === phase)
      .sort((left, right) => {
        const leftOrder = alignOrder[left.align as keyof typeof alignOrder] ?? 9;
        const rightOrder = alignOrder[right.align as keyof typeof alignOrder] ?? 9;
        if (leftOrder !== rightOrder) return leftOrder - rightOrder;
        return left.name.localeCompare(right.name);
      }),
  }));
}

function exportPreviewTokenFromSearch(search: string) {
  const fromSearch = new URLSearchParams(search).get("token")?.trim();
  if (fromSearch) return fromSearch;
  const hashQuery = window.location.hash.split("?")[1] ?? "";
  return new URLSearchParams(hashQuery).get("token")?.trim() ?? "";
}

function commandErrorMessage(reason: unknown) {
  if (reason instanceof Error) return reason.message;
  if (typeof reason === "string") return reason;
  if (reason && typeof reason === "object") {
    if ("message" in reason && typeof reason.message === "string") {
      return reason.message;
    }
    if ("error" in reason && typeof reason.error === "string") {
      return reason.error;
    }
    try {
      return JSON.stringify(reason);
    } catch {
      return String(reason);
    }
  }
  return String(reason);
}

function plannerCardsForChain(
  chain: "ds" | "mx" | "ls",
  reference: ReturnType<typeof usePlannerStore.getState>["plannerReference"],
  projection: ReturnType<typeof usePlannerStore.getState>["plannerProjection"],
) {
  if (!reference || !projection) return [];
  const cards: Array<{
    planet: (typeof reference.planets)[number];
    card: NonNullable<typeof projection>["planetCards"][string];
  }> = [];
  const chainPlanets = reference.planets.filter((planet) => planet.chain === chain);
  for (const planet of chainPlanets) {
    const card = projection.planetCards[planet.id];
    if (card) {
      cards.push({ planet, card });
    }
    const bonus = reference.planets.find(
      (entry) => entry.chain === "bonus" && entry.unlockedBy === planet.id,
    );
    if (bonus) {
      const bonusCard = projection.planetCards[bonus.id];
      if (bonusCard) cards.push({ planet: bonus, card: bonusCard });
    }
  }
  return cards;
}

function plannerDepth(planetId: string) {
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

function plannerMaxHoldDays(planet: PlannerPlanetDefinition) {
  return Math.max(1, 7 - planet.phase);
}

function plannerBonusPlanetUnlocked(
  planet: PlannerPlanetDefinition,
  settings: PlannerSettings,
) {
  if (planet.chain !== "bonus" || !planet.unlockedBy) {
    return true;
  }
  const sourceState = settings.planetState[planet.unlockedBy];
  if (sourceState?.smReady) {
    return true;
  }
  return (sourceState?.smCount ?? 0) >= (planet.unlockedAt ?? 0);
}

function missionEstimateInputLimit(cmMode: string, memberCount = 50) {
  const countLimit = Math.min(50, Math.max(1, Math.round(memberCount || 50)));
  return cmMode === "count" ? countLimit : 100;
}

function planetPlannerDisplayValue(
  planetId: string,
  settings: PlannerSettings,
  state: PlannerPlanetState | undefined,
  kind: "cm" | "fleet",
) {
  const depth = plannerDepth(planetId);
  const base = kind === "cm" ? settings.cmBase : settings.fleetBase;
  const falloff = kind === "cm" ? settings.cmFalloff : settings.fleetFalloff;
  const defaultValue = Math.max(0, base - falloff * depth);

  if (settings.cmMode === "pct") {
    const rawValue =
      kind === "cm"
        ? state?.cmRateOverride ?? defaultValue
        : state?.fleetRateOverride ?? defaultValue;
    return Math.round(Math.min(100, Math.max(0, rawValue)));
  }

  const countLimit = missionEstimateInputLimit(settings.cmMode, settings.guildMembers);
  const defaultCount = Math.min(countLimit, defaultValue);
  const rawValue =
    kind === "cm"
      ? state?.cmCountOverride ?? defaultCount
      : state?.fleetCountOverride ?? defaultCount;
  return Math.round(Math.min(countLimit, Math.max(0, rawValue)));
}

function planetPlannerMissionDisplayValue(
  planetId: string,
  missionId: string,
  settings: PlannerSettings,
  state: PlannerPlanetState | undefined,
  kind: "cm" | "fleet",
) {
  const missionOverride = state?.missionOverrides?.[missionId];
  const planetValue = planetPlannerDisplayValue(planetId, settings, state, kind);

  if (settings.cmMode === "pct") {
    return Math.round(
      Math.min(100, Math.max(0, missionOverride?.rateOverride ?? planetValue)),
    );
  }

  return Math.round(
    Math.min(
      missionEstimateInputLimit(settings.cmMode, settings.guildMembers),
      Math.max(0, missionOverride?.countOverride ?? planetValue),
    ),
  );
}

function starCountFromStatus(status: string) {
  if (status === "s3") return 3;
  if (status === "s2") return 2;
  if (status === "s1") return 1;
  return 0;
}

function plannerDayPlanetIds(dayPlan: PlannerOptimizationResponse | null, day: number) {
  const current = dayPlan?.dayPlan.find((entry) => entry.day === day);
  if (!current) return [];
  return [
    current.chains.ds?.planetId,
    current.chains.mx?.planetId,
    current.chains.ls?.planetId,
    ...current.bonusPlanets.map((planet) => planet.planetId),
  ].filter((value): value is string => typeof value === "string" && value.length > 0);
}

function buildGuildMemberNameMap(guildSummary: GuildSummary | null) {
  const out = new Map<string, string>();
  guildSummary?.members.forEach((member) => {
    if (member.allyCode) out.set(member.allyCode, member.displayName);
    if (member.playerId) out.set(member.playerId, member.displayName);
  });
  return out;
}

function titleizeOperationsPlanet(planetId: string) {
  return planetId
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function operationsRequirementText(minRarity: number, minRelic: number) {
  return minRelic > 0 ? `${minRarity}* | R${minRelic}+` : `${minRarity}* | Ship`;
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

function buildPlannerOpsStage(
  plannerResult: PlannerOptimizationResponse | null,
  day: number,
  planetId: string,
  opsDefinitions: OpsDefinitions | null,
  guildSummary: GuildSummary | null,
) {
  const dayPlan = plannerResult?.dayPlan.find((entry) => entry.day === day);
  const planetDay = dayPlan?.opsPlanets[planetId];
  const platoonDefs = opsDefinitions?.[planetId] ?? [];
  if (!planetDay && !platoonDefs.length) return null;

  const memberNameMap = buildGuildMemberNameMap(guildSummary);
  const assignmentsByPlatoon = new Map<number, Map<number, NonNullable<typeof planetDay>["assignments"][number]["entries"][number]>>();
  const todayAssignmentsByPlatoon = new Map<number, Set<number>>();
  const completedToday = new Set<number>();

  plannerResult?.dayPlan
    .filter((entry) => entry.day <= day)
    .forEach((entry) => {
      const opsPlanet = entry.opsPlanets[planetId];
      if (!opsPlanet) return;

      opsPlanet.assignments.forEach((assignmentGroup) => {
        const history = assignmentsByPlatoon.get(assignmentGroup.platoonIdx) ?? new Map();
        assignmentGroup.entries.forEach((slotAssignment) => {
          history.set(slotAssignment.reqIdx, slotAssignment);
        });
        assignmentsByPlatoon.set(assignmentGroup.platoonIdx, history);

        if (entry.day !== day) return;

        const todaySlots = todayAssignmentsByPlatoon.get(assignmentGroup.platoonIdx) ?? new Set();
        assignmentGroup.entries.forEach((slotAssignment) => {
          todaySlots.add(slotAssignment.reqIdx);
        });
        todayAssignmentsByPlatoon.set(assignmentGroup.platoonIdx, todaySlots);

        if (assignmentGroup.completed) {
          completedToday.add(assignmentGroup.platoonIdx);
        }
      });
    });

  const historyPlatoonIndexes = Array.from(assignmentsByPlatoon.keys());
  const platoonCount = Math.max(
    platoonDefs.length,
    historyPlatoonIndexes.length ? Math.max(...historyPlatoonIndexes) + 1 : 0,
  );

  return {
    stageTitle: `${titleizeOperationsPlanet(planetId)} - Planned Operations`,
    stageSubtitle: "Assignments rebuilt from the optimizer timeline so each platoon reflects all 15 operation slots by the selected day.",
    stageMeta: planetDay
      ? `Today: ${planetDay.slotsFilled} slots | ${planetDay.completedToday} completed | ${formatMillions(planetDay.pointsEarned)}`
      : "No optimizer assignments for this day yet.",
    platoons: Array.from({ length: platoonCount }, (_, index) => {
      const slotDefs = platoonDefs[index] ?? [];
      const slotDisplayNames = numberOperationsSlotNames(
        slotDefs.map((slot) => slot.name || `Slot ${index + 1}`),
      );
      const historicalAssignments = assignmentsByPlatoon.get(index) ?? new Map();
      const todayAssignments = todayAssignmentsByPlatoon.get(index) ?? new Set();
      const totalSlots = slotDefs.length || historicalAssignments.size;
      const filledToDay = historicalAssignments.size;
      const status =
        totalSlots > 0 && filledToDay >= totalSlots
          ? "complete"
          : filledToDay > 0
            ? "partial"
            : "ready";

      return {
        id: index + 1,
        status,
        filled: `${filledToDay}/${totalSlots} slots filled`,
        label: completedToday.has(index)
          ? "Completed today"
          : status === "complete"
            ? "Completed"
            : todayAssignments.size > 0
              ? "Partial today"
              : filledToDay > 0
                ? "Partially loaded"
                : "Unfilled",
        slots:
          totalSlots > 0
            ? Array.from({ length: totalSlots }, (_, slotIndex) => {
                const slotDef = slotDefs[slotIndex];
                const assignment = historicalAssignments.get(slotIndex);
                const requirementText = operationsRequirementText(
                  slotDef?.minRarity ?? assignment?.minRarity ?? 7,
                  slotDef?.minRelic ?? assignment?.minRelic ?? 0,
                );
                const displayName =
                  slotDisplayNames[slotIndex] ??
                  slotDef?.name ??
                  assignment?.name ??
                  `Slot ${slotIndex + 1}`;
                const displayMember = assignment
                  ? memberNameMap.get(assignment.allyCode) ?? assignment.allyCode
                  : "Unassigned";
                return {
                  name: displayName,
                  assignee: assignment
                    ? `${displayMember} (${todayAssignments.has(slotIndex) ? "today" : `Day ${assignment.day}`})`
                    : "Unassigned",
                  meta: `Requirement: ${requirementText}`,
                  unassigned: !assignment,
                };
              })
            : [],
      };
    }),
  };
}

type GuideEditorDraft = {
  id: string | null;
  leader: string;
  members: string[];
  notes: string;
  videoUrl: string;
  requiredTbOmicronKeys: string[];
};

type GuideEditorSubmit = {
  id: string | null;
  leader: string;
  leaderDefId: string;
  members: string[];
  memberDefIds: string[];
  notes: string;
  videoUrl: string;
  requiredTbOmicrons: GuideSquad["requiredTbOmicrons"];
  difficulty: GuideDifficulty;
};

type GuideUnitLookup = {
  defId: string;
  name: string;
  combatType: number;
};

type GuideOmicronOption = {
  key: string;
  unitDefId: string;
  unitName: string;
  skillId: string;
  skillName: string;
};

type GuideRosterCheckEntry = {
  slot: "leader" | "starter" | "reinforcement" | "member";
  label: string;
  name: string;
  ok: boolean;
  reason: string;
};

type GuideRosterCheck = {
  ok: boolean;
  failCount: number;
  reason: string;
  entries: GuideRosterCheckEntry[];
};

const GUIDE_FLEET_STARTER_COUNT = 3;
const GUIDE_TB_OMICRON_AREA = 7;
const GUIDE_MISSION_LIMIT = 20;
const CAPITAL_SHIP_DEFIDS = new Set([
  "CAPITALCHIMAERA",
  "CHIMAERA",
  "CAPITALEXECUTOR",
  "EXECUTOR",
  "CAPITALEXECUTRIX",
  "EXECUTRIX",
  "CAPITALFINALIZER",
  "FINALIZER",
  "CAPITALJEDICRUISER",
  "ENDURANCE",
  "CAPITALLEVIATHAN",
  "LEVIATHAN",
  "CAPITALMALEVOLENCE",
  "MALEVOLENCE",
  "CAPITALMONCALAMARICRUISER",
  "HOMEONE",
  "CAPITALNEGOTIATOR",
  "NEGOTIATOR",
  "CAPITALPROFUNDITY",
  "PROFUNDITY",
  "CAPITALRADDUS",
  "RADDUS",
  "CAPITALSTARDESTROYER",
  "EXECUTRIX",
]);

function guideMissionKey(planetId: string, missionId: string) {
  return `${planetId}___${missionId}`;
}

function guideMissionCopyGroup(mission: PlannerMissionDefinition) {
  if (mission.unlocks) return "unlock";
  return mission.missionType;
}

function normalizeGuideUnitName(value: string) {
  let normalized = "";
  for (const character of value.trim()) {
    if (character === "&") {
      normalized += "and";
      continue;
    }
    if (/[a-z0-9]/i.test(character)) {
      normalized += character.toLowerCase();
    }
  }
  return normalized;
}

function normalizeGuideDefId(value: string) {
  return value.trim().toUpperCase().split(":")[0] ?? "";
}

function normalizeGuideSkillKey(value: string) {
  return normalizeGuideDefId(value);
}

function buildGuideUnitLookup(
  guideUnitCatalog: GuideUnitCatalogEntry[],
  guildRosters: ReturnType<typeof usePlannerStore.getState>["guildRosters"],
) {
  const lookup = new Map<string, GuideUnitLookup>();
  for (const unit of guideUnitCatalog) {
    const normalizedName = normalizeGuideUnitName(unit.name);
    if (!normalizedName || lookup.has(normalizedName)) continue;
    lookup.set(normalizedName, {
      defId: unit.defId,
      name: unit.name,
      combatType: unit.combatType,
    });
  }
  for (const roster of Object.values(guildRosters)) {
    for (const unit of roster ?? []) {
      const normalizedName = normalizeGuideUnitName(unit.name);
      if (!normalizedName || lookup.has(normalizedName)) continue;
      lookup.set(normalizedName, {
        defId: unit.defId,
        name: unit.name,
        combatType: unit.combatType,
      });
    }
  }
  return lookup;
}

function buildGuideUnitSelectionKey(name: string, lookup?: GuideUnitLookup | null) {
  const defId = normalizeGuideDefId(lookup?.defId ?? "");
  if (defId) return `DEF:${defId}`;
  const normalizedName = normalizeGuideUnitName(name);
  return normalizedName ? `NAME:${normalizedName}` : "";
}

function isCapitalGuideUnit(lookup?: GuideUnitLookup | null) {
  return CAPITAL_SHIP_DEFIDS.has(normalizeGuideDefId(lookup?.defId ?? ""));
}

function findRosterGuideUnit(
  roster: SimplifiedRosterUnit[],
  name: string,
  defId: string,
) {
  const normalizedDefId = normalizeGuideDefId(defId);
  if (normalizedDefId) {
    const byDefId = roster.find((unit) => normalizeGuideDefId(unit.defId) === normalizedDefId);
    if (byDefId) return byDefId;
  }
  const normalizedName = normalizeGuideUnitName(name);
  if (!normalizedName) return null;
  return (
    roster.find((unit) => normalizeGuideUnitName(unit.name) === normalizedName) ?? null
  );
}

function buildGuideOmicronOptions(
  draft: GuideEditorDraft | null,
  isFleetMission: boolean,
  guideTbOmicrons: ReturnType<typeof usePlannerStore.getState>["guideTbOmicrons"],
  guideUnitLookup: Map<string, GuideUnitLookup>,
) {
  if (!draft || isFleetMission) return [] as GuideOmicronOption[];

  const seenUnits = new Set<string>();
  const units = [draft.leader, ...draft.members]
    .map((name) => {
      const lookup = guideUnitLookup.get(normalizeGuideUnitName(name));
      return {
        name: name.trim(),
        defId: normalizeGuideDefId(lookup?.defId ?? ""),
      };
    })
    .filter((entry) => entry.name && entry.defId && !seenUnits.has(entry.defId))
    .map((entry) => {
      seenUnits.add(entry.defId);
      return entry;
    });

  const options: GuideOmicronOption[] = [];
  for (const unit of units) {
    for (const skill of guideTbOmicrons[unit.defId] ?? []) {
      const skillKey = normalizeGuideSkillKey(skill.skillId);
      if (!skillKey) continue;
      options.push({
        key: `${unit.defId}|${skillKey}`,
        unitDefId: unit.defId,
        unitName: unit.name,
        skillId: skill.skillId,
        skillName: skill.name || skill.skillId,
      });
    }
  }

  return options;
}

function buildGuideRosterCheck(
  squad: GuideSquad,
  roster: SimplifiedRosterUnit[] | null,
  mission: PlannerMissionDefinition,
  planet: PlannerPlanetDefinition,
): GuideRosterCheck | null {
  if (!roster) return null;

  const isFleetMission = mission.missionType === "fleet";
  const requiredRelic = planet.minRelic;
  const requiredOmicrons = new Map<string, GuideSquad["requiredTbOmicrons"]>();
  for (const requirement of squad.requiredTbOmicrons ?? []) {
    const key = normalizeGuideDefId(requirement.unitDefId);
    if (!key) continue;
    const current = requiredOmicrons.get(key) ?? [];
    current.push(requirement);
    requiredOmicrons.set(key, current);
  }

  const entries: Array<{
    slot: GuideRosterCheckEntry["slot"];
    label: string;
    name: string;
    defId: string;
    required: boolean;
  }> = [];

  if (squad.leader || squad.members.some((entry) => entry.trim())) {
    entries.push({
      slot: "leader",
      label: isFleetMission ? "Capital Ship" : "Leader",
      name: squad.leader.trim(),
      defId: squad.leaderDefId,
      required: true,
    });
  }

  if (isFleetMission) {
    for (let index = 0; index < GUIDE_FLEET_STARTER_COUNT; index += 1) {
      entries.push({
        slot: "starter",
        label: `Starter ${index + 1}`,
        name: squad.members[index]?.trim() ?? "",
        defId: squad.memberDefIds[index] ?? "",
        required: true,
      });
    }
    for (let index = GUIDE_FLEET_STARTER_COUNT; index < squad.members.length; index += 1) {
      const name = squad.members[index]?.trim() ?? "";
      if (!name) continue;
      entries.push({
        slot: "reinforcement",
        label: `Reinforcement ${index + 1 - GUIDE_FLEET_STARTER_COUNT}`,
        name,
        defId: squad.memberDefIds[index] ?? "",
        required: false,
      });
    }
  } else {
    squad.members.forEach((member, index) => {
      const name = member.trim();
      if (!name) return;
      entries.push({
        slot: "member",
        label: `Member ${index + 1}`,
        name,
        defId: squad.memberDefIds[index] ?? "",
        required: true,
      });
    });
  }

  if (!entries.length) return null;

  const results = entries.map<GuideRosterCheckEntry>((entry) => {
    if (!entry.name) {
      return {
        slot: entry.slot,
        label: entry.label,
        name: "",
        ok: false,
        reason: isFleetMission ? "No ship assigned" : "No unit assigned",
      };
    }

    const rosterUnit = findRosterGuideUnit(roster, entry.name, entry.defId);
    if (!rosterUnit) {
      return {
        slot: entry.slot,
        label: entry.label,
        name: entry.name,
        ok: false,
        reason: "Not in roster",
      };
    }

    if (isFleetMission && entry.slot === "leader" && !CAPITAL_SHIP_DEFIDS.has(normalizeGuideDefId(rosterUnit.defId))) {
      return {
        slot: entry.slot,
        label: entry.label,
        name: entry.name,
        ok: false,
        reason: "Not a capital ship",
      };
    }

    if (isFleetMission && entry.slot !== "leader" && CAPITAL_SHIP_DEFIDS.has(normalizeGuideDefId(rosterUnit.defId))) {
      return {
        slot: entry.slot,
        label: entry.label,
        name: entry.name,
        ok: false,
        reason: "Capital ships can only lead",
      };
    }

    if (rosterUnit.rarity < 7) {
      return {
        slot: entry.slot,
        label: entry.label,
        name: entry.name,
        ok: false,
        reason: "Not 7-star",
      };
    }

    if (!isFleetMission && rosterUnit.relic < requiredRelic) {
      return {
        slot: entry.slot,
        label: entry.label,
        name: entry.name,
        ok: false,
        reason: `R${rosterUnit.relic} (need R${requiredRelic})`,
      };
    }

    if (!isFleetMission) {
      const omicronRequirements = requiredOmicrons.get(normalizeGuideDefId(rosterUnit.defId)) ?? [];
      if (omicronRequirements.length) {
        const unlockedTbOmicrons = new Set(
          rosterUnit.skills
            .filter((skill) => skill.hasOmicron && skill.omicronArea === GUIDE_TB_OMICRON_AREA)
            .map((skill) => normalizeGuideSkillKey(skill.skillId || skill.id))
            .filter(Boolean),
        );
        const missingOmicrons = omicronRequirements.filter(
          (requirement) => !unlockedTbOmicrons.has(normalizeGuideSkillKey(requirement.skillId)),
        );
        if (missingOmicrons.length) {
          return {
            slot: entry.slot,
            label: entry.label,
            name: entry.name,
            ok: false,
            reason: `Missing TB omicron: ${missingOmicrons
              .map((requirement) => requirement.skillName || requirement.skillId)
              .join(", ")}`,
          };
        }

        return {
          slot: entry.slot,
          label: entry.label,
          name: entry.name,
          ok: true,
          reason: `R${rosterUnit.relic} | TB omi ready`,
        };
      }
    }

    return {
      slot: entry.slot,
      label: entry.label,
      name: entry.name,
      ok: true,
      reason: isFleetMission ? "7-star ready" : `R${rosterUnit.relic}`,
    };
  });

  const failCount = results.filter((result) => !result.ok).length;
  return {
    ok: failCount === 0,
    failCount,
    reason: results
      .map((result) => `${result.ok ? "OK" : "Missing"} ${result.label}${result.name ? ` - ${result.name}` : ""} (${result.reason})`)
      .join("\n"),
    entries: results,
  };
}

function difficultyBadgeClassName(difficulty: string) {
  if (difficulty === "easy") return `${styles.difficultyBadge} ${styles.difficultyEasy}`;
  if (difficulty === "medium") return `${styles.difficultyBadge} ${styles.difficultyMedium}`;
  if (difficulty === "hard") return `${styles.difficultyBadge} ${styles.difficultyHard}`;
  return `${styles.difficultyBadge} ${styles.difficultyAuto}`;
}

function normalizeGuideVideoUrl(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

function createGuideEditorDraft(isFleetMission: boolean, squad?: GuideSquad | null): GuideEditorDraft {
  const slotCount = isFleetMission ? 7 : 4;
  return {
    id: squad?.id ?? null,
    leader: squad?.leader ?? "",
    members: Array.from({ length: slotCount }, (_, index) => squad?.members[index] ?? ""),
    notes: squad?.notes ?? "",
    videoUrl: squad?.videoUrl ?? "",
    requiredTbOmicronKeys: (squad?.requiredTbOmicrons ?? []).map(
      (entry) => `${entry.unitDefId.toUpperCase()}|${entry.skillId}`,
    ),
  };
}

function buildGuideEditorFieldOptions(
  draft: GuideEditorDraft,
  fieldKey: string,
  options: string[],
  guideUnitLookup: Map<string, GuideUnitLookup>,
  query: string,
  isFleetMission: boolean,
) {
  const currentValue =
    fieldKey === "leader"
      ? draft.leader
      : draft.members[Number(fieldKey.replace("member-", ""))] ?? "";
  const currentLookup = guideUnitLookup.get(normalizeGuideUnitName(currentValue));
  const currentKey = buildGuideUnitSelectionKey(currentValue, currentLookup);
  const occupiedKeys = new Set<string>();

  const pushOccupied = (value: string, otherFieldKey: string) => {
    if (!value.trim() || otherFieldKey === fieldKey) return;
    const lookup = guideUnitLookup.get(normalizeGuideUnitName(value));
    const key = buildGuideUnitSelectionKey(value, lookup);
    if (key) occupiedKeys.add(key);
  };

  pushOccupied(draft.leader, "leader");
  draft.members.forEach((member, index) => pushOccupied(member, `member-${index}`));

  const needle = normalizeGuideUnitName(query);
  const role = fieldKey === "leader" ? "leader" : "member";
  const available = options.filter((option) => {
    const optionLookup = guideUnitLookup.get(normalizeGuideUnitName(option));
    if (!optionLookup) return false;
    if (isFleetMission && role === "leader" && !isCapitalGuideUnit(optionLookup)) {
      return false;
    }
    if (isFleetMission && role !== "leader" && isCapitalGuideUnit(optionLookup)) {
      return false;
    }
    const optionKey = buildGuideUnitSelectionKey(option, optionLookup);
    if (optionKey && occupiedKeys.has(optionKey) && optionKey !== currentKey) {
      return false;
    }
    return true;
  });

  if (!needle) {
    return available.slice(0, 80);
  }

  const starts: string[] = [];
  const contains: string[] = [];
  for (const option of available) {
    const normalizedOption = normalizeGuideUnitName(option);
    if (normalizedOption.startsWith(needle)) {
      starts.push(option);
      continue;
    }
    if (normalizedOption.includes(needle)) {
      contains.push(option);
    }
  }

  return starts.concat(contains).slice(0, 80);
}

type GuideAutocompleteFieldProps = {
  fieldKey: string;
  label: string;
  placeholder: string;
  value: string;
  options: string[];
  isOpen: boolean;
  highlightedIndex: number;
  inputRef?: Ref<HTMLInputElement>;
  onOpen: (fieldKey: string) => void;
  onClose: (fieldKey: string) => void;
  onChange: (fieldKey: string, value: string) => void;
  onSelect: (fieldKey: string, value: string) => void;
  onHighlight: (index: number) => void;
};

function GuideAutocompleteField({
  fieldKey,
  label,
  placeholder,
  value,
  options,
  isOpen,
  highlightedIndex,
  inputRef,
  onOpen,
  onClose,
  onChange,
  onSelect,
  onHighlight,
}: GuideAutocompleteFieldProps) {
  const hasSuggestions = options.length > 0;

  const handleBlur = (event: ReactFocusEvent<HTMLDivElement>) => {
    const nextFocusTarget = event.relatedTarget;
    if (nextFocusTarget instanceof Node && event.currentTarget.contains(nextFocusTarget)) {
      return;
    }
    onClose(fieldKey);
  };

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (!isOpen) {
      if (event.key === "ArrowDown" && hasSuggestions) {
        event.preventDefault();
        onOpen(fieldKey);
        onHighlight(0);
      }
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (hasSuggestions) {
        onHighlight((highlightedIndex + 1) % options.length);
      }
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (hasSuggestions) {
        onHighlight((highlightedIndex - 1 + options.length) % options.length);
      }
      return;
    }

    if (event.key === "Enter") {
      const highlightedOption = options[highlightedIndex];
      if (highlightedOption) {
        event.preventDefault();
        onSelect(fieldKey, highlightedOption);
      }
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      onClose(fieldKey);
    }
  };

  return (
    <label className={styles.modalField}>
      <span className={styles.label}>{label}</span>
      <div className={styles.autocompleteField} onBlur={handleBlur}>
        <input
          ref={inputRef}
          className={styles.modalInput}
          autoComplete="off"
          placeholder={placeholder}
          value={value}
          aria-autocomplete="list"
          aria-expanded={isOpen}
          onFocus={() => onOpen(fieldKey)}
          onChange={(event) => onChange(fieldKey, event.currentTarget.value)}
          onKeyDown={handleKeyDown}
        />
        {isOpen ? (
          <div className={styles.autocompleteList}>
            {hasSuggestions ? (
              options.map((option, index) => (
                <button
                  key={`${fieldKey}-${option}`}
                  type="button"
                  className={`${styles.autocompleteOption} ${
                    index === highlightedIndex ? styles.autocompleteOptionActive : ""
                  }`}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => onSelect(fieldKey, option)}
                  onFocus={() => onHighlight(index)}
                >
                  {option}
                </button>
              ))
            ) : (
              <div className={styles.autocompleteEmpty}>No matching units found.</div>
            )}
          </div>
        ) : null}
      </div>
    </label>
  );
}

function guidePlanetNameClassName(
  planet: PlannerPlanetDefinition,
  styleMap: Record<string, string>,
) {
  if (isGuideBonusPlanet(planet)) {
    return `${styleMap.guidePlanetName} ${styleMap.guidePlanetNameBonus}`;
  }
  if (planet.align === "ds") {
    return `${styleMap.guidePlanetName} ${styleMap.guidePlanetNameDs}`;
  }
  if (planet.align === "mx") {
    return `${styleMap.guidePlanetName} ${styleMap.guidePlanetNameMx}`;
  }
  return `${styleMap.guidePlanetName} ${styleMap.guidePlanetNameLs}`;
}

function guideMissionBadgeClassName(
  mission: PlannerMissionDefinition,
  styleMap: Record<string, string>,
) {
  if (mission.unlocks) {
    return `${styleMap.missionTypeBadge} ${styleMap.missionTypeBadgeUnlock}`;
  }
  if (mission.missionType === "sm") {
    return `${styleMap.missionTypeBadge} ${styleMap.missionTypeBadgeSpecial}`;
  }
  if (mission.missionType === "fleet") {
    return `${styleMap.missionTypeBadge} ${styleMap.missionTypeBadgeFleet}`;
  }
  return `${styleMap.missionTypeBadge} ${styleMap.missionTypeBadgeCombat}`;
}

type GuideEditorModalProps = {
  planet: PlannerPlanetDefinition;
  mission: PlannerMissionDefinition;
  initialSquad: GuideSquad | null;
  initialDifficulty: GuideDifficulty;
  guideTbOmicrons: ReturnType<typeof usePlannerStore.getState>["guideTbOmicrons"];
  guideUnitLookup: Map<string, GuideUnitLookup>;
  guideCharacterOptions: string[];
  guideShipOptions: string[];
  onClose: () => void;
  onSave: (payload: GuideEditorSubmit) => void;
};

function GuideEditorModal({
  planet,
  mission,
  initialSquad,
  initialDifficulty,
  guideTbOmicrons,
  guideUnitLookup,
  guideCharacterOptions,
  guideShipOptions,
  onClose,
  onSave,
}: GuideEditorModalProps) {
  const isFleetMission = mission.missionType === "fleet";
  const expectedCombatType = isFleetMission ? 2 : 1;
  const leaderInputRef = useRef<HTMLInputElement>(null);
  const [difficulty, setDifficulty] = useState<GuideDifficulty>(initialDifficulty);
  const [draft, setDraft] = useState<GuideEditorDraft>(() =>
    createGuideEditorDraft(isFleetMission, initialSquad),
  );
  const [error, setError] = useState("");
  const [openFieldKey, setOpenFieldKey] = useState<string | null>("leader");
  const [highlightedOptionIndex, setHighlightedOptionIndex] = useState(0);
  const guideOmicronOptions = buildGuideOmicronOptions(
    draft,
    isFleetMission,
    guideTbOmicrons,
    guideUnitLookup,
  );

  useEffect(() => {
    setDifficulty(initialDifficulty);
    setDraft(createGuideEditorDraft(isFleetMission, initialSquad));
    setError("");
    setOpenFieldKey("leader");
    setHighlightedOptionIndex(0);
  }, [initialDifficulty, initialSquad, isFleetMission, mission.id, planet.id]);

  useEffect(() => {
    const visibleKeys = new Set(guideOmicronOptions.map((option) => option.key));
    const filteredKeys = draft.requiredTbOmicronKeys.filter((key) => visibleKeys.has(key));
    if (
      filteredKeys.length !== draft.requiredTbOmicronKeys.length ||
      filteredKeys.some((key, index) => key !== draft.requiredTbOmicronKeys[index])
    ) {
      setDraft((current) => ({
        ...current,
        requiredTbOmicronKeys: filteredKeys,
      }));
    }
  }, [draft.requiredTbOmicronKeys, guideOmicronOptions]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const frame = window.requestAnimationFrame(() => {
      leaderInputRef.current?.focus();
      leaderInputRef.current?.select();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  const optionSource = isFleetMission ? guideShipOptions : guideCharacterOptions;
  const buildFieldOptions = (fieldKey: string, value: string) =>
    buildGuideEditorFieldOptions(
      draft,
      fieldKey,
      optionSource,
      guideUnitLookup,
      value,
      isFleetMission,
    );
  const leaderOptions =
    openFieldKey === "leader" ? buildFieldOptions("leader", draft.leader) : [];

  const updateFieldValue = (fieldKey: string, value: string) => {
    setDraft((current) => {
      if (fieldKey === "leader") {
        return {
          ...current,
          leader: value,
        };
      }
      const index = Number(fieldKey.replace("member-", ""));
      return {
        ...current,
        members: current.members.map((entry, memberIndex) =>
          memberIndex === index ? value : entry,
        ),
      };
    });
    setOpenFieldKey(fieldKey);
    setHighlightedOptionIndex(0);
    setError("");
  };

  const selectFieldOption = (fieldKey: string, value: string) => {
    updateFieldValue(fieldKey, value);
    setOpenFieldKey(null);
  };

  const submit = () => {
    const leader = draft.leader.trim();
    if (!leader) {
      setError("Squad leader name is required.");
      return;
    }

    const leaderLookup = guideUnitLookup.get(normalizeGuideUnitName(leader));
    if (leaderLookup && leaderLookup.combatType !== expectedCombatType) {
      setError(
        isFleetMission
          ? "Fleet missions can only use ship names."
          : "Combat and special missions can only use character names.",
      );
      return;
    }
    if (isFleetMission && leaderLookup && !isCapitalGuideUnit(leaderLookup)) {
      setError("Fleet mission leaders must be capital ships.");
      return;
    }

    const members = draft.members.map((entry) => entry.trim());
    if (isFleetMission && members.slice(0, GUIDE_FLEET_STARTER_COUNT).some((entry) => !entry)) {
      setError("Fleet guides require 3 starting ships before they can be saved.");
      return;
    }

    const memberLookups = members.map((entry) =>
      guideUnitLookup.get(normalizeGuideUnitName(entry)) ?? null,
    );
    const invalidMember = memberLookups.find(
      (lookup) => lookup && lookup.combatType !== expectedCombatType,
    );
    if (invalidMember) {
      setError(
        isFleetMission
          ? "Fleet missions can only use ship names."
          : "Combat and special missions can only use character names.",
      );
      return;
    }

    if (isFleetMission && memberLookups.some((lookup) => lookup && isCapitalGuideUnit(lookup))) {
      setError("Capital ships can only be used in the fleet leader slot.");
      return;
    }

    const duplicateKeys = new Set<string>();
    const entries = [{ name: leader, lookup: leaderLookup ?? null }].concat(
      members.filter(Boolean).map((name, index) => ({ name, lookup: memberLookups[index] })),
    );
    for (const entry of entries) {
      const key = buildGuideUnitSelectionKey(entry.name, entry.lookup);
      if (!key) continue;
      if (duplicateKeys.has(key)) {
        setError(`Each squad slot must use a unique unit. Duplicate found: ${entry.name}`);
        return;
      }
      duplicateKeys.add(key);
    }

    const selectedOmicronKeys = new Set(draft.requiredTbOmicronKeys);
    const requiredTbOmicrons = guideOmicronOptions
      .filter((option) => selectedOmicronKeys.has(option.key))
      .map((option) => ({
        unitDefId: option.unitDefId,
        unitName: option.unitName,
        skillId: option.skillId,
        skillName: option.skillName,
      }));

    onSave({
      id: draft.id,
      leader,
      leaderDefId: leaderLookup?.defId ?? "",
      members,
      memberDefIds: memberLookups.map((lookup) => lookup?.defId ?? ""),
      notes: draft.notes.trim(),
      videoUrl: normalizeGuideVideoUrl(draft.videoUrl),
      requiredTbOmicrons,
      difficulty,
    });
  };

  const modal = (
    <div
      className={styles.modalBackdrop}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className={styles.modalCard} onClick={(event) => event.stopPropagation()}>
        <div className={styles.modalHeader}>
          <div>
            <div className={styles.modalTitle}>{initialSquad ? "Edit Squad" : "Add Squad"}</div>
            <div className={styles.noteText}>
              {planet.name} - {mission.label} | {guideMissionRequirement(planet, mission)}
            </div>
          </div>
          <button type="button" className={styles.closeButton} onClick={onClose}>
            X
          </button>
        </div>

        <div className={styles.modalField}>
          <div className={styles.label}>Difficulty</div>
          <div className={styles.difficultyRow}>
            {(["auto", "easy", "medium", "hard"] as GuideDifficulty[]).map((value) => (
              <button
                key={value}
                type="button"
                className={`${styles.difficultyButton} ${
                  difficulty === value ? styles.difficultyButtonActive : ""
                }`}
                onClick={() => setDifficulty(value)}
              >
                {value}
              </button>
            ))}
          </div>
        </div>

        <GuideAutocompleteField
          fieldKey="leader"
          label={isFleetMission ? "Capital Ship Leader" : "Squad Leader"}
          placeholder={isFleetMission ? "e.g. Leviathan" : "e.g. Sith Eternal Emperor"}
          value={draft.leader}
          options={leaderOptions}
          isOpen={openFieldKey === "leader"}
          highlightedIndex={highlightedOptionIndex}
          inputRef={leaderInputRef}
          onOpen={(fieldKey) => {
            setOpenFieldKey(fieldKey);
            setHighlightedOptionIndex(0);
          }}
          onClose={(fieldKey) => {
            setOpenFieldKey((current) => (current === fieldKey ? null : current));
            setHighlightedOptionIndex(0);
          }}
          onChange={updateFieldValue}
          onSelect={selectFieldOption}
          onHighlight={setHighlightedOptionIndex}
        />

        <div className={styles.fieldHint}>
          Start typing to narrow the list. Units must be unique within a squad.
        </div>

        <div className={styles.fieldHint}>
          {isFleetMission
            ? "Fleet guides require 1 capital ship leader, 3 starting ships, and may add up to 4 reinforcements."
            : "Combat and special mission guides accept characters only."}
        </div>

        {isFleetMission ? (
          <>
            <div className={styles.slotGroupHeading}>Starting Ships (required)</div>
            <div className={styles.modalSlotsGrid}>
              {draft.members.slice(0, GUIDE_FLEET_STARTER_COUNT).map((member, index) => {
                const fieldKey = `member-${index}`;
                const options = openFieldKey === fieldKey ? buildFieldOptions(fieldKey, member) : [];
                return (
                  <GuideAutocompleteField
                    key={`starter-${index}`}
                    fieldKey={fieldKey}
                    label={`Starting Ship ${index + 1}`}
                    placeholder={`Starting Ship ${index + 1}`}
                    value={member}
                    options={options}
                    isOpen={openFieldKey === fieldKey}
                    highlightedIndex={highlightedOptionIndex}
                    onOpen={(nextFieldKey) => {
                      setOpenFieldKey(nextFieldKey);
                      setHighlightedOptionIndex(0);
                    }}
                    onClose={(nextFieldKey) => {
                      setOpenFieldKey((current) => (current === nextFieldKey ? null : current));
                      setHighlightedOptionIndex(0);
                    }}
                    onChange={updateFieldValue}
                    onSelect={selectFieldOption}
                    onHighlight={setHighlightedOptionIndex}
                  />
                );
              })}
            </div>

            <div className={styles.slotGroupHeading}>Reinforcements (optional)</div>
            <div className={styles.modalSlotsGrid}>
              {draft.members.slice(GUIDE_FLEET_STARTER_COUNT).map((member, index) => {
                const memberIndex = index + GUIDE_FLEET_STARTER_COUNT;
                const fieldKey = `member-${memberIndex}`;
                const options = openFieldKey === fieldKey ? buildFieldOptions(fieldKey, member) : [];
                return (
                  <GuideAutocompleteField
                    key={`reinforcement-${index}`}
                    fieldKey={fieldKey}
                    label={`Reinforcement ${index + 1}`}
                    placeholder={`Reinforcement ${index + 1}`}
                    value={member}
                    options={options}
                    isOpen={openFieldKey === fieldKey}
                    highlightedIndex={highlightedOptionIndex}
                    onOpen={(nextFieldKey) => {
                      setOpenFieldKey(nextFieldKey);
                      setHighlightedOptionIndex(0);
                    }}
                    onClose={(nextFieldKey) => {
                      setOpenFieldKey((current) => (current === nextFieldKey ? null : current));
                      setHighlightedOptionIndex(0);
                    }}
                    onChange={updateFieldValue}
                    onSelect={selectFieldOption}
                    onHighlight={setHighlightedOptionIndex}
                  />
                );
              })}
            </div>
          </>
        ) : (
          <div className={styles.modalSlotsGrid}>
            {draft.members.map((member, index) => {
              const fieldKey = `member-${index}`;
              const options = openFieldKey === fieldKey ? buildFieldOptions(fieldKey, member) : [];
              return (
                <GuideAutocompleteField
                  key={`member-${index}`}
                  fieldKey={fieldKey}
                  label={`Member ${index + 2}`}
                  placeholder={`Member ${index + 2}`}
                  value={member}
                  options={options}
                  isOpen={openFieldKey === fieldKey}
                  highlightedIndex={highlightedOptionIndex}
                  onOpen={(nextFieldKey) => {
                    setOpenFieldKey(nextFieldKey);
                    setHighlightedOptionIndex(0);
                  }}
                  onClose={(nextFieldKey) => {
                    setOpenFieldKey((current) => (current === nextFieldKey ? null : current));
                    setHighlightedOptionIndex(0);
                  }}
                  onChange={updateFieldValue}
                  onSelect={selectFieldOption}
                  onHighlight={setHighlightedOptionIndex}
                />
              );
            })}
          </div>
        )}

        {!isFleetMission ? (
          <div className={styles.modalField}>
            <div className={styles.label}>Required Territory Battle Omicrons</div>
            {guideOmicronOptions.length ? (
              <div className={styles.omicronOptionList}>
                {guideOmicronOptions.map((option) => (
                  <label key={option.key} className={styles.omicronOptionCard}>
                    <input
                      type="checkbox"
                      checked={draft.requiredTbOmicronKeys.includes(option.key)}
                      onChange={(event) => {
                        const checked = event.currentTarget.checked;
                        setDraft((current) => ({
                          ...current,
                          requiredTbOmicronKeys: checked
                            ? [...current.requiredTbOmicronKeys, option.key]
                            : current.requiredTbOmicronKeys.filter((entry) => entry !== option.key),
                        }));
                      }}
                    />
                    <div>
                      <div className={styles.squadSectionValue}>{option.skillName}</div>
                      <div className={styles.fieldHint}>
                        Territory Battle omicron on {option.unitName}
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            ) : (
              <div className={styles.fieldHint}>
                {Object.keys(guideTbOmicrons).length
                  ? "No Territory Battle omicrons are available for the currently selected units."
                  : "Run Scan Rosters to load Territory Battle omicron data for this guide editor."}
              </div>
            )}
          </div>
        ) : null}

        <label className={styles.modalField}>
          <span className={styles.label}>Notes / Strategy</span>
          <textarea
            className={styles.modalInput}
            placeholder="Strategy notes, tips, mod recommendations..."
            rows={4}
            value={draft.notes}
            onChange={(event) => {
              const nextNotes = event.currentTarget.value;
              setDraft((current) => ({
                ...current,
                notes: nextNotes,
              }));
            }}
          />
        </label>

        <label className={styles.modalField}>
          <span className={styles.label}>YouTube URL</span>
          <input
            className={styles.modalInput}
            type="url"
            autoComplete="off"
            placeholder="https://youtube.com/watch?v=..."
            value={draft.videoUrl}
            onChange={(event) => {
              const nextVideoUrl = event.currentTarget.value;
              setDraft((current) => ({
                ...current,
                videoUrl: nextVideoUrl,
              }));
            }}
          />
        </label>

        {error ? <div className={styles.modalError}>{error}</div> : null}

        <div className={styles.modalFooter}>
          <div className={styles.modalFooterCopy}>
            Guide squads are stored in the app workspace and can be shared through guide
            JSON export/import.
          </div>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>
            Cancel
          </button>
          <button type="button" className={styles.primaryButton} onClick={submit}>
            {initialSquad ? "Update Squad" : "Save Squad"}
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}

type GuideCopyMissionOption = {
  planetId: string;
  planetName: string;
  missionId: string;
  missionLabel: string;
  squadCount: number;
};

type GuideCopyModalProps = {
  squad: GuideSquad;
  sourcePlanetName: string;
  sourceMissionLabel: string;
  targetPlanetId: string;
  targetMissionId: string;
  targetPlanets: Array<{ id: string; name: string }>;
  targetMissions: GuideCopyMissionOption[];
  onPlanetChange: (planetId: string) => void;
  onMissionChange: (missionId: string) => void;
  onClose: () => void;
  onConfirm: () => void;
};

function GuideCopyModal({
  squad,
  sourcePlanetName,
  sourceMissionLabel,
  targetPlanetId,
  targetMissionId,
  targetPlanets,
  targetMissions,
  onPlanetChange,
  onMissionChange,
  onClose,
  onConfirm,
}: GuideCopyModalProps) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  const modal = (
    <div
      className={styles.modalBackdrop}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className={styles.modalCard} onClick={(event) => event.stopPropagation()}>
        <div className={styles.modalHeader}>
          <div>
            <div className={styles.modalTitle}>Copy Guide</div>
            <div className={styles.noteText}>
              {sourcePlanetName} - {sourceMissionLabel}
            </div>
          </div>
          <button type="button" className={styles.closeButton} onClick={onClose}>
            X
          </button>
        </div>

        <div className={styles.squadSection}>
          <div className={styles.squadSectionLabel}>Copying Squad</div>
          <div className={styles.squadSectionValue}>{squad.leader || "Unnamed Squad"}</div>
        </div>

        <label className={styles.modalField}>
          <span className={styles.label}>Target Planet</span>
          <select
            className={styles.selectControl}
            value={targetPlanetId}
            onChange={(event) => onPlanetChange(event.currentTarget.value)}
          >
            {targetPlanets.length ? (
              targetPlanets.map((planet) => (
                <option key={planet.id} value={planet.id}>
                  {planet.name}
                </option>
              ))
            ) : (
              <option value="">No eligible target planets</option>
            )}
          </select>
        </label>

        <label className={styles.modalField}>
          <span className={styles.label}>Target Mission</span>
          <select
            className={styles.selectControl}
            value={targetMissionId}
            onChange={(event) => onMissionChange(event.currentTarget.value)}
            disabled={!targetMissions.length}
          >
            {targetMissions.length ? (
              targetMissions.map((mission) => (
                <option key={`${mission.planetId}-${mission.missionId}`} value={mission.missionId}>
                  {mission.missionLabel} ({mission.squadCount}/{GUIDE_MISSION_LIMIT})
                </option>
              ))
            ) : (
              <option value="">No eligible target missions</option>
            )}
          </select>
        </label>

        <div className={styles.fieldHint}>
          Guides can only be copied to the same mission type on a different planet.
        </div>

        <div className={styles.modalFooter}>
          <div className={styles.modalFooterCopy}>
            This keeps the squad composition, notes, omicrons, and YouTube link intact.
          </div>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={onConfirm}
            disabled={!targetPlanetId || !targetMissionId || !targetMissions.length}
          >
            Copy Guide
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}

function triggerJsonDownload(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function GuildOverviewPage() {
  const primaryAllyCode = usePlannerStore((state) => state.primaryAllyCode);
  const guildSummary = usePlannerStore((state) => state.guildSummary);
  const guildRosters = usePlannerStore((state) => state.guildRosters);
  const plannerSettings = usePlannerStore((state) => state.plannerSettings);
  const plannerProjection = usePlannerStore((state) => state.plannerProjection);
  const isFetchingGuild = usePlannerStore((state) => state.isFetchingGuild);
  const isScanningRosters = usePlannerStore((state) => state.isScanningRosters);
  const statusMessage = usePlannerStore((state) => state.statusMessage);
  const lastSyncAt = usePlannerStore((state) => state.lastSyncAt);
  const setPrimaryAllyCode = usePlannerStore((state) => state.setPrimaryAllyCode);
  const setPlannerMode = usePlannerStore((state) => state.setPlannerMode);
  const setPlannerNumber = usePlannerStore((state) => state.setPlannerNumber);
  const setDailyUndep = usePlannerStore((state) => state.setDailyUndep);
  const fillDailyUndepFromDayOne = usePlannerStore((state) => state.fillDailyUndepFromDayOne);
  const applyMissionEstimatesToPlanner = usePlannerStore(
    (state) => state.applyMissionEstimatesToPlanner,
  );
  const fetchGuildByAllyCode = usePlannerStore((state) => state.fetchGuildByAllyCode);
  const scanGuildRosters = usePlannerStore((state) => state.scanGuildRosters);

  const [draftAllyCode, setDraftAllyCode] = useState(primaryAllyCode || "");
  const [applyStatus, setApplyStatus] = useState("");
  const displayedMembers = buildOverviewMembers(guildSummary, guildRosters);
  const summary = plannerProjection?.summary;
  const zoneNames = ["Z1 R5", "Z2 R6", "Z3 R7", "Z4 R8", "Z5 R9", "Z6 R9"];
  const zoneColors = ["#5dade2", "#27ae60", "#d4ac0d", "#e67e22", "#9b59b6", "#e74c3c"];
  const cmValues = Array.from({ length: 6 }, (_, index) =>
    Math.max(0, plannerSettings.cmBase - index * plannerSettings.cmFalloff),
  );
  const fleetValues = Array.from({ length: 6 }, (_, index) =>
    Math.max(0, plannerSettings.fleetBase - index * plannerSettings.fleetFalloff),
  );
  const falloffMax = Math.max(...cmValues, ...fleetValues, 1);
  const estimateInputLimit = missionEstimateInputLimit(
    plannerSettings.cmMode,
    plannerSettings.guildMembers,
  );
  const guildMemberCount = guildSummary?.members.length ?? plannerSettings.guildMembers;
  const guildGpValue = guildSummary?.gp ?? plannerSettings.guildGp;

  const handleApplyMissionEstimates = () => {
    applyMissionEstimatesToPlanner();
    setApplyStatus("Applied to all planets");
    globalThis.setTimeout(() => setApplyStatus(""), 2500);
  };

  return (
    <section className={styles.panel}>
      <div className={styles.panelCard}>
        <div className={styles.cardTitle}>Live Guild Import</div>
        <div className={styles.importBanner}>
          <div className={styles.importIcon}>LINK</div>
          <div className={styles.importText}>
            <h3>Import directly from the game</h3>
            <p>Enter any guild member&apos;s ally code to fetch guild GP, member list, and roster data.</p>
          </div>
        </div>

        <div className={styles.formGrid}>
          <label className={styles.field}>
            <span className={styles.label}>Ally Code (any guild member)</span>
            <input
              className={styles.input}
              value={draftAllyCode}
              onChange={(event) => {
                setDraftAllyCode(event.currentTarget.value);
                setPrimaryAllyCode(event.currentTarget.value);
              }}
            />
          </label>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => void fetchGuildByAllyCode(draftAllyCode)}
            disabled={isFetchingGuild}
          >
            Fetch Guild
          </button>
        </div>

        <div className={styles.statusBar}>{statusMessage}</div>

        <div className={styles.memberToolbar}>
          <div>
            <div className={styles.memberHeading}>{guildSummary?.name ?? "Crimson Order"}</div>
            <div className={styles.memberSubheading}>
              {guildSummary ? `${formatMillions(guildSummary.gp)} GP` : "452.7M GP"}
            </div>
          </div>
          <button
            type="button"
            className={styles.scanButton}
            onClick={() => void scanGuildRosters()}
            disabled={!guildSummary || isScanningRosters}
          >
            Scan Rosters
          </button>
        </div>

        <div className={styles.memberGrid}>
          {displayedMembers.map((member, index) => (
            <article key={`${member.name}-${index}`} className={styles.memberCard}>
              <div className={styles.memberName}>{member.name}</div>
              <div className={styles.memberGp}>{member.gp}</div>
              <div className={styles.relicBar}>
                {member.relicPips.map((pip, index) => (
                  <span
                    key={`${member.name}-${index}`}
                    className={`${styles.relicPip} ${
                      pip === "r7"
                        ? styles.relicPipR7
                        : pip === "r5"
                          ? styles.relicPipR5
                          : ""
                    }`}
                  />
                ))}
              </div>
            </article>
          ))}
        </div>
      </div>

      <div className={styles.settingsGrid}>
        <div className={styles.panelCard}>
          <div className={styles.cardTitle}>Guild Stats</div>
          <label className={styles.field}>
            <span className={styles.label}>Total Guild Galactic Power</span>
            <input
              className={`${styles.input} ${styles.readOnlyInput}`}
              type="number"
              value={guildGpValue}
              readOnly
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Guild Members</span>
            <input
              className={`${styles.input} ${styles.readOnlyInput}`}
              type="number"
              value={guildMemberCount}
              readOnly
            />
          </label>
          <div className={styles.metricGrid}>
            {[
              { label: "Est. Stars", value: `${summary?.estimatedStars ?? 0}`, tone: "gold" as const },
              {
                label: "Ops Filled",
                value: `${summary?.opsFilled ?? 0} / ${summary?.opsTotal ?? 0}`,
                tone: "green" as const,
              },
              {
                label: "Bonus Planets",
                value: `${summary?.bonusEligibleCount ?? 0} eligible`,
                tone: "purple" as const,
              },
              {
                label: "Roster Coverage",
                value: summary?.rosterCoverage ?? "No guild loaded",
                tone: "neutral" as const,
              },
            ].map((metric) => (
              <article key={metric.label} className={styles.metricCard}>
                <div className={styles.metricLabel}>{metric.label}</div>
                <div className={`${styles.metricValue} ${toneClassName(metric.tone)}`}>
                  {metric.value}
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className={styles.panelCard}>
          <div className={styles.cardTitle}>Mission Completion Estimates</div>
          <div className={styles.toggleGroup}>
            <button
              type="button"
              className={`${styles.toggleButton} ${plannerSettings.cmMode === "pct" ? styles.toggleButtonActive : ""}`}
              onClick={() => setPlannerMode("cmMode", "pct")}
            >
              % Rate
            </button>
            <button
              type="button"
              className={`${styles.toggleButton} ${plannerSettings.cmMode === "count" ? styles.toggleButtonActive : ""}`}
              onClick={() => setPlannerMode("cmMode", "count")}
            >
              # Count
            </button>
          </div>
          <div className={styles.twoColumnGrid}>
            {[
              ["cmBase", plannerSettings.cmMode === "count" ? "CM clear members" : "CM base %"],
              ["cmFalloff", plannerSettings.cmMode === "count" ? "CM falloff (members)" : "CM falloff %"],
              ["fleetBase", plannerSettings.cmMode === "count" ? "Fleet completions" : "Fleet base %"],
              ["fleetFalloff", plannerSettings.cmMode === "count" ? "Fleet falloff (members)" : "Fleet falloff %"],
            ].map(([key, label]) => (
              <label key={key} className={styles.field}>
                <span className={styles.label}>{label}</span>
                <input
                  className={styles.input}
                  type="number"
                  min={0}
                  max={estimateInputLimit}
                  value={plannerSettings[key as keyof PlannerSettings] as number}
                  onChange={(event) =>
                    setPlannerNumber(
                      key as "cmBase" | "cmFalloff" | "fleetBase" | "fleetFalloff",
                      Number(event.currentTarget.value) || 0,
                    )
                  }
                />
              </label>
            ))}
          </div>
          <div className={styles.noteText}>
            CM base starts on the first planet in each lane. Falloff reduces that estimate for
            each deeper zone before pushing the defaults into the Planet Planner.
          </div>
          <div className={styles.vizTitle}>Rate by planet depth</div>
          <div className={styles.falloffVizDetailed}>
            {zoneNames.map((zoneName, index) => (
              <div
                key={zoneName}
                className={styles.falloffZone}
                style={{ borderLeftColor: zoneColors[index] }}
              >
                <div className={styles.falloffBars}>
                  <div
                    className={`${styles.falloffBar} ${styles.falloffBarCm}`}
                    style={{ height: `${Math.round((cmValues[index] / falloffMax) * 44)}px` }}
                    title={`CM ${Math.round(cmValues[index])}`}
                  />
                  <div
                    className={`${styles.falloffBar} ${styles.falloffBarFleet}`}
                    style={{ height: `${Math.round((fleetValues[index] / falloffMax) * 44)}px` }}
                    title={`Fleet ${Math.round(fleetValues[index])}`}
                  />
                </div>
                <div className={styles.falloffZoneLabel}>{zoneName}</div>
                <div className={styles.falloffValueCm}>
                  {plannerSettings.cmMode === "count"
                    ? Math.round(cmValues[index])
                    : `${Math.round(cmValues[index])}%`}
                </div>
                <div className={styles.falloffValueFleet}>
                  {plannerSettings.cmMode === "count"
                    ? Math.round(fleetValues[index])
                    : `${Math.round(fleetValues[index])}%`}
                </div>
              </div>
            ))}
          </div>
          <div className={styles.vizLegend}>
            <span className={styles.vizLegendItem}>
              <span className={`${styles.vizLegendSwatch} ${styles.vizLegendSwatchCm}`} />
              CM %
            </span>
            <span className={styles.vizLegendItem}>
              <span className={`${styles.vizLegendSwatch} ${styles.vizLegendSwatchFleet}`} />
              Fleet %
            </span>
            <span className={styles.vizLegendHint}>Left border = zone / relic requirement</span>
          </div>
          <button
            type="button"
            className={`${styles.primaryButton} ${styles.fullButton}`}
            onClick={handleApplyMissionEstimates}
          >
            Apply to Planet Planner
          </button>
          <div className={styles.inlineStatus}>{applyStatus}</div>
        </div>

        <div className={styles.panelCard}>
          <div className={styles.cardTitle}>Daily Undeployed GP</div>
          <div className={styles.noteText}>
            Account for members who miss a day. This feeds the optimizer as unused GP for each TB
            day.
          </div>
          <div className={styles.toggleGroup}>
            <button
              type="button"
              className={`${styles.toggleButton} ${plannerSettings.undepMode === "pct" ? styles.toggleButtonActive : ""}`}
              onClick={() => setPlannerMode("undepMode", "pct")}
            >
              % of GP
            </button>
            <button
              type="button"
              className={`${styles.toggleButton} ${plannerSettings.undepMode === "flat" ? styles.toggleButtonActive : ""}`}
              onClick={() => setPlannerMode("undepMode", "flat")}
            >
              Flat GP
            </button>
          </div>
          <table className={styles.dailyTable}>
            <thead>
              <tr>
                <th>Day</th>
                <th>{plannerSettings.undepMode === "pct" ? "Undeployed %" : "Undeployed GP"}</th>
                <th>Effective GP</th>
              </tr>
            </thead>
            <tbody>
              {plannerSettings.dailyUndep.map((value, index) => {
                const effective =
                  plannerSettings.undepMode === "pct"
                    ? plannerSettings.guildGp * (1 - value / 100)
                    : plannerSettings.guildGp - value;
                return (
                  <tr key={index}>
                    <td>D{index + 1}</td>
                    <td>
                      <input
                        className={styles.tableInput}
                        type="number"
                        min={0}
                        max={plannerSettings.undepMode === "pct" ? 100 : plannerSettings.guildGp}
                        value={value}
                        onChange={(event) =>
                          setDailyUndep(index, Number(event.currentTarget.value) || 0)
                        }
                      />
                    </td>
                    <td>{formatMillions(Math.max(0, effective))}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={fillDailyUndepFromDayOne}
          >
            Fill all from Day 1
          </button>
          <div className={styles.noteText}>
            {lastSyncAt ? `Last live sync: ${new Date(lastSyncAt).toLocaleString()}` : "No live scan completed yet."}
          </div>
        </div>
      </div>
    </section>
  );
}

export function PlanetPlannerPage() {
  const selectedChain = usePlannerStore((state) => state.selectedChain);
  const plannerReference = usePlannerStore((state) => state.plannerReference);
  const plannerProjection = usePlannerStore((state) => state.plannerProjection);
  const plannerSettings = usePlannerStore((state) => state.plannerSettings);
  const setSelectedChain = usePlannerStore((state) => state.setSelectedChain);
  const setPlanetPlannerState = usePlannerStore((state) => state.setPlanetPlannerState);
  const setPlanetMissionOverride = usePlannerStore((state) => state.setPlanetMissionOverride);
  const cards = plannerCardsForChain(selectedChain, plannerReference, plannerProjection);
  const plannerInputLimit = missionEstimateInputLimit(
    plannerSettings.cmMode,
    plannerSettings.guildMembers,
  );

  const renderPlanetCard = (
    planet: PlannerPlanetDefinition,
    card: NonNullable<typeof plannerProjection>["planetCards"][string],
  ) => {
    const state = plannerSettings.planetState[planet.id];
    const bonusLocked = !plannerBonusPlanetUnlocked(planet, plannerSettings);
    const stars = starCountFromStatus(card.status);
    const specialUnlock = card.specialMissions.find((mission) => mission.unlocks);
    const regularSpecialMissions = card.specialMissions.filter((mission) => !mission.unlocks);
    const unlockedLabel = specialUnlock?.unlocks
      ? `${specialUnlock.unlocks.charAt(0).toUpperCase()}${specialUnlock.unlocks.slice(1)}`
      : "";

    return (
      <article
        className={`${styles.planetCard} ${
          planet.align === "bonus"
            ? styles.planetCardBonus
            : planet.align === "ds"
              ? styles.planetCardDs
              : planet.align === "mx"
                ? styles.planetCardMx
                : styles.planetCardLs
        } ${card.status === "s3" ? styles.planetCardS3 : ""} ${
          card.status === "s2" ? styles.planetCardS2 : ""
        } ${card.status === "s1" ? styles.planetCardS1 : ""} ${
          bonusLocked ? styles.planetCardLocked : ""
        }`}
      >
        <div className={styles.planetHeader}>
          <div>
            <div className={styles.planetName}>{card.name}</div>
            <div className={styles.planetCapability}>{card.capability}</div>
          </div>
          <span className={alignBadgeClassName(card.align, bonusLocked)}>
            {card.align === "bonus"
              ? bonusLocked
                ? "Bonus Locked"
                : "Bonus"
              : card.align === "ds"
                ? "Dark"
                : card.align === "mx"
                  ? "Mixed"
                  : "Light"}
          </span>
        </div>

        <div className={styles.starsRow}>
          {[0, 1, 2].map((index) => (
            <span
              key={`${planet.id}-star-${index}`}
              className={`${styles.star} ${index < stars ? styles.starActive : ""}`}
            >
              {index < stars ? "\u2605" : "\u2606"}
            </span>
          ))}
        </div>

        <div className={styles.pointsRow}>
          Est: <strong>{formatMillions(card.estimate)}</strong> / {formatMillions(card.target)}
        </div>
        <div className={styles.progressBar}>
          <div className={styles.progressFill} style={{ width: `${card.progress}%` }} />
        </div>

        <div className={styles.missionSection}>
          <div className={styles.missionHeader}>
            Combat / Special Missions ({card.combatMissions.length})
          </div>
          {card.combatMissions.map((mission) => (
            <div key={mission.id} className={styles.missionEstimateRow}>
              <span>{mission.label}</span>
              <div>
                <div className={styles.miniLabel}>
                  {plannerSettings.cmMode === "pct" ? "Clear %" : "Clear #"}
                </div>
                <input
                  className={styles.tableInput}
                  type="number"
                  min={0}
                  max={plannerInputLimit}
                  value={planetPlannerMissionDisplayValue(
                    planet.id,
                    mission.id,
                    plannerSettings,
                    state,
                    "cm",
                  )}
                  onChange={(event) =>
                    setPlanetMissionOverride(planet.id, mission.id, {
                      ...(plannerSettings.cmMode === "pct"
                        ? {
                            rateOverride: Number(event.currentTarget.value) || 0,
                            countOverride: null,
                          }
                        : {
                            countOverride: Number(event.currentTarget.value) || 0,
                            rateOverride: null,
                          }),
                    })
                  }
                />
              </div>
              <div>
                <div className={styles.miniLabel}>est pts</div>
                <div className={styles.miniValue}>{formatMillions(mission.points)}</div>
              </div>
            </div>
          ))}
          {card.fleetMissions.map((mission) => (
            <div key={mission.id} className={styles.missionEstimateRow}>
              <span>{mission.label}</span>
              <div>
                <div className={styles.miniLabel}>
                  {plannerSettings.cmMode === "pct" ? "Comp %" : "Comp #"}
                </div>
                <input
                  className={styles.tableInput}
                  type="number"
                  min={0}
                  max={plannerInputLimit}
                  value={planetPlannerMissionDisplayValue(
                    planet.id,
                    mission.id,
                    plannerSettings,
                    state,
                    "fleet",
                  )}
                  onChange={(event) =>
                    setPlanetMissionOverride(planet.id, mission.id, {
                      ...(plannerSettings.cmMode === "pct"
                        ? {
                            rateOverride: Number(event.currentTarget.value) || 0,
                            countOverride: null,
                          }
                        : {
                            countOverride: Number(event.currentTarget.value) || 0,
                            rateOverride: null,
                          }),
                    })
                  }
                />
              </div>
              <div>
                <div className={styles.miniLabel}>est pts</div>
                <div className={styles.miniValue}>{formatMillions(mission.points)}</div>
              </div>
            </div>
          ))}
        </div>

        {specialUnlock ? (
          <div className={styles.specialMissionBox}>
            <div className={styles.specialMissionLabel}>{specialUnlock.label}</div>
            <label className={styles.specialMissionToggle}>
              <input
                type="checkbox"
                checked={Boolean(state?.smReady)}
                onChange={(event) =>
                  setPlanetPlannerState(planet.id, {
                    smReady: event.currentTarget.checked,
                    smCount: event.currentTarget.checked
                      ? Math.max(state?.smCount ?? 0, planet.smThreshold ?? 0)
                      : 0,
                  })
                }
              />
              <span>
                Plan to unlock {unlockedLabel || "the bonus planet"} on {planet.name}
              </span>
            </label>
            <div className={styles.specialMissionNote}>
              {state?.smReady
                ? `${unlockedLabel || "Bonus planet"} is enabled for the planner.`
                : "Leave unchecked unless the guild can clear this unlock special mission."}
              {regularSpecialMissions.length ? (
                <>
                  <br />
                  Other special missions:{" "}
                  {regularSpecialMissions.map((mission) => mission.label).join(", ")}
                </>
              ) : null}
            </div>
          </div>
        ) : regularSpecialMissions.length ? (
          <div className={styles.specialMissionBox}>
            <div className={styles.specialMissionLabel}>
              {regularSpecialMissions.length > 1 ? "Special Missions" : "Special Mission"}
            </div>
            <div className={styles.specialMissionNote}>
              Guide-only missions on this planet:{" "}
              {regularSpecialMissions.map((mission) => mission.label).join(", ")}. These do not
              add projected territory points.
            </div>
          </div>
        ) : null}

        <div className={styles.operationsRow}>
          {Array.from({ length: Math.max(card.operationsTotal, 6) }).map((_, slotIndex) => (
            <span
              key={`${planet.id}-${slotIndex}`}
              className={`${styles.operationsPill} ${slotIndex < card.operationsFilled ? styles.operationsPillOn : ""}`}
            >
              {slotIndex + 1}
            </span>
          ))}
        </div>
        <div className={styles.noteText}>{card.operationsNote}</div>
        <div className={styles.planetNote}>{bonusLocked ? "Bonus locked" : card.note}</div>
      </article>
    );
  };

  return (
    <section className={styles.panel}>
      <div className={styles.plannerToolbar}>
        <div className={styles.chainSelect}>
          {[
            ["ds", "Dark Side"],
            ["mx", "Mixed"],
            ["ls", "Light Side"],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`${styles.chainButton} ${
                selectedChain === key
                  ? key === "ds"
                    ? styles.chainButtonDsActive
                    : key === "mx"
                      ? styles.chainButtonMxActive
                      : styles.chainButtonLsActive
                  : ""
              }`}
              onClick={() => setSelectedChain(key as ChainKey)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.chainStack}>
        {cards.map(({ planet, card }) => (
          <Fragment key={planet.id}>{renderPlanetCard(planet, card)}</Fragment>
        ))}
      </div>

    </section>
  );
}

export function ExportPreviewPage() {
  const location = useLocation();
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [preview, setPreview] = useState<ExportPreviewResponse | null>(null);
  const [activeDocumentId, setActiveDocumentId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const token = exportPreviewTokenFromSearch(location.search);

  useEffect(() => {
    let cancelled = false;

    if (!token) {
      setPreview(null);
      setActiveDocumentId("");
      setError("This export preview is missing its session token.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError("");
    setPreview(null);

    void plannerApi
      .getExportPreview(token)
      .then((response) => {
        if (cancelled) return;
        setPreview(response);
        setActiveDocumentId(response.initialDocumentId || response.documents[0]?.id || "");
        setLoading(false);
      })
      .catch((reason) => {
        if (cancelled) return;
        const message = commandErrorMessage(reason);
        setError(`Could not load the export preview: ${message}`);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    if (!preview) return;
    document.title = preview.title;
  }, [preview]);

  useEffect(() => {
    if (!preview?.documents.length) return;
    if (preview.documents.some((document) => document.id === activeDocumentId)) return;
    setActiveDocumentId(preview.initialDocumentId || preview.documents[0]?.id || "");
  }, [activeDocumentId, preview]);

  const activeDocument =
    preview?.documents.find((document) => document.id === activeDocumentId) ??
    preview?.documents[0] ??
    null;

  const handlePrint = () => {
    const frameWindow = iframeRef.current?.contentWindow;
    if (!frameWindow) {
      setError("The preview is still loading. Try Print again in a moment.");
      return;
    }
    frameWindow.focus();
    frameWindow.print();
  };

  return (
    <section className={styles.exportPreviewShell}>
      <div className={styles.exportPreviewHeader}>
        <div>
          <div className={styles.exportPreviewTitle}>
            {preview?.title ?? "Plan Export Preview"}
          </div>
          <div className={styles.exportPreviewNote}>
            Review the print-ready plan here, then click Print and choose Save as PDF to select a
            location on the computer.
          </div>
        </div>

        <div className={styles.exportPreviewToolbar}>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={handlePrint}
            disabled={loading || !activeDocument}
          >
            Print
          </button>
        </div>
      </div>

      {preview && preview.documents.length > 1 ? (
        <div className={styles.exportPreviewDocStrip}>
          {preview.documents.map((document) => (
            <button
              key={document.id}
              type="button"
              className={`${styles.exportPreviewDocButton} ${
                document.id === activeDocument?.id ? styles.exportPreviewDocButtonActive : ""
              }`}
              onClick={() => setActiveDocumentId(document.id)}
            >
              {document.title}
            </button>
          ))}
        </div>
      ) : null}

      {loading ? (
        <article className={styles.emptyStateCard}>
          <div className={styles.emptyStateTitle}>Loading export preview</div>
          <div className={styles.emptyStateCopy}>
            Building the printable preview window. This usually only takes a moment.
          </div>
        </article>
      ) : error ? (
        <article className={styles.emptyStateCard}>
          <div className={styles.emptyStateTitle}>Export preview unavailable</div>
          <div className={styles.emptyStateCopy}>{error}</div>
        </article>
      ) : activeDocument ? (
        <div className={styles.exportPreviewFrameWrap}>
          <iframe
            ref={iframeRef}
            title={activeDocument.title}
            srcDoc={activeDocument.html}
            className={styles.exportPreviewFrame}
          />
        </div>
      ) : (
        <article className={styles.emptyStateCard}>
          <div className={styles.emptyStateTitle}>No export document available</div>
          <div className={styles.emptyStateCopy}>
            The planner did not generate a printable document for this preview session.
          </div>
        </article>
      )}
    </section>
  );
}

export function DayByDayPlanPage() {
  const plannerReference = usePlannerStore((state) => state.plannerReference);
  const plannerProjection = usePlannerStore((state) => state.plannerProjection);
  const plannerResult = usePlannerStore((state) => state.plannerResult);
  const guildSummary = usePlannerStore((state) => state.guildSummary);
  const guildRosters = usePlannerStore((state) => state.guildRosters);
  const opsDefinitions = usePlannerStore((state) => state.opsDefinitions);
  const opsAnalysis = usePlannerStore((state) => state.opsAnalysis);
  const plannerSettings = usePlannerStore((state) => state.plannerSettings);
  const primaryAllyCode = usePlannerStore((state) => state.primaryAllyCode);
  const selectedAlgorithm = usePlannerStore((state) => state.selectedAlgorithm);
  const setPlanetHold = usePlannerStore((state) => state.setPlanetHold);
  const setPlanetHoldDays = usePlannerStore((state) => state.setPlanetHoldDays);
  const selectedChain = usePlannerStore((state) => state.selectedChain);
  const selectedOperationsDay = usePlannerStore((state) => state.selectedOperationsDay);
  const selectedOperationsPlanetId = usePlannerStore(
    (state) => state.selectedOperationsPlanetId,
  );
  const selectedGuideMember = usePlannerStore((state) => state.selectedGuideMember);
  const selectedGuideMission = usePlannerStore((state) => state.selectedGuideMission);
  const expandedGuidePlanets = usePlannerStore((state) => state.expandedGuidePlanets);
  const guideData = usePlannerStore((state) => state.guideData);
  const guideEditorDifficulty = usePlannerStore((state) => state.guideEditorDifficulty);
  const selectedRosterMemberId = usePlannerStore((state) => state.selectedRosterMemberId);
  const rosterSearch = usePlannerStore((state) => state.rosterSearch);
  const rosterFilter = usePlannerStore((state) => state.rosterFilter);
  const rosterSortKey = usePlannerStore((state) => state.rosterSortKey);
  const optimizerAcknowledged = usePlannerStore((state) => state.optimizerAcknowledged);
  const optimizerDirty = usePlannerStore((state) => state.optimizerDirty);
  const isRunningOptimization = usePlannerStore((state) => state.isRunningOptimization);
  const optimizationProgress = usePlannerStore((state) => state.optimizationProgress);
  const optimizerStatusMessage = usePlannerStore(
    (state) => state.optimizerStatusMessage,
  );
  const importPlannerSnapshot = usePlannerStore((state) => state.importPlannerSnapshot);
  const setSelectedAlgorithm = usePlannerStore((state) => state.setSelectedAlgorithm);
  const acknowledgeOptimizerWarning = usePlannerStore((state) => state.acknowledgeOptimizerWarning);
  const runPlannerOptimization = usePlannerStore((state) => state.runPlannerOptimization);

  const [exportMode, setExportMode] = useState<PlanExportMode>("all");
  const [detailMode, setDetailMode] = useState<PlanExportDetailMode>("detailed");
  const [transferStatus, setTransferStatus] = useState("");
  const snapshotInputRef = useRef<HTMLInputElement | null>(null);

  const algorithms = plannerReference?.algorithms ?? dayPlanAlgorithms;
  const summary = plannerResult?.summary ?? plannerProjection?.summary;
  const selectedAlgorithmLabel =
    algorithms.find((algorithm) => algorithm.id === selectedAlgorithm)?.label ??
    selectedAlgorithm;
  const holdPlanetOptions = (plannerReference?.planets ?? [])
    .slice()
    .sort((left, right) => left.phase - right.phase || left.name.localeCompare(right.name));
  const selectedHoldPlanet = holdPlanetOptions.find(
    (planet) => planet.id === plannerSettings.planetHold?.planetId,
  );
  const holdMaxDays = selectedHoldPlanet ? plannerMaxHoldDays(selectedHoldPlanet) : 0;
  const holdDaysValue = plannerSettings.planetHold
    ? Math.min(plannerSettings.planetHold.days, Math.max(1, holdMaxDays))
    : 0;
  const dayPlanStatusMessage = (() => {
    if (isRunningOptimization) {
      return optimizerStatusMessage || `Running ${selectedAlgorithmLabel || "optimization"}...`;
    }
    if (optimizerStatusMessage.startsWith("Optimization failed:")) {
      return optimizerStatusMessage;
    }
    if (!optimizerAcknowledged) {
      return "Review and confirm the optimizer warning above before choosing an algorithm.";
    }
    if (!selectedAlgorithm) {
      return "Choose an algorithm to enable the optimizer.";
    }
    if (optimizerDirty) {
      return "Planner inputs changed after the last run. Select an algorithm and rerun to refresh the plan.";
    }
    if (plannerResult) {
      return (
        optimizerStatusMessage ||
        "Select an algorithm and click Run to refresh or compare the current saved plan."
      );
    }
    return "Select an algorithm and click Run to generate the optimal TB plan.";
  })();

  const handleExportPlan = async () => {
    if (!plannerResult) {
      setTransferStatus("Run the optimizer first to export a day-by-day plan PDF.");
      return;
    }
    setTransferStatus("Preparing the print preview...");
    try {
      const preview = buildPlanExportPreview({
        plannerResult,
        guildSummary,
        guildRosters,
        plannerReference,
        opsDefinitions,
        opsAnalysis,
        plannerSettings,
        mode: exportMode,
        detailMode,
      });
      await plannerApi.openExportPreview(
        preview.title,
        preview.initialDocumentId,
        preview.documents,
      );
      setTransferStatus(
        exportMode === "separate"
          ? "Opened the day-by-day preview window. Use Print on each day tab to choose Save as PDF and a destination."
          : "Opened the full-plan preview window. Use Print and choose Save as PDF to pick a save location.",
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setTransferStatus(`Plan export failed: ${message}`);
    }
  };

  const handleSaveSnapshot = () => {
    if (!plannerResult) {
      setTransferStatus("Run the optimizer first to save a full planning snapshot.");
      return;
    }
    const payload = buildPlannerSnapshotPayload({
      primaryAllyCode,
      plannerSettings,
      selectedAlgorithm,
      optimizerAcknowledged,
      selectedChain,
      selectedOperationsDay,
      selectedOperationsPlanetId,
      selectedGuideMember,
      selectedGuideMission,
      expandedGuidePlanets,
      guideData,
      guideEditorDifficulty,
      selectedRosterMemberId,
      rosterSearch,
      rosterFilter,
      rosterSortKey,
      guildSummary,
      guildRosters,
      opsDefinitions,
      opsAnalysis,
      plannerProjection,
      plannerResult,
    });
    const stamp = new Date().toISOString().replace(/:/g, "-").replace(/\..+$/, "");
    triggerJsonDownload(`rote-plan-snapshot-${stamp}.json`, payload);
    setTransferStatus(
      "Planning snapshot saved. This file can restore the exact guild, rosters, plan, and operations later.",
    );
  };

  const handleLoadSnapshot = async (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    setTransferStatus(`Loading snapshot from ${file.name}...`);
    try {
      const payload = JSON.parse(await file.text());
      await importPlannerSnapshot(payload);
      setTransferStatus(
        `Snapshot loaded - restored guild, rosters, day plan, and operations from ${file.name}.`,
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setTransferStatus(`Failed to load planning snapshot: ${message}`);
    } finally {
      input.value = "";
    }
  };

  return (
    <section className={styles.panel}>
      <div
        className={`${styles.panelCard} ${styles.warningCard} ${
          optimizerAcknowledged ? styles.warningCardConfirmed : ""
        }`}
      >
        <div className={styles.warningHeader}>
          <div>
            <div className={styles.cardTitle}>Optimizer Warning</div>
            <div className={styles.warningCopy}>
              These optimization passes can take a long time once roster scans and operations assignments are folded into the search.
            </div>
            <div className={styles.warningNote}>
              Greedy is the fast preview option. PSO and GA are the serious planning passes. Adam and All Algorithms are long unattended runs.
            </div>
          </div>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={acknowledgeOptimizerWarning}
            disabled={optimizerAcknowledged}
          >
            {optimizerAcknowledged ? "Warning Confirmed" : "I Understand"}
          </button>
        </div>

        <div className={styles.algorithmGrid}>
          {algorithms.map((algorithm) => (
            <article
              key={algorithm.id}
              className={`${styles.algorithmCard} ${
                !optimizerAcknowledged ? styles.algorithmCardLocked : ""
              }`}
            >
              <div className={styles.algorithmTitle}>{algorithm.label}</div>
              <div className={styles.algorithmDescription}>{algorithm.description}</div>
              <div className={styles.badgeRow}>
                <span className={`${styles.badge} ${styles.badgeQuality}`}>{algorithm.quality}</span>
                <span className={`${styles.badge} ${styles.badgeComplexity}`}>{algorithm.complexity}</span>
                <span className={`${styles.badge} ${styles.badgeRuntime}`}>{algorithm.runtime}</span>
              </div>
            </article>
          ))}
        </div>
      </div>

      <div className={styles.metricGrid}>
        {[
          { label: "Total Est. Stars", value: `${summary?.estimatedStars ?? 0}`, tone: "gold" as const },
          { label: "Max Possible", value: `${summary?.maxPossibleStars ?? 0}`, tone: "neutral" as const },
          { label: "Bonus Planets", value: `${summary?.bonusActiveCount ?? 0} Active`, tone: "purple" as const },
          { label: "Ops Filled", value: `${summary?.opsFilled ?? 0}`, tone: "green" as const },
        ].map((metric) => (
          <article key={metric.label} className={styles.metricCard}>
            <div className={styles.metricLabel}>{metric.label}</div>
            <div className={`${styles.metricValue} ${toneClassName(metric.tone)}`}>{metric.value}</div>
          </article>
        ))}
      </div>

      <div className={styles.exportToolbar}>
        <div className={styles.exportToolbarGroup}>
          <label className={styles.inlineField}>
            <span className={styles.label}>Leave Planet Open</span>
            <select
              className={styles.selectControl}
              value={plannerSettings.planetHold?.planetId ?? ""}
              onChange={(event) => {
                const planetId = event.currentTarget.value.trim();
                if (!planetId) {
                  setPlanetHold(null);
                  return;
                }
                const planet = holdPlanetOptions.find((entry) => entry.id === planetId);
                const maxDays = planet ? plannerMaxHoldDays(planet) : 1;
                setPlanetHold(planetId);
                setPlanetHoldDays(maxDays);
              }}
              disabled={isRunningOptimization}
            >
              <option value="">No forced hold</option>
              {holdPlanetOptions.map((planet) => (
                <option key={planet.id} value={planet.id}>
                  {planet.name} (P{planet.phase})
                </option>
              ))}
            </select>
          </label>
          <label className={styles.inlineField}>
            <span className={styles.label}>Hold Days</span>
            <select
              className={styles.selectControl}
              value={plannerSettings.planetHold ? String(holdDaysValue) : ""}
              onChange={(event) => setPlanetHoldDays(Number(event.currentTarget.value) || 1)}
              disabled={!plannerSettings.planetHold || isRunningOptimization}
            >
              {!plannerSettings.planetHold ? <option value="">Select a planet first</option> : null}
              {Array.from({ length: holdMaxDays }, (_, index) => index + 1).map((days) => (
                <option key={days} value={days}>
                  {days} day{days === 1 ? "" : "s"}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className={styles.exportToolbarGroup}>
          <div className={styles.noteText}>
            {selectedHoldPlanet
              ? `${selectedHoldPlanet.name} can be held open for up to ${holdMaxDays} day${
                  holdMaxDays === 1 ? "" : "s"
                }. The optimizer will keep it below roughly half of 1-star until the hold is satisfied, then chase the best star outcome around that constraint.`
              : "Optional hold rule: keep one planet open for extra special-mission attempts while the optimizer still maximizes stars everywhere else."}
          </div>
        </div>
      </div>

      <div className={styles.controlsGrid}>
        <select
          className={styles.selectControl}
          value={selectedAlgorithm}
          onChange={(event) => setSelectedAlgorithm(event.currentTarget.value)}
          disabled={!optimizerAcknowledged || isRunningOptimization}
        >
          <option value="">Choose an optimization algorithm...</option>
          {algorithms.map((algorithm) => (
            <option key={algorithm.id} value={algorithm.id}>
              {algorithm.label}
            </option>
          ))}
        </select>
        <div className={styles.progressButtonWrap}>
          <div
            className={styles.progressFillBg}
            style={{ width: `${Math.max(0, Math.min(100, optimizationProgress))}%` }}
          />
          <button
            type="button"
            className={`${styles.primaryButton} ${styles.progressActionButton}`}
            onClick={() => void runPlannerOptimization()}
            disabled={!optimizerAcknowledged || !selectedAlgorithm || isRunningOptimization}
          >
            {isRunningOptimization
              ? `Running ${selectedAlgorithmLabel || "optimization"}...`
              : "Run Optimization"}
          </button>
        </div>
      </div>

      <div className={styles.statusLine}>{dayPlanStatusMessage}</div>

      <div className={styles.exportToolbar}>
        <div className={styles.exportToolbarGroup}>
          <label className={styles.inlineField}>
            <span className={styles.label}>Export mode</span>
            <select
              className={styles.selectControl}
              value={exportMode}
              onChange={(event) => setExportMode(event.currentTarget.value as PlanExportMode)}
              disabled={isRunningOptimization}
            >
              <option value="all">One preview with all days</option>
              <option value="separate">Separate print views by day</option>
            </select>
          </label>
          <label className={styles.inlineField}>
            <span className={styles.label}>Layout</span>
            <select
              className={styles.selectControl}
              value={detailMode}
              onChange={(event) =>
                setDetailMode(event.currentTarget.value as PlanExportDetailMode)
              }
              disabled={isRunningOptimization}
            >
              <option value="detailed">Detailed operations layout</option>
              <option value="condensed">Condensed operations layout</option>
            </select>
          </label>
        </div>

        <div className={styles.exportToolbarGroup}>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => void handleExportPlan()}
            disabled={!plannerResult || isRunningOptimization}
          >
            Preview / Print Plan
          </button>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={handleSaveSnapshot}
            disabled={!plannerResult || isRunningOptimization}
          >
            Save Plan Snapshot
          </button>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={() => snapshotInputRef.current?.click()}
            disabled={isRunningOptimization}
          >
            Load Plan Snapshot
          </button>
          <input
            ref={snapshotInputRef}
            type="file"
            accept=".json,application/json"
            className={styles.hiddenInput}
            onChange={(event) => void handleLoadSnapshot(event)}
          />
        </div>
      </div>

      {transferStatus ? <div className={styles.exportStatusLine}>{transferStatus}</div> : null}

      {plannerResult && plannerResult.algorithmScores.length > 1 ? (
        <div className={styles.algorithmScoreGrid}>
          {plannerResult.algorithmScores.map((score) => (
            <article
              key={score.algorithm}
              className={`${styles.algorithmScoreCard} ${
                score.algorithm === plannerResult.bestAlgorithm
                  ? styles.algorithmScoreCardBest
                  : ""
              }`}
            >
              <div className={styles.algorithmScoreLabel}>{score.label}</div>
              <div className={styles.algorithmScoreValue}>{score.score} stars</div>
            </article>
          ))}
        </div>
      ) : null}

      {(plannerResult?.dayPlan ?? []).map((day) => {
        const chainEntries = [
          day.chains.ds,
          day.chains.mx,
          day.chains.ls,
        ].filter(Boolean);
        return (
          <article key={day.day} className={styles.dayBlock}>
            <div className={styles.dayBlockHeader}>
              <div className={styles.dayTitle}>Day {day.day}</div>
              <div className={styles.dayMeta}>
                <span>GP: {formatMillions(day.gpAvail)} avail / {formatMillions(day.gpUsed)} used</span>
                <span>{day.starsDay} stars</span>
              </div>
            </div>
            <div className={styles.dayChainsGrid}>
              {chainEntries.map((entry) => (
                <div key={`${day.day}-${entry.key}-${entry.planetId ?? "done"}`} className={dayChainClassName(entry.align ?? "bonus")}>
                  <div className={styles.dayChainTitle}>{entry.key.toUpperCase()}</div>
                  <div className={styles.dayChainPlanet}>{entry.planetName ?? "Complete"}</div>
                  <div className={styles.dayChainStars}>
                    {entry.status === "preload" ? "Preload" : `${entry.stars} stars`}
                  </div>
                  <div className={styles.dayChainAction}>
                    {entry.status === "preload" ? `Banked ${formatMillions(entry.banked)}` : `Projected total: ${formatMillions(entry.pts)}`}
                  </div>
                  <div className={styles.dayChainBreakdown}>
                    Mission {formatMillions(entry.missionPts)} | Ops {formatMillions(entry.opsPts)} | GP {formatMillions(entry.gpDeployed)}
                  </div>
                  <div className={styles.dayChainAdvance}>
                    {entry.status === "preload"
                      ? `Tomorrow est. ${formatMillions(entry.tomorrowEst)}`
                      : entry.stars >= 1
                        ? "Chain advances tomorrow"
                        : `${formatNumber(Math.max(0, entry.threshold1star - entry.pts))} to 1*`}
                  </div>
                </div>
              ))}
              {day.bonusPlanets.map((planet) => (
                <div key={`${day.day}-${planet.planetId}`} className={dayChainClassName("bonus")}>
                  <div className={styles.dayChainTitle}>Bonus</div>
                  <div className={styles.dayChainPlanet}>{planet.planetName}</div>
                  <div className={styles.dayChainStars}>{planet.stars} stars</div>
                  <div className={styles.dayChainAction}>Projected total: {formatMillions(planet.pts)}</div>
                  <div className={styles.dayChainBreakdown}>
                    Mission {formatMillions(planet.missionPts)} | Ops {formatMillions(planet.opsPts)} | GP {formatMillions(planet.gpDeployed)}
                  </div>
                  <div className={styles.dayChainAdvance}>Unlocked Day {planet.activeFromDay}</div>
                </div>
              ))}
            </div>
            <div className={styles.notesBlock}>
              <div className={styles.noteLine}>{`Operations: ${formatMillions(day.opsPoints)} projected from daily assignments.`}</div>
              {day.notices.map((note) => (
                <div key={`${day.day}-${note}`} className={`${styles.noteLine} ${styles.noteLineBonus}`}>
                  {note}
                </div>
              ))}
            </div>
          </article>
        );
      })}
    </section>
  );
}

export function OperationsPage() {
  const plannerResult = usePlannerStore((state) => state.plannerResult);
  const opsAnalysis = usePlannerStore((state) => state.opsAnalysis);
  const opsDefinitions = usePlannerStore((state) => state.opsDefinitions);
  const guildSummary = usePlannerStore((state) => state.guildSummary);
  const guildRosters = usePlannerStore((state) => state.guildRosters);
  const selectedOperationsDay = usePlannerStore((state) => state.selectedOperationsDay);
  const selectedOperationsPlanetId = usePlannerStore((state) => state.selectedOperationsPlanetId);
  const isLoadingOps = usePlannerStore((state) => state.isLoadingOps);
  const setSelectedOperationsDay = usePlannerStore((state) => state.setSelectedOperationsDay);
  const setSelectedOperationsPlanetId = usePlannerStore((state) => state.setSelectedOperationsPlanetId);
  const loadOpsDefinitions = usePlannerStore((state) => state.loadOpsDefinitions);
  const analyzePlatoons = usePlannerStore((state) => state.analyzePlatoons);

  const liveMetrics = buildOperationsMetrics(opsAnalysis, guildRosters, opsDefinitions);
  const plannerSummary = plannerResult?.summary;
  const metrics = plannerSummary
    ? [
        { label: "Projected Platoons", value: `${plannerSummary.opsFilled} / ${plannerSummary.opsTotal}`, tone: "green" as const },
        { label: "Projected Ops Points", value: formatMillions(plannerSummary.opsPoints), tone: "gold" as const },
        { label: "Definitions Loaded", value: opsDefinitions ? "Bundled Gamedata" : "Not loaded", tone: "neutral" as const },
        { label: "Roster Coverage", value: plannerSummary.rosterCoverage, tone: "purple" as const },
      ]
    : liveMetrics;
  const plannerStage = buildPlannerOpsStage(
    plannerResult,
    selectedOperationsDay,
    selectedOperationsPlanetId,
    opsDefinitions,
    guildSummary,
  );
  const fallbackStage = buildOperationsStage(selectedOperationsPlanetId, opsAnalysis);
  const selectedStage = plannerStage ?? fallbackStage;
  const planetIds = plannerResult
    ? plannerDayPlanetIds(plannerResult, selectedOperationsDay)
    : buildPlanetOptions(opsAnalysis);

  return (
    <section className={styles.panel}>
      <div className={styles.metricGrid}>
        {metrics.map((metric) => (
          <article key={metric.label} className={styles.metricCard}>
            <div className={styles.metricLabel}>{metric.label}</div>
            <div className={`${styles.metricValue} ${toneClassName(metric.tone)}`}>{metric.value}</div>
          </article>
        ))}
      </div>

      <div className={styles.panelCard}>
        <div className={styles.cardTitle}>Operations Planner</div>
        <div className={styles.cardSubtitle}>
          Platoons are driven by the Rust backend and reflect the same daily assignments used by the optimizer when a plan is available.
        </div>
        <div className={styles.actionRow}>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={() => void loadOpsDefinitions()}
            disabled={isLoadingOps}
          >
            Load Definitions
          </button>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => void analyzePlatoons()}
            disabled={isLoadingOps}
          >
            Refresh Analysis
          </button>
        </div>
      </div>

      <div className={styles.opsLayout}>
        <div className={styles.opsSidebar}>
          {(plannerResult?.dayPlan ?? []).map((day) => (
            <button
              key={day.day}
              type="button"
              className={`${styles.dayPickerCard} ${
                day.day === selectedOperationsDay ? styles.dayPickerCardActive : ""
              }`}
              onClick={() => setSelectedOperationsDay(day.day)}
            >
              <div className={styles.dayPickerHead}>
                <div className={styles.dayPickerTitle}>Day {day.day}</div>
                <div className={styles.dayPickerPoints}>{formatMillions(day.opsPoints)}</div>
              </div>
              <div className={styles.dayPickerKicker}>
                {planetIds.length} active planet{planetIds.length === 1 ? "" : "s"}
              </div>
              <div className={styles.dayPickerSub}>{day.notices[0] ?? `${day.starsDay} stars planned`}</div>
            </button>
          ))}
        </div>

        <div className={styles.opsMainPane}>
          <div className={styles.planetStrip}>
            {planetIds.map((planetId) => (
              <button
                key={planetId}
                type="button"
                className={`${styles.planetPill} ${
                  planetId === selectedOperationsPlanetId ? styles.planetPillActive : ""
                }`}
                onClick={() => setSelectedOperationsPlanetId(planetId)}
              >
                <div className={styles.planetPillName}>{planetId}</div>
                <div className={styles.planetPillMeta}>
                  {plannerResult ? "Optimizer-backed" : "Live analysis"}
                </div>
              </button>
            ))}
          </div>

          {selectedStage ? (
            <article className={styles.stageCard}>
              <div className={styles.stageHead}>
                <div>
                  <div className={styles.stageTitle}>{selectedStage.stageTitle}</div>
                  <div className={styles.stageSubtitle}>{selectedStage.stageSubtitle}</div>
                </div>
                <div className={styles.stageMeta}>{selectedStage.stageMeta}</div>
              </div>

              <div className={styles.platoonGrid}>
                {selectedStage.platoons.map((platoon) => (
                  <article key={platoon.id} className={operationsStatusClassName(platoon.status)}>
                    <div className={styles.platoonHead}>
                      <div>
                        <div className={styles.platoonTitle}>Platoon {platoon.id}</div>
                        <div className={styles.platoonSub}>{platoon.filled}</div>
                      </div>
                      <div className={styles.platoonBadge}>{platoon.label}</div>
                    </div>

                    <div className={styles.slotList}>
                      {platoon.slots.map((slot) => (
                        <div key={`${platoon.id}-${slot.name}-${slot.assignee}`} className={styles.slotCard}>
                          <div className={styles.slotName}>{slot.name}</div>
                          <div
                            className={`${styles.slotAssignee} ${
                              slot.unassigned ? styles.slotAssigneeUnassigned : ""
                            }`}
                          >
                            {slot.assignee}
                          </div>
                          <div className={styles.slotMeta}>{slot.meta}</div>
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            </article>
          ) : (
            <article className={styles.stageCard}>
              <div className={styles.stageTitle}>No operations data yet</div>
              <div className={styles.stageSubtitle}>Run a roster scan and optimization to populate the live operations plan.</div>
            </article>
          )}
        </div>
      </div>
    </section>
  );
}

export function GuidesPageLegacy() {
  const plannerReference = usePlannerStore((state) => state.plannerReference);
  const guildSummary = usePlannerStore((state) => state.guildSummary);
  const guildRosters = usePlannerStore((state) => state.guildRosters);
  const guideTbOmicrons = usePlannerStore((state) => state.guideTbOmicrons);
  const selectedGuideMember = usePlannerStore((state) => state.selectedGuideMember);
  const selectedGuideMission = usePlannerStore((state) => state.selectedGuideMission);
  const expandedGuidePlanets = usePlannerStore((state) => state.expandedGuidePlanets);
  const guideEditorOpen = usePlannerStore((state) => state.guideEditorOpen);
  const guideEditorDifficulty = usePlannerStore((state) => state.guideEditorDifficulty);
  const setSelectedGuideMember = usePlannerStore((state) => state.setSelectedGuideMember);
  const setSelectedGuideMission = usePlannerStore((state) => state.setSelectedGuideMission);
  const toggleGuidePlanet = usePlannerStore((state) => state.toggleGuidePlanet);
  const openGuideEditor = usePlannerStore((state) => state.openGuideEditor);
  const closeGuideEditor = usePlannerStore((state) => state.closeGuideEditor);
  const setGuideEditorDifficulty = usePlannerStore((state) => state.setGuideEditorDifficulty);

  const scannedMembers = buildRosterMembers(guildSummary, guildRosters);
  const phaseGroups = buildGuidePhasePlanets(plannerReference?.planets ?? []);
  const allPlanets = phaseGroups.flatMap((group) => group.planets);
  const fallbackPlanet = allPlanets[0] ?? null;
  const activePlanet =
    allPlanets.find((planet) => planet.id === selectedGuideMission.planetId) ?? fallbackPlanet;
  const activeMission =
    activePlanet?.missions.find((mission) => mission.id === selectedGuideMission.missionId) ??
    activePlanet?.missions[0] ??
    null;
  const selectedMemberLabel =
    scannedMembers.find((member) => member.id === selectedGuideMember)?.label ??
    "No scanned member selected";
  const guideOmicronCount = Object.values(guideTbOmicrons).reduce(
    (total, skills) => total + skills.length,
    0,
  );
  const isFleetMission = activeMission?.missionType === "fleet";
  const modalSlots = isFleetMission
    ? [
        "Starting Ship 1",
        "Starting Ship 2",
        "Starting Ship 3",
        "Reinforcement 1",
        "Reinforcement 2",
        "Reinforcement 3",
        "Reinforcement 4",
      ]
    : ["Member 1", "Member 2", "Member 3", "Member 4"];

  return (
    <section className={styles.panel}>
      <div className={styles.guideTopBar}>
        <div className={styles.actionRow}>
          <label className={styles.inlineField}>
            <span className={styles.label}>Viewing for:</span>
            <select
              className={styles.selectControl}
              value={selectedGuideMember}
              onChange={(event) => setSelectedGuideMember(event.currentTarget.value)}
            >
              {scannedMembers.length ? null : (
                <option value="">-- Scan rosters first --</option>
              )}
              {scannedMembers.map((member) => (
                <option key={member.id} value={member.id}>
                  {member.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className={styles.actionRow}>
          <button type="button" className={styles.secondaryButton} disabled>
            Save Guide
          </button>
          <button type="button" className={styles.secondaryButton} disabled>
            Load Guide
          </button>
        </div>
      </div>

      <div className={styles.guideLayout}>
        <aside className={styles.guideSidebar}>
          {phaseGroups.map((group) => (
            <Fragment key={group.phase}>
              <div className={styles.phaseHeader}>Phase {group.phase}</div>
              {group.planets.map((planet) => {
                const isExpanded = expandedGuidePlanets.includes(planet.id);
                return (
                  <div key={planet.id}>
                    <button
                      type="button"
                      className={`${styles.guidePlanetHeader} ${
                        isExpanded ? styles.guidePlanetHeaderActive : ""
                      }`}
                      onClick={() => toggleGuidePlanet(planet.id)}
                    >
                      <span
                        className={`${styles.guidePlanetName} ${
                          isGuideBonusPlanet(planet) ? styles.guidePlanetNameBonus : ""
                        }`}
                      >
                        {isGuideBonusPlanet(planet) ? "\u2022 " : ""}
                        {planet.name}
                      </span>
                      <span className={styles.guidePlanetCount} />
                    </button>

                    {isExpanded ? (
                      <div>
                        {planet.missions.map((mission) => {
                          const active =
                            activePlanet?.id === planet.id && activeMission?.id === mission.id;
                          return (
                            <button
                              key={mission.id}
                              type="button"
                              className={`${styles.guideMissionItem} ${
                                active ? styles.guideMissionItemActive : ""
                              }`}
                              onClick={() => setSelectedGuideMission(planet.id, mission.id)}
                            >
                              <span className={styles.missionTypeBadge}>
                                {guideMissionTypeIcon(mission)}
                              </span>
                              <span>{mission.label}</span>
                              <span className={styles.guidePlanetCount} />
                              <span
                                className={styles.guideAddButton}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setSelectedGuideMission(planet.id, mission.id);
                                  openGuideEditor("auto");
                                }}
                                title="Add squad"
                              >
                                +
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </Fragment>
          ))}
        </aside>

        <div className={styles.missionPanel}>
          {activePlanet && activeMission ? (
            <>
              <div className={styles.missionPanelHero}>
                <div>
                  <div className={styles.missionPanelTitle}>
                    {activePlanet.name} - {activeMission.label}
                  </div>
                  <div className={styles.missionPanelMeta}>
                    {guideMissionTypeLabel(activeMission)} |{" "}
                    {guideMissionRequirement(activePlanet, activeMission)}
                  </div>
                  <div className={styles.missionPanelCopy}>{activeMission.unitsText}</div>
                  {activeMission.rewardText ? (
                    <div className={styles.noteText}>Reward: {activeMission.rewardText}</div>
                  ) : null}
                  {activeMission.note ? (
                    <div className={styles.noteText}>{activeMission.note}</div>
                  ) : null}
                </div>
                <button
                  type="button"
                  className={styles.primaryButton}
                  onClick={() => openGuideEditor("auto")}
                >
                  Add Squad
                </button>
              </div>

              <article className={styles.emptyStateCard}>
                <div className={styles.emptyStateTitle}>
                  No guide squads saved for this mission yet.
                </div>
                <div className={styles.emptyStateCopy}>
                  This rebuild now uses the legacy planet and mission structure from the
                  original planner. Add Squad opens the corrected layout for this mission,
                  and guide persistence is the next backend slice to wire in.
                </div>
                <div className={styles.noteText}>Viewing for: {selectedMemberLabel}</div>
              </article>
            </>
          ) : (
            <article className={styles.emptyStateCard}>
              <div className={styles.emptyStateTitle}>No guide mission selected</div>
              <div className={styles.emptyStateCopy}>
                Choose a planet mission from the left to review its requirements and build
                squad guides.
              </div>
            </article>
          )}
        </div>
      </div>

      {guideEditorOpen && activePlanet && activeMission ? (
        <div className={styles.modalBackdrop}>
          <div className={styles.modalCard}>
            <div className={styles.modalHeader}>
              <div>
                <div className={styles.modalTitle}>Add Squad</div>
                <div className={styles.noteText}>
                  {activePlanet.name} - {activeMission.label} |{" "}
                  {guideMissionRequirement(activePlanet, activeMission)}
                </div>
              </div>
              <button type="button" className={styles.closeButton} onClick={closeGuideEditor}>
                X
              </button>
            </div>

            <div className={styles.modalField}>
              <div className={styles.label}>Difficulty</div>
              <div className={styles.difficultyRow}>
                {(["auto", "easy", "medium", "hard"] as GuideDifficulty[]).map((difficulty) => (
                  <button
                    key={difficulty}
                    type="button"
                    className={`${styles.difficultyButton} ${
                      guideEditorDifficulty === difficulty
                        ? styles.difficultyButtonActive
                        : ""
                    }`}
                    onClick={() => setGuideEditorDifficulty(difficulty)}
                  >
                    {difficulty}
                  </button>
                ))}
              </div>
            </div>

            <label className={styles.modalField}>
              <span className={styles.label}>
                {isFleetMission ? "Capital Ship" : "Squad Leader"}
              </span>
              <input
                className={styles.modalInput}
                placeholder={
                  isFleetMission ? "e.g. Executor" : "e.g. Sith Eternal Emperor"
                }
              />
            </label>

            {isFleetMission ? (
              <>
                <div className={styles.slotGroupHeading}>Starting Ships (required)</div>
                <div className={styles.modalSlotsGrid}>
                  {modalSlots.slice(0, 3).map((label) => (
                    <label key={label} className={styles.modalField}>
                      <span className={styles.label}>{label}</span>
                      <input className={styles.modalInput} placeholder={label} />
                    </label>
                  ))}
                </div>
                <div className={styles.slotGroupHeading}>Reinforcements (optional)</div>
                <div className={styles.modalSlotsGrid}>
                  {modalSlots.slice(3).map((label) => (
                    <label key={label} className={styles.modalField}>
                      <span className={styles.label}>{label}</span>
                      <input className={styles.modalInput} placeholder={label} />
                    </label>
                  ))}
                </div>
              </>
            ) : (
              <div className={styles.modalSlotsGrid}>
                {modalSlots.map((label) => (
                  <label key={label} className={styles.modalField}>
                    <span className={styles.label}>{label}</span>
                    <input className={styles.modalInput} placeholder={label} />
                  </label>
                ))}
              </div>
            )}

            <div className={styles.modalField}>
              <div className={styles.label}>Required Territory Battle Omicrons</div>
              <div className={styles.fieldHint}>
                {isFleetMission
                  ? "Fleet missions do not use Territory Battle omicron requirements."
                  : guideOmicronCount > 0
                    ? `${guideOmicronCount} Territory Battle omicron abilities are loaded from scanned roster data.`
                    : "Run Scan Rosters to load Territory Battle omicron data for this guide editor."}
              </div>
            </div>

            <label className={styles.modalField}>
              <span className={styles.label}>Notes / Strategy</span>
              <textarea
                className={styles.modalInput}
                placeholder="Strategy notes, tips, mod recommendations..."
                rows={4}
              />
            </label>

            <label className={styles.modalField}>
              <span className={styles.label}>YouTube URL</span>
              <input
                className={styles.modalInput}
                type="url"
                placeholder="https://youtube.com/watch?v=..."
              />
            </label>

            <div className={styles.modalFooter}>
              <div className={styles.modalFooterCopy}>
                Guide save/load behavior is not wired yet, but this editor now matches the
                legacy mission-specific layout.
              </div>
              <button type="button" className={styles.secondaryButton} onClick={closeGuideEditor}>
                Cancel
              </button>
              <button type="button" className={styles.primaryButton} disabled>
                Save Squad
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export function GuidesPage() {
  const plannerReference = usePlannerStore((state) => state.plannerReference);
  const guildSummary = usePlannerStore((state) => state.guildSummary);
  const guildRosters = usePlannerStore((state) => state.guildRosters);
  const guideTbOmicrons = usePlannerStore((state) => state.guideTbOmicrons);
  const guideUnitCatalog = usePlannerStore((state) => state.guideUnitCatalog);
  const guideData = usePlannerStore((state) => state.guideData);
  const selectedGuideMember = usePlannerStore((state) => state.selectedGuideMember);
  const selectedGuideMission = usePlannerStore((state) => state.selectedGuideMission);
  const expandedGuidePlanets = usePlannerStore((state) => state.expandedGuidePlanets);
  const guideEditorOpen = usePlannerStore((state) => state.guideEditorOpen);
  const guideEditorDifficulty = usePlannerStore((state) => state.guideEditorDifficulty);
  const setSelectedGuideMember = usePlannerStore((state) => state.setSelectedGuideMember);
  const setSelectedGuideMission = usePlannerStore((state) => state.setSelectedGuideMission);
  const toggleGuidePlanet = usePlannerStore((state) => state.toggleGuidePlanet);
  const saveGuideSquad = usePlannerStore((state) => state.saveGuideSquad);
  const copyGuideSquad = usePlannerStore((state) => state.copyGuideSquad);
  const moveGuideSquad = usePlannerStore((state) => state.moveGuideSquad);
  const deleteGuideSquad = usePlannerStore((state) => state.deleteGuideSquad);
  const importGuideData = usePlannerStore((state) => state.importGuideData);
  const openGuideEditor = usePlannerStore((state) => state.openGuideEditor);
  const closeGuideEditor = usePlannerStore((state) => state.closeGuideEditor);
  const setGuideEditorDifficulty = usePlannerStore((state) => state.setGuideEditorDifficulty);

  const [guideStatus, setGuideStatus] = useState("");
  const [editingSquadId, setEditingSquadId] = useState<string | null>(null);
  const [expandedSquads, setExpandedSquads] = useState<Record<string, boolean>>({});
  const [copyingSquadId, setCopyingSquadId] = useState<string | null>(null);
  const [copyTargetPlanetId, setCopyTargetPlanetId] = useState("");
  const [copyTargetMissionId, setCopyTargetMissionId] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const scannedMembers = buildRosterMembers(guildSummary, guildRosters);
  const phaseGroups = buildGuidePhasePlanets(plannerReference?.planets ?? []);
  const allPlanets = phaseGroups.flatMap((group) => group.planets);
  const fallbackPlanet = allPlanets[0] ?? null;
  const activePlanet =
    allPlanets.find((planet) => planet.id === selectedGuideMission.planetId) ?? fallbackPlanet;
  const activeMission =
    activePlanet?.missions.find((mission) => mission.id === selectedGuideMission.missionId) ??
    activePlanet?.missions[0] ??
    null;
  const activeMissionKey =
    activePlanet && activeMission ? guideMissionKey(activePlanet.id, activeMission.id) : "";
  const savedSquads = activeMissionKey
    ? [...(guideData.squads[activeMissionKey] ?? [])].sort(
        (left, right) => left.order - right.order || left.id.localeCompare(right.id),
      )
    : [];
  const selectedMemberLabel =
    scannedMembers.find((member) => member.id === selectedGuideMember)?.label ??
    "No scanned member selected";
  const selectedRoster = selectedGuideMember ? guildRosters[selectedGuideMember] ?? null : null;
  const scannedRosters = Object.values(guildRosters).filter(
    (roster): roster is SimplifiedRosterUnit[] => Array.isArray(roster),
  );
  const guideUnitLookup = buildGuideUnitLookup(guideUnitCatalog, guildRosters);
  const guideUnits = Array.from(guideUnitLookup.values()).sort((left, right) =>
    left.name.localeCompare(right.name),
  );
  const guideCharacterOptions = guideUnits
    .filter((unit) => unit.combatType === 1)
    .map((unit) => unit.name);
  const guideShipOptions = guideUnits
    .filter((unit) => unit.combatType === 2)
    .map((unit) => unit.name);
  const editingSquad = editingSquadId
    ? savedSquads.find((squad) => squad.id === editingSquadId) ?? null
    : null;
  const copyingSquad = copyingSquadId
    ? savedSquads.find((squad) => squad.id === copyingSquadId) ?? null
    : null;
  const guideMissionCounts = Object.fromEntries(
    Object.entries(guideData.squads).map(([missionKey, squads]) => [missionKey, squads.length]),
  ) as Record<string, number>;
  const guideSaveBlocked = Object.values(guideMissionCounts).some(
    (count) => count > GUIDE_MISSION_LIMIT,
  );
  const activeMissionCount = activeMissionKey ? guideMissionCounts[activeMissionKey] ?? 0 : 0;
  const activeMissionAtLimit = activeMissionCount >= GUIDE_MISSION_LIMIT;
  const activeMissionOverLimit = activeMissionCount > GUIDE_MISSION_LIMIT;
  const copyMissionOptions =
    activeMission && activePlanet
      ? allPlanets.flatMap((planet) =>
          planet.id === activePlanet.id
            ? []
            : planet.missions
                .filter(
                  (mission) =>
                    guideMissionCopyGroup(mission) === guideMissionCopyGroup(activeMission) &&
                    (guideMissionCounts[guideMissionKey(planet.id, mission.id)] ?? 0) <
                      GUIDE_MISSION_LIMIT,
                )
                .map((mission) => ({
                  planetId: planet.id,
                  planetName: planet.name,
                  missionId: mission.id,
                  missionLabel: mission.label,
                  squadCount: guideMissionCounts[guideMissionKey(planet.id, mission.id)] ?? 0,
                })),
        )
      : [];
  const copyTargetPlanets = Array.from(
    new Map(copyMissionOptions.map((mission) => [mission.planetId, mission.planetName])).entries(),
  ).map(([id, name]) => ({ id, name }));
  const copyTargetMissions = copyMissionOptions.filter(
    (mission) => mission.planetId === copyTargetPlanetId,
  );

  const handleCloseGuideEditor = () => {
    setEditingSquadId(null);
    closeGuideEditor();
  };

  const closeCopyGuideModal = () => {
    setCopyingSquadId(null);
    setCopyTargetPlanetId("");
    setCopyTargetMissionId("");
  };

  useEffect(() => {
    if (!copyingSquad) {
      return;
    }
    const firstPlanetId = copyTargetPlanets[0]?.id ?? "";
    const nextPlanetId =
      copyTargetPlanetId && copyTargetPlanets.some((planet) => planet.id === copyTargetPlanetId)
        ? copyTargetPlanetId
        : firstPlanetId;
    if (nextPlanetId !== copyTargetPlanetId) {
      setCopyTargetPlanetId(nextPlanetId);
      return;
    }
    const missionsForPlanet = copyMissionOptions.filter((mission) => mission.planetId === nextPlanetId);
    const nextMissionId =
      copyTargetMissionId && missionsForPlanet.some((mission) => mission.missionId === copyTargetMissionId)
        ? copyTargetMissionId
        : missionsForPlanet[0]?.missionId ?? "";
    if (nextMissionId !== copyTargetMissionId) {
      setCopyTargetMissionId(nextMissionId);
    }
  }, [
    copyMissionOptions,
    copyTargetMissionId,
    copyTargetPlanetId,
    copyTargetPlanets,
    copyingSquad,
  ]);

  const openNewGuideEditor = () => {
    if (!activePlanet || !activeMission) return;
    if (activeMissionAtLimit) {
      setGuideStatus(`This mission has reached the ${GUIDE_MISSION_LIMIT}-guide limit.`);
      return;
    }
    setEditingSquadId(null);
    setGuideEditorDifficulty("auto");
    openGuideEditor("auto");
  };

  const openGuideEditorForMission = (planetId: string, missionId: string) => {
    const missionKey = guideMissionKey(planetId, missionId);
    if ((guideMissionCounts[missionKey] ?? 0) >= GUIDE_MISSION_LIMIT) {
      setSelectedGuideMission(planetId, missionId);
      setGuideStatus(`This mission has reached the ${GUIDE_MISSION_LIMIT}-guide limit.`);
      return;
    }
    setSelectedGuideMission(planetId, missionId);
    setEditingSquadId(null);
    setGuideEditorDifficulty("auto");
    openGuideEditor("auto");
  };

  const openExistingGuideEditor = (squad: GuideSquad) => {
    const difficulty =
      squad.difficulty === "easy" || squad.difficulty === "medium" || squad.difficulty === "hard"
        ? squad.difficulty
        : "auto";
    setEditingSquadId(squad.id);
    setGuideEditorDifficulty(difficulty);
    openGuideEditor(difficulty);
    setExpandedSquads((current) => ({
      ...current,
      [squad.id]: true,
    }));
  };

  const openCopyGuideModal = (squad: GuideSquad) => {
    setCopyingSquadId(squad.id);
  };

  const exportGuideFile = () => {
    if (guideSaveBlocked) {
      setGuideStatus(
        `Guide save is disabled while any mission is over the ${GUIDE_MISSION_LIMIT}-guide limit.`,
      );
      return;
    }
    triggerJsonDownload("rote-guide.json", guideData);
    setGuideStatus(`Guide exported - ${Object.keys(guideData.squads).length} mission entries.`);
  };

  const handleGuideImport = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    if (!file) return;

    try {
      const parsed = JSON.parse(await file.text()) as Record<string, unknown>;
      await importGuideData(parsed);
      const squadsRecord =
        parsed.squads && typeof parsed.squads === "object"
          ? (parsed.squads as Record<string, unknown>)
          : {};
      setGuideStatus(`Guide loaded - ${Object.keys(squadsRecord).length} missions with squads.`);
    } catch (error) {
      setGuideStatus(
        `Guide load failed - ${error instanceof Error ? error.message : "Invalid guide file."}`,
      );
    } finally {
      event.currentTarget.value = "";
    }
  };

  const handleGuideEditorSave = (payload: GuideEditorSubmit) => {
    if (!activePlanet || !activeMission) return;
    const squadId =
      payload.id ?? `guide_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
    const result = saveGuideSquad(activePlanet.id, activeMission.id, {
      id: squadId,
      leader: payload.leader,
      leaderDefId: payload.leaderDefId,
      members: payload.members,
      memberDefIds: payload.memberDefIds,
      notes: payload.notes,
      videoUrl: payload.videoUrl,
      requiredTbOmicrons: payload.requiredTbOmicrons,
      difficulty: payload.difficulty,
    });
    if (!result.ok) {
      setGuideStatus(result.reason ?? "Guide squad could not be saved.");
      return;
    }
    setExpandedSquads((current) => ({
      ...current,
      [squadId]: true,
    }));
    setGuideStatus(payload.id ? "Guide squad updated." : "Guide squad saved for the selected mission.");
    handleCloseGuideEditor();
  };

  const handleCopyGuide = () => {
    if (!activePlanet || !activeMission || !copyingSquad || !copyTargetPlanetId || !copyTargetMissionId) {
      return;
    }
    const result = copyGuideSquad(
      activePlanet.id,
      activeMission.id,
      copyingSquad.id,
      copyTargetPlanetId,
      copyTargetMissionId,
    );
    if (!result.ok) {
      setGuideStatus(result.reason ?? "Guide squad could not be copied.");
      return;
    }
    const targetMission = copyTargetMissions.find(
      (mission) => mission.missionId === copyTargetMissionId,
    );
    setGuideStatus(
      `Guide copied to ${targetMission?.planetName ?? "target planet"} - ${targetMission?.missionLabel ?? "target mission"}.`,
    );
    closeCopyGuideModal();
  };

  return (
    <section className={styles.panel}>
      <div className={styles.guideTopBar}>
        <div className={styles.actionRow}>
          <label className={styles.inlineField}>
            <span className={styles.label}>Viewing for:</span>
            <select
              className={styles.selectControl}
              value={selectedGuideMember}
              onChange={(event) => setSelectedGuideMember(event.currentTarget.value)}
            >
              <option value="">
                {scannedMembers.length ? "-- Select member --" : "-- Scan rosters first --"}
              </option>
              {scannedMembers.map((member) => (
                <option key={member.id} value={member.id}>
                  {member.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className={styles.actionRow}>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={exportGuideFile}
            disabled={guideSaveBlocked}
            title={
              guideSaveBlocked
                ? `Reduce any mission over ${GUIDE_MISSION_LIMIT} guides before saving.`
                : "Save Guide"
            }
          >
            Save Guide
          </button>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={() => fileInputRef.current?.click()}
          >
            Load Guide
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,application/json"
            className={styles.hiddenInput}
            onChange={handleGuideImport}
          />
        </div>
      </div>

      {guideStatus ? <div className={styles.guideStatusLine}>{guideStatus}</div> : null}
      {guideSaveBlocked ? (
        <div className={styles.guideLimitNotice}>
          Guide save is disabled while any mission is over the {GUIDE_MISSION_LIMIT}-guide limit.
        </div>
      ) : null}

      <div className={styles.guideLayout}>
        <aside className={styles.guideSidebar}>
          {phaseGroups.map((group) => (
            <Fragment key={group.phase}>
              <div className={styles.phaseHeader}>Phase {group.phase}</div>
              {group.planets.map((planet) => {
                const isExpanded = expandedGuidePlanets.includes(planet.id);
                const planetSquadCount = planet.missions.reduce(
                  (total, mission) =>
                    total +
                    (guideData.squads[guideMissionKey(planet.id, mission.id)]?.length ?? 0),
                  0,
                );

                return (
                  <div key={planet.id}>
                    <button
                      type="button"
                      className={`${styles.guidePlanetHeader} ${
                        isExpanded ? styles.guidePlanetHeaderActive : ""
                      }`}
                      onClick={() => toggleGuidePlanet(planet.id)}
                    >
                      <span className={guidePlanetNameClassName(planet, styles)}>
                        {isGuideBonusPlanet(planet) ? "\u2022 " : ""}
                        {planet.name}
                      </span>
                      <span className={styles.guidePlanetCount}>
                        {planetSquadCount > 0 ? planetSquadCount : ""}
                      </span>
                    </button>

                    {isExpanded ? (
                      <div>
                        {planet.missions.map((mission) => {
                          const missionKey = guideMissionKey(planet.id, mission.id);
                          const missionSquadCount = guideData.squads[missionKey]?.length ?? 0;
                          const missionAtLimit = missionSquadCount >= GUIDE_MISSION_LIMIT;
                          const active =
                            activePlanet?.id === planet.id && activeMission?.id === mission.id;
                          return (
                            <button
                              key={mission.id}
                              type="button"
                              className={`${styles.guideMissionItem} ${
                                active ? styles.guideMissionItemActive : ""
                              }`}
                              onClick={() => setSelectedGuideMission(planet.id, mission.id)}
                            >
                              <span className={guideMissionBadgeClassName(mission, styles)}>
                                {mission.unlocks
                                  ? "UN"
                                  : mission.missionType === "sm"
                                    ? "SM"
                                    : mission.missionType === "fleet"
                                      ? "FL"
                                      : "CM"}
                              </span>
                              <span
                                className={`${styles.guideMissionLabel} ${
                                  missionAtLimit ? styles.guideMissionLabelAtLimit : ""
                                }`}
                              >
                                {mission.label}
                              </span>
                              <span
                                className={`${styles.guidePlanetCount} ${
                                  missionAtLimit ? styles.guidePlanetCountAtLimit : ""
                                }`}
                              >
                                {missionSquadCount > 0 ? missionSquadCount : ""}
                              </span>
                              <span
                                className={styles.guideAddButton}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  openGuideEditorForMission(planet.id, mission.id);
                                }}
                                title="Add squad"
                              >
                                +
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </Fragment>
          ))}
        </aside>

        <div className={styles.missionPanel}>
          {activePlanet && activeMission ? (
            <>
              <div className={styles.missionPanelHero}>
                <div>
                  <div className={styles.missionPanelTitle}>
                    {activePlanet.name} - {activeMission.label}
                  </div>
                  <div className={styles.missionPanelMeta}>
                    {guideMissionTypeLabel(activeMission)} |{" "}
                    {guideMissionRequirement(activePlanet, activeMission)}
                  </div>
                  <div className={styles.missionPanelCopy}>
                    Allowed / required units: {activeMission.unitsText}
                  </div>
                  {activeMission.rewardText ? (
                    <div className={styles.noteText}>Reward: {activeMission.rewardText}</div>
                  ) : null}
                  {activeMission.note ? (
                    <div className={styles.noteText}>{activeMission.note}</div>
                  ) : null}
                  <div className={styles.noteText}>Viewing for: {selectedMemberLabel}</div>
                  {activeMissionAtLimit ? (
                    <div className={styles.guideLimitNotice}>
                      {activeMissionOverLimit
                        ? `This mission is over the ${GUIDE_MISSION_LIMIT}-guide limit. Remove unused guides before saving.`
                        : `This mission has reached the ${GUIDE_MISSION_LIMIT}-guide capacity.`}
                    </div>
                  ) : null}
                </div>
                <button
                  type="button"
                  className={styles.primaryButton}
                  onClick={openNewGuideEditor}
                  disabled={activeMissionAtLimit}
                  title={
                    activeMissionAtLimit
                      ? `This mission has reached the ${GUIDE_MISSION_LIMIT}-guide limit.`
                      : "Add Squad"
                  }
                >
                  Add Squad
                </button>
              </div>

              {savedSquads.length ? (
                savedSquads.map((squad, index) => {
                  const rosterCheck = buildGuideRosterCheck(
                    squad,
                    selectedRoster,
                    activeMission,
                    activePlanet,
                  );
                  const expanded = expandedSquads[squad.id] ?? false;
                  const watchUrl = normalizeGuideVideoUrl(squad.videoUrl);
                  const guildReadyCount = scannedRosters.reduce((total, roster) => {
                    const check = buildGuideRosterCheck(squad, roster, activeMission, activePlanet);
                    return total + (check?.ok ? 1 : 0);
                  }, 0);
                  const compositionEntries = [squad.leader, ...squad.members.map((entry) => entry.trim())]
                    .filter(Boolean)
                    .join(", ");

                  return (
                    <article key={squad.id} className={styles.squadCard}>
                      <div className={styles.squadCardHeader}>
                        <div>
                          <div className={styles.squadCardTitle}>
                            {squad.leader || "Unnamed Squad"}
                          </div>
                          <div className={styles.actionRow}>
                            <span className={difficultyBadgeClassName(squad.difficulty)}>
                              {squad.difficulty}
                            </span>
                            {rosterCheck ? (
                              <span
                                className={
                                  rosterCheck.ok
                                    ? styles.guideRosterStatusReady
                                    : styles.guideRosterStatusMissing
                                }
                                title={rosterCheck.reason}
                              >
                                {rosterCheck.ok ? "Ready" : `${rosterCheck.failCount} missing`}
                              </span>
                            ) : (
                              <span className={styles.guidePlanetCount}>No roster check</span>
                            )}
                            <span
                              className={
                                scannedRosters.length
                                  ? styles.guideGuildReady
                                  : styles.guideGuildReadyMuted
                              }
                            >
                              {scannedRosters.length
                                ? `Guild Ready ${guildReadyCount}/${scannedRosters.length}`
                                : "Guild Ready n/a"}
                            </span>
                          </div>
                        </div>

                        <div className={styles.actionRow}>
                          <button
                            type="button"
                            className={styles.secondaryButton}
                            onClick={() =>
                              setExpandedSquads((current) => ({
                                ...current,
                                [squad.id]: !expanded,
                              }))
                            }
                          >
                            {expanded ? "Hide" : "Show"}
                          </button>
                        </div>
                      </div>

                      {expanded ? (
                        <>
                          <div className={styles.squadSection}>
                            <div className={styles.squadSectionLabel}>Composition</div>
                            <div className={styles.squadSectionValue}>
                              {compositionEntries || "No units assigned yet."}
                            </div>
                          </div>

                          <div className={styles.squadSection}>
                            <div className={styles.squadSectionLabel}>Roster Check</div>
                            {rosterCheck ? (
                              <div className={styles.guideCheckList}>
                                {rosterCheck.entries.map((entry) => (
                                  <div
                                    key={`${squad.id}-${entry.slot}-${entry.label}`}
                                    className={
                                      entry.ok
                                        ? styles.guideCheckResultReady
                                        : styles.guideCheckResultMissing
                                    }
                                    title={entry.reason}
                                  >
                                    {entry.ok ? "OK" : "Missing"} {entry.label}:{" "}
                                    {entry.name || "Unassigned"} ({entry.reason})
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <div className={styles.noteText}>
                                Select a scanned guild member to run this mission check.
                              </div>
                            )}
                          </div>

                          {squad.requiredTbOmicrons.length ? (
                            <div className={styles.squadSection}>
                              <div className={styles.squadSectionLabel}>TB Omicrons</div>
                              <div className={styles.omicronList}>
                                {squad.requiredTbOmicrons.map((requirement) => (
                                  <span
                                    key={`${squad.id}-${requirement.unitDefId}-${requirement.skillId}`}
                                    className={styles.omicronBadge}
                                  >
                                    {requirement.unitName || requirement.unitDefId}:{" "}
                                    {requirement.skillName || requirement.skillId}
                                  </span>
                                ))}
                              </div>
                            </div>
                          ) : null}

                          {squad.notes ? (
                            <div className={styles.squadSection}>
                              <div className={styles.squadSectionLabel}>Notes</div>
                              <div className={styles.squadNotes}>{squad.notes}</div>
                            </div>
                          ) : null}

                          {watchUrl ? (
                            <a
                              href={watchUrl}
                              target="_blank"
                              rel="noreferrer"
                              className={styles.linkButton}
                            >
                              Watch Video
                            </a>
                          ) : null}

                          <div className={styles.squadActionRow}>
                            {index > 0 ? (
                              <button
                                type="button"
                                className={styles.secondaryButton}
                                onClick={() => {
                                  moveGuideSquad(activePlanet.id, activeMission.id, squad.id, -1);
                                  setGuideStatus("Guide squad moved up.");
                                }}
                              >
                                Up
                              </button>
                            ) : null}
                            {index < savedSquads.length - 1 ? (
                              <button
                                type="button"
                                className={styles.secondaryButton}
                                onClick={() => {
                                  moveGuideSquad(activePlanet.id, activeMission.id, squad.id, 1);
                                  setGuideStatus("Guide squad moved down.");
                                }}
                              >
                                Down
                              </button>
                            ) : null}
                            <button
                              type="button"
                              className={styles.secondaryButton}
                              onClick={() => openCopyGuideModal(squad)}
                              disabled={!copyMissionOptions.length}
                              title={
                                copyMissionOptions.length
                                  ? "Copy this guide to another eligible mission"
                                  : "No eligible target missions are available"
                              }
                            >
                              Copy to
                            </button>
                            <button
                              type="button"
                              className={styles.secondaryButton}
                              onClick={() => openExistingGuideEditor(squad)}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className={styles.secondaryButton}
                              onClick={() => {
                                if (!window.confirm("Delete this squad?")) return;
                                deleteGuideSquad(activePlanet.id, activeMission.id, squad.id);
                                setGuideStatus("Guide squad deleted.");
                              }}
                            >
                              Delete
                            </button>
                          </div>
                        </>
                      ) : null}
                    </article>
                  );
                })
              ) : (
                <article className={styles.emptyStateCard}>
                  <div className={styles.emptyStateTitle}>
                    No squads yet. Click Add Squad to create the first one.
                  </div>
                  <div className={styles.emptyStateCopy}>
                    This mission now uses persisted squad data in the Zustand workspace state,
                    with JSON export/import restored to match the legacy planner flow.
                  </div>
                </article>
              )}
            </>
          ) : (
            <article className={styles.emptyStateCard}>
              <div className={styles.emptyStateTitle}>No guide mission selected</div>
              <div className={styles.emptyStateCopy}>
                Choose a planet mission from the left to review requirements and manage saved
                squad guides.
              </div>
            </article>
          )}
        </div>
      </div>

      {guideEditorOpen && activePlanet && activeMission ? (
        <GuideEditorModal
          planet={activePlanet}
          mission={activeMission}
          initialSquad={editingSquad}
          initialDifficulty={guideEditorDifficulty}
          guideTbOmicrons={guideTbOmicrons}
          guideUnitLookup={guideUnitLookup}
          guideCharacterOptions={guideCharacterOptions}
          guideShipOptions={guideShipOptions}
          onClose={handleCloseGuideEditor}
          onSave={handleGuideEditorSave}
        />
      ) : null}
      {copyingSquad && activePlanet && activeMission ? (
        <GuideCopyModal
          squad={copyingSquad}
          sourcePlanetName={activePlanet.name}
          sourceMissionLabel={activeMission.label}
          targetPlanetId={copyTargetPlanetId}
          targetMissionId={copyTargetMissionId}
          targetPlanets={copyTargetPlanets}
          targetMissions={copyTargetMissions}
          onPlanetChange={setCopyTargetPlanetId}
          onMissionChange={setCopyTargetMissionId}
          onClose={closeCopyGuideModal}
          onConfirm={handleCopyGuide}
        />
      ) : null}
    </section>
  );
}

export function RosterPage() {
  const guildSummary = usePlannerStore((state) => state.guildSummary);
  const guildRosters = usePlannerStore((state) => state.guildRosters);
  const selectedRosterMemberId = usePlannerStore((state) => state.selectedRosterMemberId);
  const rosterSearch = usePlannerStore((state) => state.rosterSearch);
  const rosterFilter = usePlannerStore((state) => state.rosterFilter);
  const rosterSortKey = usePlannerStore((state) => state.rosterSortKey);
  const setSelectedRosterMemberId = usePlannerStore((state) => state.setSelectedRosterMemberId);
  const setRosterSearch = usePlannerStore((state) => state.setRosterSearch);
  const setRosterFilter = usePlannerStore((state) => state.setRosterFilter);
  const setRosterSortKey = usePlannerStore((state) => state.setRosterSortKey);

  const rosterMembers = buildRosterMembers(guildSummary, guildRosters);
  const rosterMember =
    rosterMembers.find((member) => member.id === selectedRosterMemberId) ??
    rosterMembers[0] ??
    null;

  if (!rosterMembers.length || !rosterMember) {
    return (
      <section className={styles.panel}>
        <article className={styles.rosterSection}>
          <div className={styles.emptyStateTitle}>No roster data loaded yet.</div>
          <div className={styles.emptyStateCopy}>
            Run Scan Rosters from Guild Overview after comlink is online. The roster tab
            now only shows scanned members and will stay empty until live profile data is
            actually available.
          </div>
        </article>
      </section>
    );
  }

  const filteredCharacters = filterRosterUnits(
    rosterMember.characters,
    rosterSearch,
    rosterFilter,
    rosterSortKey,
  );
  const filteredShips = filterRosterUnits(
    rosterMember.ships,
    rosterSearch,
    rosterFilter,
    rosterSortKey,
  );
  const rosterSummary = buildRosterSummary(filteredCharacters, filteredShips);

  return (
    <section className={styles.panel}>
      <div className={styles.rosterTopBar}>
        <div className={styles.rosterSelectWrap}>
          <select
            className={styles.selectControl}
            value={rosterMember.id}
            onChange={(event) => setSelectedRosterMemberId(event.currentTarget.value)}
          >
            {rosterMembers.map((member) => (
              <option key={member.id} value={member.id}>
                {member.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.searchRow}>
          <input
            className={styles.searchInput}
            value={rosterSearch}
            onChange={(event) => setRosterSearch(event.currentTarget.value)}
            placeholder="Search units..."
          />
          <select
            className={styles.selectControl}
            value={rosterFilter}
            onChange={(event) => setRosterFilter(event.currentTarget.value)}
          >
            <option value="all">All Units</option>
            <option value="chars">Characters Only</option>
            <option value="ships">Ships Only</option>
            <option value="r5plus">R5+ Only</option>
            <option value="r7plus">R7+ Only</option>
            <option value="r9plus">R9+ Only</option>
            <option value="g12plus">G12+ Only</option>
          </select>
        </div>

        <div className={styles.summaryText}>{rosterSummary}</div>
      </div>

      <div className={styles.sortBar}>
        {[
          ["name", "Character"],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`${styles.sortButton} ${
              rosterSortKey === key ? styles.sortButtonActive : ""
            }`}
            onClick={() => setRosterSortKey(key)}
          >
            {label}
          </button>
        ))}
        <span className={styles.sortLabel}>Highest Guild Gear/Relic level</span>
        {[
          ["type", "Type"],
          ["stars", "Star"],
          ["level", "Gear/Relic"],
          ["power", "Power"],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`${styles.sortButton} ${
              rosterSortKey === key ? styles.sortButtonActive : ""
            }`}
            onClick={() => setRosterSortKey(key)}
          >
            {label}
          </button>
        ))}
        <span className={styles.sortStaticLabel}>Abilities</span>
      </div>

      <div className={styles.rosterSection}>
        <div className={styles.rosterSectionHeader}>
          <span className={styles.rosterSectionTitle}>
            Characters ({filteredCharacters.length})
          </span>
        </div>
        <div className={styles.rosterList}>
          {filteredCharacters.length ? (
            filteredCharacters.map((unit) => (
              <div key={unit.defId ?? unit.name} className={styles.rosterRow}>
                <span>{unit.name}</span>
                <span className={styles.rosterGuildLevel}>
                  {unit.highestGuildLevel ?? "-"}
                </span>
                <span>{unit.type}</span>
                <span>{unit.stars}</span>
                <span>{unit.level}</span>
                <span
                  className={`${styles.rosterPowerValue} ${
                    unit.powerMissing ? styles.rosterPowerMissing : ""
                  }`}
                >
                  {unit.power}
                </span>
                <span className={styles.abilityList}>
                  {unit.abilities.length ? (
                    <span className={styles.abilityStack}>
                      {unit.abilities.map((ability, index) => {
                        const normalized = normalizeRosterAbility(ability);
                        return (
                          <span
                            key={`${normalized.name}-${index}`}
                            className={styles.abilityRow}
                          >
                            <span className={styles.abilityName}>{normalized.name}</span>
                            <span className={styles.abilityMeta}>
                              {normalized.detail ? (
                                <span className={styles.abilityDetail}>{normalized.detail}</span>
                              ) : null}
                              {normalized.hasZeta ? (
                                <span
                                  className={`${styles.abilityTag} ${styles.abilityTagZeta}`}
                                >
                                  Zeta
                                </span>
                              ) : null}
                              {normalized.hasOmicron ? (
                                <span
                                  className={`${styles.abilityTag} ${styles.abilityTagOmicron}`}
                                >
                                  Omicron
                                </span>
                              ) : null}
                            </span>
                          </span>
                        );
                      })}
                    </span>
                  ) : (
                    <span className={styles.abilityMissing}>Re-scan to load abilities</span>
                  )}
                </span>
              </div>
            ))
          ) : (
            <div className={styles.emptyRosterRow}>No characters match this filter.</div>
          )}
        </div>
      </div>

      <div className={styles.rosterSection}>
        <div className={styles.rosterSectionHeader}>
          <span className={styles.rosterSectionTitle}>Ships ({filteredShips.length})</span>
        </div>
        <div className={styles.rosterList}>
          {filteredShips.length ? (
            filteredShips.map((unit) => (
              <div key={unit.defId ?? unit.name} className={styles.rosterRow}>
                <span>{unit.name}</span>
                <span className={styles.rosterGuildLevel}>
                  {unit.highestGuildLevel ?? "-"}
                </span>
                <span>{unit.type}</span>
                <span>{unit.stars}</span>
                <span>{unit.level}</span>
                <span
                  className={`${styles.rosterPowerValue} ${
                    unit.powerMissing ? styles.rosterPowerMissing : ""
                  }`}
                >
                  {unit.power}
                </span>
                <span className={styles.abilityList}>
                  {unit.abilities.length ? (
                    <span className={styles.abilityStack}>
                      {unit.abilities.map((ability, index) => {
                        const normalized = normalizeRosterAbility(ability);
                        return (
                          <span
                            key={`${normalized.name}-${index}`}
                            className={styles.abilityRow}
                          >
                            <span className={styles.abilityName}>{normalized.name}</span>
                            <span className={styles.abilityMeta}>
                              {normalized.detail ? (
                                <span className={styles.abilityDetail}>{normalized.detail}</span>
                              ) : null}
                              {normalized.hasZeta ? (
                                <span
                                  className={`${styles.abilityTag} ${styles.abilityTagZeta}`}
                                >
                                  Zeta
                                </span>
                              ) : null}
                              {normalized.hasOmicron ? (
                                <span
                                  className={`${styles.abilityTag} ${styles.abilityTagOmicron}`}
                                >
                                  Omicron
                                </span>
                              ) : null}
                            </span>
                          </span>
                        );
                      })}
                    </span>
                  ) : (
                    <span className={styles.abilityMissing}>Re-scan to load abilities</span>
                  )}
                </span>
              </div>
            ))
          ) : (
            <div className={styles.emptyRosterRow}>No ships match this filter.</div>
          )}
        </div>
      </div>
    </section>
  );
}
