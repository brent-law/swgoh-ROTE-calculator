export type ChainKey = "ds" | "mx" | "ls";
export type Alignment = ChainKey | "bonus";
export type GuideMissionType = "combat" | "fleet" | "special";
export type GuideDifficulty = "auto" | "easy" | "medium" | "hard";
export type OperationsStatus = "complete" | "partial" | "impossible" | "ready";

export type NavigationTab = {
  to: string;
  label: string;
};

export type MemberCard = {
  name: string;
  gp: string;
  relicPips: Array<"base" | "r5" | "r7">;
};

export type OverviewMetric = {
  label: string;
  value: string;
  tone: "gold" | "green" | "purple" | "neutral";
};

export type DailyUndeployedRow = {
  day: number;
  value: string;
  effectiveGp: string;
};

export type PlanetMissionEstimate = {
  label: string;
  completion: string;
  points: string;
};

export type PlanetCardData = {
  id: string;
  name: string;
  align: Alignment;
  status: "s1" | "s2" | "s3" | "locked";
  capability: string;
  estimate: string;
  target: string;
  progress: number;
  note: string;
  combatMissions: PlanetMissionEstimate[];
  fleetMissions: PlanetMissionEstimate[];
  operations: boolean[];
  operationsNote: string;
  bonusLocked?: boolean;
};

export type DayPlanAlgorithm = {
  id: string;
  label: string;
  description: string;
  quality: string;
  complexity: string;
  runtime: string;
};

export type DayChainCard = {
  align: Alignment;
  title: string;
  planetName: string;
  stars: string;
  action: string;
  breakdown: string;
  advance: string;
};

export type DayPlanCard = {
  day: number;
  gpAvailable: string;
  gpUsed: string;
  starsEarned: string;
  chainCards: DayChainCard[];
  notes: { tone: "neutral" | "bonus" | "success"; text: string }[];
};

export type OperationsDayPicker = {
  day: number;
  pointsEarned: string;
  activePlanetCount: number;
  summary: string;
  planetIds: string[];
};

export type OperationsSlot = {
  name: string;
  assignee: string;
  meta: string;
  unassigned?: boolean;
};

export type OperationsPlatoon = {
  id: number;
  status: OperationsStatus;
  filled: string;
  label: string;
  slots: OperationsSlot[];
};

export type OperationsPlanetStage = {
  id: string;
  name: string;
  zone: string;
  label: string;
  todaySummary: string;
  stageTitle: string;
  stageSubtitle: string;
  stageMeta: string;
  platoons: OperationsPlatoon[];
  missing?: {
    title: string;
    lines: string[];
  };
};

export type GuideMissionListItem = {
  id: string;
  label: string;
  type: GuideMissionType;
  squadCount: number;
};

export type GuidePlanetListItem = {
  id: string;
  name: string;
  align: Alignment;
  phase: number;
  squadCount: number;
  missions: GuideMissionListItem[];
};

export type GuideSquad = {
  id: string;
  title: string;
  difficulty: GuideDifficulty;
  readiness: string;
  leader: string;
  members: string[];
  omicrons: string[];
  notes: string;
  videoLabel: string;
};

export type GuideMissionDetail = {
  planetId: string;
  missionId: string;
  planetName: string;
  align: Alignment;
  missionName: string;
  missionTypeLabel: string;
  requirement: string;
  summary: string;
  squads: GuideSquad[];
};

export type RosterAbility = {
  name: string;
  detail?: string;
  hasZeta?: boolean;
  hasOmicron?: boolean;
};

export type RosterUnit = {
  defId?: string;
  name: string;
  type: "Character" | "Ship";
  stars: string;
  rarity?: number;
  level: string;
  gear?: number;
  relic?: number;
  power: string;
  powerValue?: number;
  powerMissing?: boolean;
  hasAbilityDetails?: boolean;
  abilities: Array<RosterAbility | string>;
};

export type RosterMember = {
  id: string;
  label: string;
  summary: string;
  characters: RosterUnit[];
  ships: RosterUnit[];
};

export const plannerTabs: NavigationTab[] = [
  { to: "/guild-overview", label: "Guild Overview" },
  { to: "/planet-planner", label: "Planet Planner" },
  { to: "/day-by-day-plan", label: "Day-by-Day Plan" },
  { to: "/operations", label: "Operations" },
  { to: "/guides", label: "Guides" },
  { to: "/roster", label: "Roster" },
];

