import type {
  GuildRosters,
  GuildSummary,
  OpsDefinitions,
  PlatoonAnalysisEntry,
  PlatoonAnalysisMap,
  SimplifiedRosterUnit,
} from "../../lib/plannerApi";
import type {
  MemberCard,
  OverviewMetric,
  OperationsStatus,
  RosterAbility,
  RosterUnit,
} from "./mockData";

export type RuntimeRosterMember = {
  id: string;
  label: string;
  summary: string;
  characters: RosterUnit[];
  ships: RosterUnit[];
};

export type RuntimeOperationsStage = {
  stageTitle: string;
  stageSubtitle: string;
  stageMeta: string;
  platoons: Array<{
    id: number;
    status: OperationsStatus;
    filled: string;
    label: string;
    slots: Array<{
      name: string;
      assignee: string;
      meta: string;
      unassigned?: boolean;
    }>;
  }>;
  missing?: {
    title: string;
    lines: string[];
  };
};

export function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(Math.max(0, Math.round(value)));
}

export function formatMillions(value: number) {
  return `${(value / 1_000_000).toFixed(1)}M`;
}

export function buildOverviewMembers(
  guildSummary: GuildSummary | null,
  guildRosters: GuildRosters,
): MemberCard[] {
  if (!guildSummary) return [];

  return [...guildSummary.members]
    .sort((left, right) => right.galacticPower - left.galacticPower)
    .map((member) => {
      const roster = guildRosters[member.allyCode] ?? guildRosters[member.playerId] ?? [];
      const relicPips = roster
        .filter((unit) => unit.combatType === 1)
        .sort((left, right) => right.relic - left.relic)
        .slice(0, 5)
        .map((unit) => {
          if (unit.relic >= 7) return "r7" as const;
          if (unit.relic >= 5) return "r5" as const;
          return "base" as const;
        });

      while (relicPips.length < 5) relicPips.push("base");

      return {
        name: member.displayName,
        gp: `${formatMillions(member.galacticPower)} GP`,
        relicPips,
      };
    });
}

export function buildRosterMembers(
  guildSummary: GuildSummary | null,
  guildRosters: GuildRosters,
): RuntimeRosterMember[] {
  if (!guildSummary) return [];

  const memberLookup = new Map<string, GuildSummary["members"][number]>();
  guildSummary.members.forEach((member) => {
    if (member.allyCode) memberLookup.set(member.allyCode, member);
    if (member.playerId) memberLookup.set(member.playerId, member);
  });

  return Object.entries(guildRosters)
    .filter(([, roster]) => Array.isArray(roster) && roster.length > 0)
    .map(([memberId, roster]) => {
      const member = memberLookup.get(memberId);
      const characters = roster.filter((unit) => unit.combatType === 1).map(toRosterRow);
      const ships = roster.filter((unit) => unit.combatType === 2).map(toRosterRow);

      return {
        id: memberId,
        label: member?.displayName ?? memberId,
        summary: buildRosterSummary(characters, ships),
        characters,
        ships,
      };
    })
    .sort((left, right) => left.label.localeCompare(right.label));
}

export function buildRosterSummary(characters: RosterUnit[], ships: RosterUnit[]) {
  const units = [...characters, ...ships];
  const total = units.length;
  const r7Plus = characters.filter((unit) => (unit.relic ?? 0) >= 7).length;
  const r5Plus = characters.filter((unit) => (unit.relic ?? 0) >= 5).length;
  const abilityHint =
    characters.length && !characters.some((unit) => unit.hasAbilityDetails)
      ? " | re-scan rosters to load ability details"
      : "";
  const powerHint =
    total && !units.some((unit) => (unit.powerValue ?? 0) > 0)
      ? " | re-scan rosters to load unit power"
      : "";

  return `${total} units | ${characters.length} characters | ${ships.length} ships | ${r7Plus} R7+ | ${r5Plus} R5+${abilityHint}${powerHint}`;
}