export const overviewMembers: MemberCard[] = [
  { name: "Crimson Lead", gp: "11.4M GP", relicPips: ["r7", "r7", "r5", "base", "base"] },
  { name: "Echo Sabers", gp: "10.9M GP", relicPips: ["r7", "r5", "r5", "base", "base"] },
  { name: "Moff Archive", gp: "10.5M GP", relicPips: ["r7", "r7", "base", "base", "base"] },
  { name: "Blue Squadron", gp: "10.2M GP", relicPips: ["r5", "r5", "base", "base", "base"] },
  { name: "Hidden Path", gp: "10.0M GP", relicPips: ["r7", "r5", "base", "base", "base"] },
  { name: "Outer Rim Ops", gp: "9.8M GP", relicPips: ["r5", "r5", "base", "base", "base"] },
  { name: "Alderaan East", gp: "9.6M GP", relicPips: ["r7", "base", "base", "base", "base"] },
  { name: "Phoenix Trace", gp: "9.4M GP", relicPips: ["r5", "base", "base", "base", "base"] },
];

export const overviewMetrics: OverviewMetric[] = [
  { label: "Est. Stars", value: "35", tone: "gold" },
  { label: "Ops Filled", value: "43 / 54", tone: "green" },
  { label: "Special Locks", value: "4 Ready", tone: "purple" },
  { label: "Last Snapshot", value: "Today 02:11", tone: "neutral" },
];

export const dailyUndeployedRows: DailyUndeployedRow[] = [
  { day: 1, value: "3%", effectiveGp: "439.2M" },
  { day: 2, value: "5%", effectiveGp: "430.1M" },
  { day: 3, value: "6%", effectiveGp: "425.5M" },
  { day: 4, value: "8%", effectiveGp: "416.4M" },
  { day: 5, value: "10%", effectiveGp: "407.2M" },
  { day: 6, value: "12%", effectiveGp: "398.1M" },
];

export const plannerChains: Record<ChainKey, PlanetCardData[]> = {
  ds: [
    {
      id: "mustafar",
      name: "Mustafar",
      align: "ds",
      status: "s3",
      capability: "Empire and Inquisitor core ready",
      estimate: "116.4M",
      target: "96.5M",
      progress: 100,
      note: "3 stars achievable",
      combatMissions: [
        { label: "CM 1", completion: "84%", points: "14.2M" },
        { label: "CM 2", completion: "81%", points: "13.7M" },
      ],
      fleetMissions: [{ label: "Fleet", completion: "71%", points: "8.1M" }],
      operations: [true, true, true, false, true, false],
      operationsNote: "4 platoons forecast today",
    },
    {
      id: "bracca",
      name: "Bracca",
      align: "ds",
      status: "s2",
      capability: "Lord Vader preloaded, fleets slightly behind",
      estimate: "78.9M",
      target: "95.1M",
      progress: 82,
      note: "16.2M needed for 3-star",
      combatMissions: [
        { label: "CM 1", completion: "77%", points: "12.9M" },
        { label: "CM 2", completion: "72%", points: "11.8M" },
      ],
      fleetMissions: [{ label: "Fleet", completion: "64%", points: "6.4M" }],
      operations: [true, false, false, false, true, false],
      operationsNote: "2 platoons strong, 2 blocked",
    },
    {
      id: "geonosis",
      name: "Geonosis",
      align: "bonus",
      status: "s1",
      capability: "Bonus planet unlock on track",
      estimate: "29.7M",
      target: "84.0M",
      progress: 35,
      note: "Carryover lane for tomorrow",
      combatMissions: [{ label: "CM", completion: "52%", points: "7.8M" }],
      fleetMissions: [{ label: "Fleet", completion: "38%", points: "3.6M" }],
      operations: [false, false, true, false, false, false],
      operationsNote: "1 preload platoon only",
    },
  ],
  mx: [
    {
      id: "corellia",
      name: "Corellia",
      align: "mx",
      status: "s3",
      capability: "Jabba smugglers and mixed fleet lane covered",
      estimate: "108.1M",
      target: "97.2M",
      progress: 100,
      note: "3 stars achievable",
      combatMissions: [
        { label: "CM 1", completion: "82%", points: "13.6M" },
        { label: "CM 2", completion: "79%", points: "13.1M" },
      ],
      fleetMissions: [{ label: "Fleet", completion: "69%", points: "7.8M" }],
      operations: [true, true, false, true, true, false],
      operationsNote: "4 platoons scheduled, 1 spare lane",
    },
    {
      id: "felucia",
      name: "Felucia",
      align: "mx",
      status: "s2",
      capability: "Mixed Jedi and Nightsister lane",
      estimate: "82.3M",
      target: "101.5M",
      progress: 78,
      note: "19.2M needed for 3-star",
      combatMissions: [
        { label: "CM 1", completion: "74%", points: "11.5M" },
        { label: "CM 2", completion: "68%", points: "10.9M" },
      ],
      fleetMissions: [{ label: "Fleet", completion: "61%", points: "5.9M" }],
      operations: [true, false, false, true, false, false],
      operationsNote: "2 platoons fillable, 1 partial",
    },
    {
      id: "mandalore",
      name: "Mandalore",
      align: "bonus",
      status: "locked",
      capability: "Requires Day 4 unlock",
      estimate: "0M",
      target: "112.0M",
      progress: 0,
      note: "Bonus locked",
      combatMissions: [{ label: "CM", completion: "Locked", points: "0M" }],
      fleetMissions: [{ label: "Fleet", completion: "Locked", points: "0M" }],
      operations: [false, false, false, false, false, false],
      operationsNote: "No platoons until unlocked",
      bonusLocked: true,
    },
  ],
  ls: [
    {
      id: "coruscant",
      name: "Coruscant",
      align: "ls",
      status: "s3",
      capability: "Galactic Republic and Jedi lane online",
      estimate: "119.6M",
      target: "102.6M",
      progress: 100,
      note: "3 stars achievable",
      combatMissions: [
        { label: "CM 1", completion: "88%", points: "15.1M" },
        { label: "CM 2", completion: "84%", points: "14.4M" },
      ],
      fleetMissions: [{ label: "Fleet", completion: "73%", points: "8.9M" }],
      operations: [true, true, true, true, false, true],
      operationsNote: "5 platoons forecast complete",
    },
    {
      id: "kashyyyk",
      name: "Kashyyyk",
      align: "ls",
      status: "s2",
      capability: "Leia lane steady, fleet precision needed",
      estimate: "86.7M",
      target: "103.4M",
      progress: 83,
      note: "16.7M needed for 3-star",
      combatMissions: [
        { label: "CM 1", completion: "76%", points: "12.8M" },
        { label: "CM 2", completion: "70%", points: "11.6M" },
      ],
      fleetMissions: [{ label: "Fleet", completion: "63%", points: "6.3M" }],
      operations: [true, true, false, false, false, true],
      operationsNote: "3 platoons strong, 1 risky lane",
    },
    {
      id: "lothal",
      name: "Lothal",
      align: "ls",
      status: "s1",
      capability: "Fallback preload lane",
      estimate: "41.8M",
      target: "98.7M",
      progress: 42,
      note: "Preloading below 2-star",
      combatMissions: [{ label: "CM", completion: "58%", points: "9.7M" }],
      fleetMissions: [{ label: "Fleet", completion: "44%", points: "4.4M" }],
      operations: [false, false, true, false, false, false],
      operationsNote: "1 preload platoon only",
    },
  ],
};

export const dayPlanAlgorithms: DayPlanAlgorithm[] = [
  {
    id: "greedy",
    label: "Greedy Enumeration",
    description: "Fastest pass for quick sanity checks while officers adjust GP assumptions.",
    quality: "Fast",
    complexity: "Low setup",
    runtime: "Seconds",
  },
  {
    id: "sa",
    label: "Simulated Annealing",
    description: "Explores more alternatives after the first pass and usually finds cleaner tradeoffs.",
    quality: "Balanced",
    complexity: "Medium setup",
    runtime: "Minutes",
  },
  {
    id: "pso",
    label: "Particle Swarm",
    description: "Good for high-GP guilds where a few million points change the unlock order.",
    quality: "High quality",
    complexity: "Medium setup",
    runtime: "Minutes",
  },
  {
    id: "ga",
    label: "Genetic Algorithm",
    description: "Searches wider plan variations and is a strong candidate for full guild planning runs.",
    quality: "High quality",
    complexity: "Higher setup",
    runtime: "Long",
  },
  {
    id: "adam",
    label: "Adam Optimizer",
    description: "Slowest pass but useful when you want a deep unattended run across the full plan.",
    quality: "Deep search",
    complexity: "High setup",
    runtime: "Very long",
  },
  {
    id: "all",
    label: "All Algorithms",
    description: "Runs every strategy back to back and compares the best result from each one.",
    quality: "Compare all",
    complexity: "Highest setup",
    runtime: "Hours",
  },
];