export function filterRosterUnits(
  units: RosterUnit[],
  search: string,
  filter: string,
  sortKey: string,
) {
  const needle = search.trim().toLowerCase();
  const filtered = units.filter((unit) => {
    if (
      needle &&
      !unit.name.toLowerCase().includes(needle) &&
      !(unit.defId ?? "").toLowerCase().includes(needle)
    ) {
      return false;
    }
    if (filter === "chars" && unit.type !== "Character") return false;
    if (filter === "ships" && unit.type !== "Ship") return false;
    if (filter === "r5plus" && unit.type === "Character") {
      return (unit.relic ?? 0) >= 5;
    }
    if (filter === "r7plus" && unit.type === "Character") {
      return (unit.relic ?? 0) >= 7;
    }
    if (filter === "r9plus" && unit.type === "Character") {
      return (unit.relic ?? 0) >= 9;
    }
    if (filter === "g12plus" && unit.type === "Character") {
      return (unit.relic ?? 0) > 0 || (unit.gear ?? 0) >= 12;
    }
    return true;
  });

  const sorted = [...filtered].sort((left, right) => {
    if (sortKey === "power") {
      return (right.powerValue ?? 0) - (left.powerValue ?? 0);
    }
    if (sortKey === "stars") {
      return (right.rarity ?? 0) - (left.rarity ?? 0);
    }
    if (sortKey === "level") {
      return rosterLevelValue(right) - rosterLevelValue(left);
    }
    if (sortKey === "type") {
      return left.type.localeCompare(right.type);
    }
    return left.name.localeCompare(right.name);
  });

  return sorted;
}

export function buildOperationsMetrics(
  analysis: PlatoonAnalysisMap | null,
  guildRosters: GuildRosters,
  defs: OpsDefinitions | null,
): OverviewMetric[] {
  if (!analysis) {
    const totalPlatoons = Object.values(defs ?? {}).reduce(
      (sum, planetPlatoons) => sum + planetPlatoons.length,
      0,
    );
    return [
      { label: "Projected Platoons", value: `${totalPlatoons}`, tone: "neutral" },
      { label: "Projected Ops Points", value: "Awaiting scan", tone: "gold" },
      { label: "Definitions Loaded", value: defs ? "Bundled Wiki" : "Not loaded", tone: "neutral" },
      { label: "Roster Coverage", value: `${Object.keys(guildRosters).length}`, tone: "purple" },
    ];
  }

  let total = 0;
  let fillable = 0;
  Object.values(analysis).forEach((planet) => {
    planet.forEach((platoon) => {
      total += 1;
      if (platoon.fillable) fillable += 1;
    });
  });

  return [
    { label: "Projected Platoons", value: `${fillable} / ${total}`, tone: "green" },
    { label: "Projected Ops Points", value: `${fillable * 1.0}M`, tone: "gold" },
    { label: "Definitions Loaded", value: defs ? "Bundled Wiki" : "Not loaded", tone: "neutral" },
    { label: "Roster Coverage", value: `${Object.keys(guildRosters).length} members`, tone: "purple" },
  ];
}

export function buildOperationsStage(
  planetId: string,
  analysis: PlatoonAnalysisMap | null,
): RuntimeOperationsStage | null {
  const planet = analysis?.[planetId];
  if (!planet) return null;

  const fillableCount = planet.filter((entry) => entry.fillable).length;
  const titleName = titleizePlanet(planetId);
  const missingLines = planet.flatMap((entry, index) =>
    entry.slots
      .filter((slot) => !slot.ok)
      .map(
        (slot) =>
          `Platoon ${index + 1}: need ${Math.max(slot.need - slot.have, 0)} more ${slot.name}`,
      ),
  );

  return {
    stageTitle: `${titleName} - Platoon Analysis`,
    stageSubtitle: "Live roster analysis from the Rust backend using the bundled wiki operations definitions.",
    stageMeta: `${fillableCount} / ${planet.length} platoons fillable`,
    platoons: planet.map((platoon, index) => {
      const totalSlots = totalPlatoonSlots(platoon);
      const filledSlots = filledPlatoonSlots(platoon);
      return {
        id: index + 1,
        status: statusFromPlatoon(platoon),
        filled: `${filledSlots}/${totalSlots} slots ready`,
        label:
          filledSlots >= totalSlots
            ? "Ready"
            : filledSlots > 0
              ? "Partial"
              : "Shortfall",
        slots: expandPlatoonRequirements(platoon),
      };
    }),
    missing: missingLines.length
      ? {
          title: "Shortfall summary",
          lines: missingLines.slice(0, 6),
        }
      : undefined,
  };
}