export const dayPlanCards: DayPlanCard[] = [
  {
    day: 1,
    gpAvailable: "439.2M",
    gpUsed: "426.9M",
    starsEarned: "8 stars",
    chainCards: [
      {
        align: "ds",
        title: "Dark Side",
        planetName: "Mustafar",
        stars: "3 stars",
        action: "Projected total: 116.4M points",
        breakdown: "Combat 62.1M, Fleet 18.5M, Deploy 35.8M",
        advance: "3-star complete - next planet unlocks tomorrow",
      },
      {
        align: "mx",
        title: "Mixed",
        planetName: "Corellia",
        stars: "3 stars",
        action: "Projected total: 108.1M points",
        breakdown: "Combat 58.7M, Fleet 16.4M, Deploy 33.0M",
        advance: "3-star complete - special mission remains optional",
      },
      {
        align: "ls",
        title: "Light Side",
        planetName: "Coruscant",
        stars: "2 stars",
        action: "Projected total: 89.6M points",
        breakdown: "Combat 50.2M, Fleet 14.6M, Deploy 24.8M",
        advance: "13.0M needed for 3-star",
      },
    ],
    notes: [
      { tone: "success", text: "Operations: +6.3M projected from the opening assignments." },
      { tone: "neutral", text: "Use spare GP on Coruscant before preloading bonus lanes." },
    ],
  },
  {
    day: 2,
    gpAvailable: "430.1M",
    gpUsed: "417.0M",
    starsEarned: "7 stars",
    chainCards: [
      {
        align: "ds",
        title: "Dark Side",
        planetName: "Bracca",
        stars: "2 stars",
        action: "Projected total: 78.9M points",
        breakdown: "Combat 44.1M, Fleet 10.3M, Deploy 24.5M",
        advance: "16.2M needed for 3-star",
      },
      {
        align: "mx",
        title: "Mixed",
        planetName: "Felucia",
        stars: "2 stars",
        action: "Projected total: 82.3M points",
        breakdown: "Combat 46.5M, Fleet 9.9M, Deploy 25.9M",
        advance: "19.2M needed for 3-star",
      },
      {
        align: "bonus",
        title: "Bonus Planet",
        planetName: "Geonosis",
        stars: "Active",
        action: "Projected total: 29.7M points",
        breakdown: "Carryover lane with low-risk preload",
        advance: "Carryover into tomorrow: 4.4M",
      },
    ],
    notes: [
      { tone: "bonus", text: "Bonus unlock active from Mustafar hitting 1-star on Day 1." },
      { tone: "neutral", text: "Bank GP below 1-star on Lothal if Dark Side gets blocked." },
    ],
  },
  {
    day: 3,
    gpAvailable: "425.5M",
    gpUsed: "401.8M",
    starsEarned: "6 stars",
    chainCards: [
      {
        align: "ls",
        title: "Light Side",
        planetName: "Kashyyyk",
        stars: "2 stars",
        action: "Projected total: 86.7M points",
        breakdown: "Combat 48.0M, Fleet 11.1M, Deploy 27.6M",
        advance: "16.7M needed for 3-star",
      },
      {
        align: "mx",
        title: "Mixed",
        planetName: "Felucia",
        stars: "Preloading",
        action: "Projected total: 44.0M points",
        breakdown: "Banking below 1-star for tomorrow",
        advance: "Tomorrow est. base: 75.0M",
      },
      {
        align: "ds",
        title: "Dark Side",
        planetName: "Geonosis",
        stars: "Below 1-star",
        action: "Projected total: 21.6M points",
        breakdown: "Side preload if primary lanes overcap",
        advance: "Needs more GP or carryover to unlock safely",
      },
    ],
    notes: [
      { tone: "neutral", text: "Hold fleets for Kashyyyk before widening bonus attempts." },
      { tone: "success", text: "Operations: preloading only, no new platoons required." },
    ],
  },
];

export const operationsDayPickers: OperationsDayPicker[] = [
  { day: 1, pointsEarned: "6.3M", activePlanetCount: 3, summary: "Opening platoons and early preload", planetIds: ["mustafar", "corellia", "coruscant"] },
  { day: 2, pointsEarned: "5.1M", activePlanetCount: 3, summary: "Primary lanes plus Geonosis preload", planetIds: ["bracca", "felucia", "geonosis"] },
  { day: 3, pointsEarned: "3.2M", activePlanetCount: 2, summary: "Selective fills on long-run planets", planetIds: ["kashyyyk", "lothal"] },
];

export const operationsMetrics: OverviewMetric[] = [
  { label: "Projected Platoons", value: "43", tone: "green" },
  { label: "Projected Ops Points", value: "14.6M", tone: "gold" },
  { label: "Definitions Loaded", value: "Full Wiki Set", tone: "neutral" },
  { label: "Roster Coverage", value: "82%", tone: "purple" },
];

export const operationsStages: Record<string, OperationsPlanetStage> = {
  mustafar: {
    id: "mustafar",
    name: "Mustafar",
    zone: "North",
    label: "Dark Side lane",
    todaySummary: "5 slots today | 2 complete",
    stageTitle: "Mustafar - Day 1",
    stageSubtitle: "Focus planet gets first claim on elite Empire and Inquisitor units before any preload spillover.",
    stageMeta: "4 platoons planned | 2 complete | 1 ready | 1 blocked",
    platoons: [
      {
        id: 1,
        status: "complete",
        filled: "6/6 slots filled",
        label: "Full coverage",
        slots: [
          { name: "Grand Inquisitor", assignee: "Crimson Lead", meta: "R8, 3 omicrons" },
          { name: "Reva", assignee: "Echo Sabers", meta: "R7, TB omicron" },
        ],
      },
      {
        id: 2,
        status: "ready",
        filled: "5/6 slots filled",
        label: "One donor pending",
        slots: [
          { name: "Dark Trooper Moff Gideon", assignee: "Blue Squadron", meta: "R7, zetas loaded" },
          { name: "Scout Trooper", assignee: "Unassigned", meta: "Waiting on scan handoff", unassigned: true },
        ],
      },
    ],
  },
  corellia: {
    id: "corellia",
    name: "Corellia",
    zone: "Central",
    label: "Mixed lane",
    todaySummary: "4 slots today | 1 complete",
    stageTitle: "Corellia - Day 1",
    stageSubtitle: "Smuggler and scoundrel donors are prioritized here to keep the mixed lane above the 3-star threshold.",
    stageMeta: "3 platoons planned | 1 complete | 1 partial | 1 impossible",
    platoons: [
      {
        id: 1,
        status: "partial",
        filled: "4/6 slots filled",
        label: "Need two more smugglers",
        slots: [
          { name: "Jabba the Hutt", assignee: "Crimson Lead", meta: "R9, full team intact" },
          { name: "Skiff Guard Lando", assignee: "Outer Rim Ops", meta: "R7, mission conflict tomorrow" },
        ],
      },
      {
        id: 2,
        status: "impossible",
        filled: "2/6 slots filled",
        label: "Blocked by missing marquee units",
        slots: [
          { name: "Boushh Leia", assignee: "Phoenix Trace", meta: "R7 donor available" },
          { name: "Embo", assignee: "Unassigned", meta: "No scanned owner yet", unassigned: true },
        ],
      },
    ],
    missing: {
      title: "Shortfall summary",
      lines: [
        "Need 2 more Aphra-era scoundrels to finish Platoon 2.",
        "Mixed lane loses 2.1M platoon points if the blocked lane stays open.",
      ],
    },
  },
  coruscant: {
    id: "coruscant",
    name: "Coruscant",
    zone: "South",
    label: "Light Side lane",
    todaySummary: "6 slots today | 3 complete",
    stageTitle: "Coruscant - Day 1",
    stageSubtitle: "Galactic Republic overlap is strong enough that this lane can spare a few donors for later preloads.",
    stageMeta: "5 platoons planned | 3 complete | 2 ready",
    platoons: [
      {
        id: 1,
        status: "complete",
        filled: "6/6 slots filled",
        label: "Padme core finished",
        slots: [
          { name: "General Skywalker", assignee: "Moff Archive", meta: "R8, fast set" },
          { name: "Commander Ahsoka Tano", assignee: "Crimson Lead", meta: "R9, mission-safe donor" },
        ],
      },
      {
        id: 2,
        status: "ready",
        filled: "5/6 slots filled",
        label: "One support donor pending",
        slots: [
          { name: "Ki-Adi-Mundi", assignee: "Alderaan East", meta: "R7, ready after combat" },
          { name: "Barriss Offee", assignee: "Unassigned", meta: "Placeholder donor", unassigned: true },
        ],
      },
    ],
  },
  bracca: {
    id: "bracca",
    name: "Bracca",
    zone: "North",
    label: "Dark Side lane",
    todaySummary: "3 slots today | 1 complete",
    stageTitle: "Bracca - Day 2",
    stageSubtitle: "Secondary Dark Side donors start to compete with mission teams, so the lane is staged more conservatively.",
    stageMeta: "3 platoons planned | 1 complete | 1 partial | 1 ready",
    platoons: [
      {
        id: 1,
        status: "complete",
        filled: "6/6 slots filled",
        label: "Opening block secured",
        slots: [
          { name: "Lord Vader", assignee: "Crimson Lead", meta: "R9, no mission conflict" },
          { name: "Royal Guard", assignee: "Hidden Path", meta: "R7, donor confirmed" },
        ],
      },
      {
        id: 2,
        status: "partial",
        filled: "4/6 slots filled",
        label: "Fleet overlap causing tension",
        slots: [
          { name: "Executor", assignee: "Blue Squadron", meta: "Fleet locked until after combat" },
          { name: "TIE Dagger", assignee: "Unassigned", meta: "No spare donor", unassigned: true },
        ],
      },
    ],
  },
  felucia: {
    id: "felucia",
    name: "Felucia",
    zone: "Central",
    label: "Mixed lane",
    todaySummary: "2 slots today | 0 complete",
    stageTitle: "Felucia - Day 2",
    stageSubtitle: "Mixed leftovers are used here after the Corellia focus lane finishes drawing first priority donors.",
    stageMeta: "2 platoons planned | 1 ready | 1 impossible",
    platoons: [
      {
        id: 1,
        status: "ready",
        filled: "5/6 slots filled",
        label: "One donor away",
        slots: [
          { name: "Merrin", assignee: "Phoenix Trace", meta: "R7 donor ready" },
          { name: "Taron Malicos", assignee: "Unassigned", meta: "Missing owner", unassigned: true },
        ],
      },
      {
        id: 2,
        status: "impossible",
        filled: "1/6 slots filled",
        label: "No guild depth on this set",
        slots: [
          { name: "Doctor Aphra", assignee: "Outer Rim Ops", meta: "Only copy available" },
          { name: "BT-1", assignee: "Unassigned", meta: "No scanned copy", unassigned: true },
        ],
      },
    ],
  },
  geonosis: {
    id: "geonosis",
    name: "Geonosis",
    zone: "Bonus",
    label: "Bonus preload lane",
    todaySummary: "1 slot today | 0 complete",
    stageTitle: "Geonosis - Day 2",
    stageSubtitle: "The bonus lane is only taking low-conflict donors while primary lanes remain under pressure.",
    stageMeta: "1 platoon planned | preload only",
    platoons: [
      {
        id: 1,
        status: "ready",
        filled: "3/6 slots filled",
        label: "Low-risk preload",
        slots: [
          { name: "Geonosian Brood Alpha", assignee: "Echo Sabers", meta: "R7, still combat-safe" },
          { name: "Sun Fac", assignee: "Moff Archive", meta: "R5, optional donor" },
        ],
      },
    ],
  },
  kashyyyk: {
    id: "kashyyyk",
    name: "Kashyyyk",
    zone: "South",
    label: "Light Side lane",
    todaySummary: "2 slots today | 1 complete",
    stageTitle: "Kashyyyk - Day 3",
    stageSubtitle: "Leia and Galactic Republic support are enough to keep the Light Side lane on pace while spare donors trickle in.",
    stageMeta: "2 platoons planned | 1 complete | 1 partial",
    platoons: [
      {
        id: 1,
        status: "complete",
        filled: "6/6 slots filled",
        label: "Leia block finished",
        slots: [
          { name: "Princess Leia", assignee: "Crimson Lead", meta: "R9, donor preserved" },
          { name: "Captain Rex", assignee: "Alderaan East", meta: "R7, combat complete" },
        ],
      },
      {
        id: 2,
        status: "partial",
        filled: "4/6 slots filled",
        label: "Waiting on support Jedi",
        slots: [
          { name: "Jedi Knight Cal", assignee: "Blue Squadron", meta: "R8 donor available" },
          { name: "Hermit Yoda", assignee: "Unassigned", meta: "No free donor yet", unassigned: true },
        ],
      },
    ],
  },
  lothal: {
    id: "lothal",
    name: "Lothal",
    zone: "South",
    label: "Preload lane",
    todaySummary: "1 slot today | 0 complete",
    stageTitle: "Lothal - Day 3",
    stageSubtitle: "Fallback lane used for low-priority preload after main Light Side goals are met.",
    stageMeta: "1 platoon planned | preload only",
    platoons: [
      {
        id: 1,
        status: "ready",
        filled: "2/6 slots filled",
        label: "Spare donor pool",
        slots: [
          { name: "Hera Syndulla", assignee: "Phoenix Trace", meta: "R7, optional donor" },
          { name: "Sabine Wren", assignee: "Outer Rim Ops", meta: "R7, optional donor" },
        ],
      },
    ],
  },
};