export function buildPlanetOptions(analysis: PlatoonAnalysisMap | null) {
  return analysis ? Object.keys(analysis) : [];
}

function toRosterRow(unit: SimplifiedRosterUnit): RosterUnit {
  const powerValue = Math.max(0, Math.round(unit.power));
  return {
    defId: unit.defId,
    name: unit.name,
    type: unit.combatType === 2 ? "Ship" : "Character",
    stars: `${unit.rarity}`,
    rarity: unit.rarity,
    level: unit.combatType === 2 ? "-" : unit.relic > 0 ? `R${unit.relic}` : `G${unit.gear}`,
    gear: unit.gear,
    relic: unit.relic,
    power: powerValue > 0 ? formatNumber(powerValue) : "-",
    powerValue,
    powerMissing: powerValue <= 0,
    hasAbilityDetails: unit.skills.length > 0,
    abilities:
      unit.skills
        .map((skill) => formatRosterAbility(skill))
        .filter(Boolean),
  };
}

function rosterLevelValue(unit: RosterUnit) {
  if (unit.level.startsWith("R")) {
    return 20 + (Number(unit.level.slice(1)) || 0);
  }
  if (unit.level.startsWith("G")) {
    return Number(unit.level.slice(1)) || 0;
  }
  return 0;
}

function formatRosterAbility(
  skill: SimplifiedRosterUnit["skills"][number],
): RosterAbility {
  const name = (skill.name || skill.kind || "Ability").trim();

  let detail = "";
  if (skill.kind === "ultimate" || skill.unlocked) {
    detail = "Unlocked";
  } else if (skill.level > 0) {
    detail = `Lv ${skill.level}`;
  } else if (skill.tier > 0) {
    detail = `Tier ${skill.tier}`;
  }

  return {
    name,
    detail,
    hasZeta: skill.hasZeta,
    hasOmicron: skill.hasOmicron,
  };
}

function statusFromPlatoon(platoon: PlatoonAnalysisEntry): OperationsStatus {
  const totalSlots = totalPlatoonSlots(platoon);
  const filledSlots = filledPlatoonSlots(platoon);
  if (filledSlots >= totalSlots && totalSlots > 0) return "complete";
  if (filledSlots === 0) return "impossible";
  return "partial";
}

function totalPlatoonSlots(platoon: PlatoonAnalysisEntry) {
  return platoon.slots.reduce((sum, slot) => sum + Math.max(0, slot.need), 0);
}

function filledPlatoonSlots(platoon: PlatoonAnalysisEntry) {
  return platoon.slots.reduce((sum, slot) => sum + Math.max(0, Math.min(slot.have, slot.need)), 0);
}

function expandPlatoonRequirements(platoon: PlatoonAnalysisEntry) {
  return platoon.slots.flatMap((slot) => {
    const readyCopies = Math.max(0, Math.min(slot.have, slot.need));
    const requirementText =
      slot.minRelic > 0 ? `${slot.minRarity}* | R${slot.minRelic}+` : `${slot.minRarity}* | Ship`;

    return Array.from({ length: Math.max(0, slot.need) }, (_, index) => ({
      name: slot.need > 1 ? `${slot.name} ${index + 1}` : slot.name,
      assignee: index < readyCopies ? "Eligible copy ready" : "Unfilled",
      meta: `Players available: ${slot.have} | Requirement: ${requirementText}`,
      unassigned: index >= readyCopies,
    }));
  });
}

function titleizePlanet(planetId: string) {
  return planetId
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