export const guideMembers = [
  "Crimson Lead",
  "Echo Sabers",
  "Blue Squadron",
  "Outer Rim Ops",
];

export const guidePlanets: GuidePlanetListItem[] = [
  {
    id: "mustafar",
    name: "Mustafar",
    align: "ds",
    phase: 1,
    squadCount: 4,
    missions: [
      { id: "cm1", label: "CM 1", type: "combat", squadCount: 2 },
      { id: "fleet", label: "Fleet", type: "fleet", squadCount: 1 },
      { id: "sm1", label: "Special Mission", type: "special", squadCount: 1 },
    ],
  },
  {
    id: "corellia",
    name: "Corellia",
    align: "mx",
    phase: 1,
    squadCount: 3,
    missions: [
      { id: "cm1", label: "CM 1", type: "combat", squadCount: 2 },
      { id: "cm2", label: "CM 2", type: "combat", squadCount: 1 },
    ],
  },
  {
    id: "coruscant",
    name: "Coruscant",
    align: "ls",
    phase: 1,
    squadCount: 5,
    missions: [
      { id: "cm1", label: "CM 1", type: "combat", squadCount: 2 },
      { id: "fleet", label: "Fleet", type: "fleet", squadCount: 1 },
      { id: "sm1", label: "Special Mission", type: "special", squadCount: 2 },
    ],
  },
  {
    id: "bracca",
    name: "Bracca",
    align: "ds",
    phase: 2,
    squadCount: 2,
    missions: [
      { id: "cm1", label: "CM 1", type: "combat", squadCount: 1 },
      { id: "fleet", label: "Fleet", type: "fleet", squadCount: 1 },
    ],
  },
];

export function guideMissionKey(planetId: string, missionId: string) {
  return `${planetId}:${missionId}`;
}

export const guideMissionDetails: Record<string, GuideMissionDetail> = {
  [guideMissionKey("mustafar", "cm1")]: {
    planetId: "mustafar",
    missionId: "cm1",
    planetName: "Mustafar",
    align: "ds",
    missionName: "CM 1",
    missionTypeLabel: "Combat Mission",
    requirement: "Phase 1 - R5+ required",
    summary: "Empire and Inquisitor squads do the heavy lifting here, with one safety net comp for lower relic accounts.",
    squads: [
      {
        id: "lv-core",
        title: "Primary Team",
        difficulty: "auto",
        readiness: "Ready for Crimson Lead",
        leader: "Lord Vader",
        members: ["Maul", "Royal Guard", "Darth Vader", "Piett"],
        omicrons: ["Reva - Inquisitorius", "Grand Inquisitor - Ready for Battle"],
        notes: "Lead with the durable opener and save Maul for the second-wave cleanup burst.",
        videoLabel: "Video guide - Full clear walkthrough",
      },
      {
        id: "inq-second",
        title: "Fallback Team",
        difficulty: "medium",
        readiness: "2 units missing for Outer Rim Ops",
        leader: "Grand Inquisitor",
        members: ["Reva", "Seventh Sister", "Eighth Brother", "Ninth Sister"],
        omicrons: ["Reva - Inquisitorius"],
        notes: "Use when Lord Vader is committed elsewhere. Mod for survivability over speed.",
        videoLabel: "Video guide - Safer fallback route",
      },
    ],
  },
  [guideMissionKey("corellia", "cm1")]: {
    planetId: "corellia",
    missionId: "cm1",
    planetName: "Corellia",
    align: "mx",
    missionName: "CM 1",
    missionTypeLabel: "Combat Mission",
    requirement: "Phase 1 - R5+ required",
    summary: "Mixed lane opener focused on Jabba scoundrels and durable neutral utility.",
    squads: [
      {
        id: "jabba-line",
        title: "Primary Team",
        difficulty: "easy",
        readiness: "Ready for Echo Sabers",
        leader: "Jabba the Hutt",
        members: ["Boushh Leia", "Krrsantan", "Skiff Guard Lando", "Boba Fett"],
        omicrons: [],
        notes: "Stall early, then unload contract pieces once turn meter starts to snowball.",
        videoLabel: "Video guide - Contract-first approach",
      },
    ],
  },
  [guideMissionKey("coruscant", "sm1")]: {
    planetId: "coruscant",
    missionId: "sm1",
    planetName: "Coruscant",
    align: "ls",
    missionName: "Special Mission",
    missionTypeLabel: "Special Mission",
    requirement: "Phase 1 - R7+ required",
    summary: "Guide-only mission with a tighter relic floor and specific omicron checks.",
    squads: [
      {
        id: "padme-special",
        title: "Unlock Team",
        difficulty: "hard",
        readiness: "1 omicron missing for Blue Squadron",
        leader: "Padme Amidala",
        members: ["General Kenobi", "Jedi Knight Anakin", "Ahsoka Tano", "C-3PO"],
        omicrons: ["Ahsoka Tano - Territory Battle Readiness"],
        notes: "Keep protection up and avoid overcommitting cooldowns before the final wave.",
        videoLabel: "Video guide - Unlock mission timing",
      },
    ],
  },
};

export const guideModalOmicrons = [
  "Reva - Inquisitorius",
  "Ahsoka Tano - Territory Battle Readiness",
  "Grand Inquisitor - Ready for Battle",
];

export const rosterMembers: RosterMember[] = [
  {
    id: "crimson-lead",
    label: "Crimson Lead",
    summary: "18 units | 12 characters | 6 ships | 6 R7+ | 9 R5+",
    characters: [
      { name: "Lord Vader", type: "Character", stars: "7", level: "R9", power: "39,812", abilities: ["4 zeta", "1 omicron"] },
      { name: "Reva", type: "Character", stars: "7", level: "R8", power: "35,104", abilities: ["3 zeta", "1 omicron"] },
      { name: "Jabba the Hutt", type: "Character", stars: "7", level: "R9", power: "37,992", abilities: ["4 zeta"] },
      { name: "Princess Leia", type: "Character", stars: "7", level: "R9", power: "38,406", abilities: ["4 zeta", "1 omicron"] },
      { name: "General Skywalker", type: "Character", stars: "7", level: "R8", power: "34,220", abilities: ["4 zeta"] },
      { name: "Commander Ahsoka Tano", type: "Character", stars: "7", level: "R9", power: "36,912", abilities: ["3 zeta"] },
    ],
    ships: [
      { name: "Executor", type: "Ship", stars: "7", level: "-", power: "210,144", abilities: ["Crew synced"] },
      { name: "Leviathan", type: "Ship", stars: "7", level: "-", power: "205,088", abilities: ["Crew synced"] },
      { name: "Profundity", type: "Ship", stars: "7", level: "-", power: "198,760", abilities: ["Crew synced"] },
    ],
  },
  {
    id: "echo-sabers",
    label: "Echo Sabers",
    summary: "15 units | 10 characters | 5 ships | 4 R7+ | 7 R5+",
    characters: [
      { name: "Grand Inquisitor", type: "Character", stars: "7", level: "R7", power: "31,440", abilities: ["4 zeta", "1 omicron"] },
      { name: "Darth Malgus", type: "Character", stars: "7", level: "R8", power: "33,118", abilities: ["4 zeta", "1 omicron"] },
      { name: "Merrin", type: "Character", stars: "7", level: "R7", power: "28,774", abilities: ["2 zeta"] },
      { name: "Bo-Katan Kryze", type: "Character", stars: "7", level: "R7", power: "29,440", abilities: ["3 zeta"] },
      { name: "Jedi Knight Cal", type: "Character", stars: "7", level: "R8", power: "34,112", abilities: ["4 zeta"] },
    ],
    ships: [
      { name: "Raven's Claw", type: "Ship", stars: "7", level: "-", power: "92,551", abilities: ["Crew synced"] },
      { name: "TIE Dagger", type: "Ship", stars: "7", level: "-", power: "88,210", abilities: ["Crew synced"] },
    ],
  },
];
