import { Fragment, useState } from "react";
import { usePlannerStore } from "../../state/plannerStoreCore";
import {
  type Alignment,
  type GuideDifficulty,
  dayPlanAlgorithms,
  dayPlanCards,
  dailyUndeployedRows,
  guideMembers,
  guideMissionDetails,
  guideMissionKey,
  guideModalOmicrons,
  guidePlanets,
  operationsDayPickers,
  operationsStages,
  overviewMembers,
  overviewMetrics,
  plannerChains,
  rosterMembers,
} from "./mockData";
import {
  buildOperationsMetrics,
  buildOperationsStage,
  buildOverviewMembers,
  buildPlanetOptions,
  buildRosterMembers,
  filterRosterUnits,
  formatMillions,
} from "./runtimeViewModels";
import styles from "./PlannerUi.module.scss";

function toneClassName(tone: "gold" | "green" | "purple" | "neutral") {
  if (tone === "gold") return styles.metricValueGold;
  if (tone === "green") return styles.metricValueGreen;
  if (tone === "purple") return styles.metricValuePurple;
  return styles.metricValue;
}

function alignBadgeClassName(align: Alignment, bonusLocked?: boolean) {
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

function dayChainClassName(align: Alignment) {
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

function rosterUnitsForDisplay(memberId: string) {
  return rosterMembers.find((member) => member.id === memberId) ?? rosterMembers[0];
}

function guideDifficultyClassName(difficulty: GuideDifficulty) {
  return `${styles.difficultyBadge} ${
    difficulty === "auto"
      ? styles.difficultyAuto
      : difficulty === "easy"
        ? styles.difficultyEasy
        : difficulty === "medium"
          ? styles.difficultyMedium
          : styles.difficultyHard
  }`;
}

function operationsStatusClassName(status: string) {
  if (status === "complete") return `${styles.platoonCard} ${styles.platoonCardComplete}`;
  if (status === "partial") return `${styles.platoonCard} ${styles.platoonCardPartial}`;
  if (status === "impossible") return `${styles.platoonCard} ${styles.platoonCardImpossible}`;
  return `${styles.platoonCard} ${styles.platoonCardReady}`;
}

export function GuildOverviewPage() {
  const primaryAllyCode = usePlannerStore((state) => state.primaryAllyCode);
  const guildSummary = usePlannerStore((state) => state.guildSummary);
  const guildRosters = usePlannerStore((state) => state.guildRosters);
  const isFetchingGuild = usePlannerStore((state) => state.isFetchingGuild);
  const isScanningRosters = usePlannerStore((state) => state.isScanningRosters);
  const statusMessage = usePlannerStore((state) => state.statusMessage);
  const lastSyncAt = usePlannerStore((state) => state.lastSyncAt);
  const opsAnalysis = usePlannerStore((state) => state.opsAnalysis);
  const setPrimaryAllyCode = usePlannerStore((state) => state.setPrimaryAllyCode);
  const fetchGuildByAllyCode = usePlannerStore((state) => state.fetchGuildByAllyCode);
  const scanGuildRosters = usePlannerStore((state) => state.scanGuildRosters);

  const [draftAllyCode, setDraftAllyCode] = useState(primaryAllyCode || "658-388-776");
  const liveMembers = buildOverviewMembers(guildSummary, guildRosters);
  const displayedMembers = liveMembers.length ? liveMembers : overviewMembers;
  const scannedCount = Object.keys(guildRosters).length;
  const totalMembers = guildSummary?.members.length ?? 0;
  const totalPlatoons = opsAnalysis ? Object.values(opsAnalysis).flat().length : 0;
  const fillablePlatoons = opsAnalysis
    ? Object.values(opsAnalysis)
        .flat()
        .filter((platoon) => platoon.fillable).length
    : 0;
  const dynamicMetrics = guildSummary
    ? [
        { label: "Est. Stars", value: totalPlatoons ? `${fillablePlatoons}` : "—", tone: "gold" as const },
        {
          label: "Ops Filled",
          value: totalPlatoons ? `${fillablePlatoons} / ${totalPlatoons}` : `${scannedCount} / ${totalMembers}`,
          tone: "green" as const,
        },
      ]
    : overviewMetrics.slice(0, 2);

  return (
    <section className={styles.panel}>
      <div className={styles.panelCard}>
        <div className={styles.cardTitle}>Live Guild Import</div>
        <div className={styles.importBanner}>
          <div className={styles.importIcon}>LINK</div>
          <div className={styles.importText}>
            <h3>Import directly from the game</h3>
            <p>
              Enter any guild member&apos;s ally code to fetch guild GP, member
              list, and roster data.
            </p>
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
          {displayedMembers.map((member) => (
            <article key={member.name} className={styles.memberCard}>
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
            <input className={styles.input} value={guildSummary?.gp ?? 452750000} readOnly />
            <small className={styles.fieldHint}>Auto-filled on import. Edit if needed.</small>
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Active Members</span>
            <input className={styles.input} value={guildSummary?.members.length ?? 49} readOnly />
          </label>

          <div className={styles.metricGrid}>
            {dynamicMetrics.map((metric) => (
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
            <button type="button" className={`${styles.toggleButton} ${styles.toggleButtonActive}`}>
              % Rate
            </button>
            <button type="button" className={styles.toggleButton}>
              # Count
            </button>
          </div>

          <div className={styles.twoColumnGrid}>
            <label className={styles.field}>
              <span className={styles.label}>CM base %</span>
              <input className={styles.input} defaultValue="70" />
              <small className={styles.fieldHint}>Day 1 / first planet</small>
            </label>
            <label className={styles.field}>
              <span className={styles.label}>CM falloff % per planet</span>
              <input className={styles.input} defaultValue="10" />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>Fleet base %</span>
              <input className={styles.input} defaultValue="50" />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>Fleet falloff % per planet</span>
              <input className={styles.input} defaultValue="15" />
            </label>
          </div>

          <div className={styles.vizTitle}>Rate by planet depth</div>
          <div className={styles.falloffViz}>
            {[70, 60, 50, 40, 30, 20].map((height, index) => (
              <span key={height} className={styles.vizBar} style={{ height: `${height}%` }}>
                D{index + 1}
              </span>
            ))}
          </div>

          <button type="button" className={`${styles.primaryButton} ${styles.fullButton}`}>
            Apply to Planet Planner
          </button>
        </div>

        <div className={styles.panelCard}>
          <div className={styles.cardTitle}>Daily Undeployed GP</div>
          <div className={styles.toggleGroup}>
            <button type="button" className={`${styles.toggleButton} ${styles.toggleButtonActive}`}>
              % of GP
            </button>
            <button type="button" className={styles.toggleButton}>
              Flat GP
            </button>
          </div>

          <table className={styles.dailyTable}>
            <thead>
              <tr>
                <th>Day</th>
                <th>Undeployed %</th>
                <th>Effective GP</th>
              </tr>
            </thead>
            <tbody>
              {dailyUndeployedRows.map((row) => (
                <tr key={row.day}>
                  <td>D{row.day}</td>
                  <td>
                    <input className={styles.tableInput} defaultValue={row.value.replace("%", "")} />
                  </td>
                  <td>
                    {guildSummary
                      ? formatMillions(
                          guildSummary.gp * (1 - Number(row.value.replace("%", "")) / 100),
                        )
                      : row.effectiveGp}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className={styles.noteText}>
            {lastSyncAt
              ? `Last live sync: ${new Date(lastSyncAt).toLocaleString()}`
              : "No live scan completed yet."}
          </div>
        </div>
      </div>
    </section>
  );
}

export function PlanetPlannerPage() {
  const selectedChain = usePlannerStore((state) => state.selectedChain);
  const setSelectedChain = usePlannerStore((state) => state.setSelectedChain);
  const cards = plannerChains[selectedChain];

  return (
    <section className={styles.panel}>
      <div className={styles.plannerToolbar}>
        <div className={styles.chainSelect}>
          <button
            type="button"
            className={`${styles.chainButton} ${selectedChain === "ds" ? styles.chainButtonDsActive : ""}`}
            onClick={() => setSelectedChain("ds")}
          >
            Dark Side
          </button>
          <button
            type="button"
            className={`${styles.chainButton} ${selectedChain === "mx" ? styles.chainButtonMxActive : ""}`}
            onClick={() => setSelectedChain("mx")}
          >
            Mixed
          </button>
          <button
            type="button"
            className={`${styles.chainButton} ${selectedChain === "ls" ? styles.chainButtonLsActive : ""}`}
            onClick={() => setSelectedChain("ls")}
          >
            Light Side
          </button>
        </div>
      </div>

      <div className={styles.chainStack}>
        {cards.map((planet, index) => (
          <div key={planet.id} className={styles.planetRow}>
            <div className={styles.chainColumn}>
              {index > 0 ? (
                <div
                  className={`${styles.chainSegment} ${
                    selectedChain === "ds"
                      ? styles.chainSegmentDs
                      : selectedChain === "mx"
                        ? styles.chainSegmentMx
                        : styles.chainSegmentLs
                  }`}
                />
              ) : null}
              <div
                className={`${styles.chainDot} ${
                  selectedChain === "ds"
                    ? styles.chainDotDs
                    : selectedChain === "mx"
                      ? styles.chainDotMx
                      : styles.chainDotLs
                }`}
              />
              {index < cards.length - 1 ? (
                <div
                  className={`${styles.chainSegment} ${
                    planet.align === "bonus"
                      ? styles.chainSegmentBonus
                      : selectedChain === "ds"
                        ? styles.chainSegmentDs
                        : selectedChain === "mx"
                          ? styles.chainSegmentMx
                          : styles.chainSegmentLs
                  }`}
                />
              ) : null}
            </div>

            <article
              className={`${styles.planetCard} ${
                planet.align === "ds"
                  ? styles.planetCardDs
                  : planet.align === "mx"
                    ? styles.planetCardMx
                    : planet.align === "ls"
                      ? styles.planetCardLs
                      : styles.planetCardBonus
              } ${
                planet.status === "s3"
                  ? styles.planetCardS3
                  : planet.status === "s2"
                    ? styles.planetCardS2
                    : planet.status === "s1"
                      ? styles.planetCardS1
                      : styles.planetCardLocked
              }`}
            >
              <div className={styles.planetHeader}>
                <div>
                  <div className={styles.planetName}>{planet.name}</div>
                  <div className={styles.planetCapability}>{planet.capability}</div>
                </div>
                <span className={alignBadgeClassName(planet.align, planet.bonusLocked)}>
                  {planet.align === "bonus"
                    ? planet.bonusLocked
                      ? "Bonus Locked"
                      : "Bonus"
                    : planet.align === "ds"
                      ? "Dark"
                      : planet.align === "mx"
                        ? "Mixed"
                        : "Light"}
                </span>
              </div>

              <div className={styles.starsRow}>
                {[0, 1, 2].map((star) => (
                  <span
                    key={star}
                    className={`${styles.star} ${
                      planet.status === "s3" ||
                      (planet.status === "s2" && star < 2) ||
                      (planet.status === "s1" && star < 1)
                        ? styles.starActive
                        : ""
                    }`}
                  >
                    Star
                  </span>
                ))}
              </div>

              <div className={styles.pointsRow}>
                Est: <strong>{planet.estimate}</strong> / {planet.target} (3-star)
              </div>
              <div className={styles.progressBar}>
                <div className={styles.progressFill} style={{ width: `${planet.progress}%` }} />
              </div>

              <div className={styles.missionSection}>
                <div className={styles.missionHeader}>
                  Combat / Special Missions ({planet.combatMissions.length})
                </div>
                {planet.combatMissions.map((mission) => (
                  <div key={mission.label} className={styles.missionEstimateRow}>
                    <span>{mission.label}</span>
                    <div>
                      <div className={styles.miniLabel}>Clear %</div>
                      <div className={styles.miniValue}>{mission.completion}</div>
                    </div>
                    <div>
                      <div className={styles.miniLabel}>est pts</div>
                      <div className={styles.miniValue}>{mission.points}</div>
                    </div>
                  </div>
                ))}
                {planet.fleetMissions.map((mission) => (
                  <div key={mission.label} className={styles.missionEstimateRow}>
                    <span>{mission.label}</span>
                    <div>
                      <div className={styles.miniLabel}>Comp %</div>
                      <div className={styles.miniValue}>{mission.completion}</div>
                    </div>
                    <div>
                      <div className={styles.miniLabel}>est pts</div>
                      <div className={styles.miniValue}>{mission.points}</div>
                    </div>
                  </div>
                ))}
              </div>

              <div className={styles.missionHeader}>Operations</div>
              <div className={styles.operationsRow}>
                {planet.operations.map((isOn, slotIndex) => (
                  <span
                    key={`${planet.id}-ops-${slotIndex}`}
                    className={`${styles.operationsPill} ${isOn ? styles.operationsPillOn : ""}`}
                  >
                    {slotIndex + 1}
                  </span>
                ))}
              </div>
              <div className={styles.noteText}>{planet.operationsNote}</div>
              <div className={styles.planetNote}>{planet.note}</div>
            </article>

            {planet.align === "bonus" ? <div className={styles.bonusConnector} /> : null}
          </div>
        ))}
      </div>
    </section>
  );
}

export function DayByDayPlanPage() {
  return (
    <section className={styles.panel}>
      <div className={`${styles.panelCard} ${styles.warningCard}`}>
        <div className={styles.warningHeader}>
          <div>
            <div className={styles.cardTitle}>Optimizer Warning</div>
            <div className={styles.warningCopy}>
              These optimization passes can take a long time once roster scans
              and operations assignments are folded into the search.
            </div>
            <div className={styles.warningNote}>
              Greedy is the fast preview option. PSO and GA are the serious
              planning passes. Adam and All Algorithms are long unattended runs.
            </div>
          </div>
          <button type="button" className={styles.primaryButton}>
            I Understand
          </button>
        </div>

        <div className={styles.algorithmGrid}>
          {dayPlanAlgorithms.map((algorithm) => (
            <article key={algorithm.id} className={styles.algorithmCard}>
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
          { label: "Total Est. Stars", value: "35", tone: "gold" as const },
          { label: "Max Possible", value: "39", tone: "neutral" as const },
          { label: "Bonus Planets", value: "2 Active", tone: "purple" as const },
          { label: "Ops Filled", value: "43", tone: "green" as const },
        ].map((metric) => (
          <article key={metric.label} className={styles.metricCard}>
            <div className={styles.metricLabel}>{metric.label}</div>
            <div className={`${styles.metricValue} ${toneClassName(metric.tone)}`}>
              {metric.value}
            </div>
          </article>
        ))}
      </div>

      <div className={styles.controlsGrid}>
        <select className={styles.selectControl} defaultValue="">
          <option value="">Choose an optimization algorithm...</option>
          {dayPlanAlgorithms.map((algorithm) => (
            <option key={algorithm.id} value={algorithm.id}>
              {algorithm.label}
            </option>
          ))}
        </select>

        <div className={styles.progressButtonWrap}>
          <div className={styles.progressFillBg} />
          <button type="button" className={styles.primaryButton}>
            Run Optimization
          </button>
        </div>
      </div>

      <div className={styles.statusLine}>
        Select an algorithm and click Run to generate the optimal TB plan.
      </div>

      {dayPlanCards.map((day) => (
        <article key={day.day} className={styles.dayBlock}>
          <div className={styles.dayBlockHeader}>
            <div className={styles.dayTitle}>Day {day.day}</div>
            <div className={styles.dayMeta}>
              <span>GP: {day.gpAvailable} avail / {day.gpUsed} used</span>
              <span>{day.starsEarned}</span>
            </div>
          </div>

          <div className={styles.dayChainsGrid}>
            {day.chainCards.map((card) => (
              <div key={`${day.day}-${card.title}-${card.planetName}`} className={dayChainClassName(card.align)}>
                <div className={styles.dayChainTitle}>{card.title}</div>
                <div className={styles.dayChainPlanet}>{card.planetName}</div>
                <div className={styles.dayChainStars}>{card.stars}</div>
                <div className={styles.dayChainAction}>{card.action}</div>
                <div className={styles.dayChainBreakdown}>{card.breakdown}</div>
                <div className={styles.dayChainAdvance}>{card.advance}</div>
              </div>
            ))}
          </div>

          <div className={styles.notesBlock}>
            {day.notes.map((note) => (
              <div
                key={`${day.day}-${note.text}`}
                className={`${styles.noteLine} ${
                  note.tone === "bonus"
                    ? styles.noteLineBonus
                    : note.tone === "success"
                      ? styles.noteLineSuccess
                      : ""
                }`}
              >
                {note.text}
              </div>
            ))}
          </div>
        </article>
      ))}
    </section>
  );
}

export function OperationsPage() {
  const opsAnalysis = usePlannerStore((state) => state.opsAnalysis);
  const opsDefinitions = usePlannerStore((state) => state.opsDefinitions);
  const guildRosters = usePlannerStore((state) => state.guildRosters);
  const selectedOperationsDay = usePlannerStore((state) => state.selectedOperationsDay);
  const selectedOperationsPlanetId = usePlannerStore((state) => state.selectedOperationsPlanetId);
  const isLoadingOps = usePlannerStore((state) => state.isLoadingOps);
  const setSelectedOperationsDay = usePlannerStore((state) => state.setSelectedOperationsDay);
  const setSelectedOperationsPlanetId = usePlannerStore((state) => state.setSelectedOperationsPlanetId);
  const loadOpsDefinitions = usePlannerStore((state) => state.loadOpsDefinitions);
  const analyzePlatoons = usePlannerStore((state) => state.analyzePlatoons);

  const liveMetrics = buildOperationsMetrics(opsAnalysis, guildRosters, opsDefinitions);
  const livePlanetIds = buildPlanetOptions(opsAnalysis);
  const hasLiveAnalysis = livePlanetIds.length > 0;
  const selectedDay =
    operationsDayPickers.find((day) => day.day === selectedOperationsDay) ??
    operationsDayPickers[0];
  const selectedStage =
    buildOperationsStage(selectedOperationsPlanetId, opsAnalysis) ??
    operationsStages[selectedOperationsPlanetId];
  const planetIds = hasLiveAnalysis ? livePlanetIds : selectedDay.planetIds;

  return (
    <section className={styles.panel}>
      <div className={styles.metricGrid}>
        {liveMetrics.map((metric) => (
          <article key={metric.label} className={styles.metricCard}>
            <div className={styles.metricLabel}>{metric.label}</div>
            <div className={`${styles.metricValue} ${toneClassName(metric.tone)}`}>
              {metric.value}
            </div>
          </article>
        ))}
      </div>

      <div className={styles.panelCard}>
        <div className={styles.cardTitle}>Operations Planner</div>
        <div className={styles.cardSubtitle}>
          Platoons are now analyzed from the Rust backend using the bundled wiki
          definitions and the current scanned roster session.
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
          {operationsDayPickers.map((day) => (
            <button
              key={day.day}
              type="button"
              className={`${styles.dayPickerCard} ${
                day.day === selectedDay.day ? styles.dayPickerCardActive : ""
              }`}
              onClick={() => setSelectedOperationsDay(day.day)}
            >
              <div className={styles.dayPickerHead}>
                <div className={styles.dayPickerTitle}>Day {day.day}</div>
                <div className={styles.dayPickerPoints}>{day.pointsEarned}</div>
              </div>
              <div className={styles.dayPickerKicker}>
                {day.activePlanetCount} active planet{day.activePlanetCount === 1 ? "" : "s"}
              </div>
              <div className={styles.dayPickerSub}>{day.summary}</div>
            </button>
          ))}
        </div>

        <div className={styles.opsMainPane}>
          <div className={styles.planetStrip}>
            {planetIds.map((planetId) => {
              const liveStage = buildOperationsStage(planetId, opsAnalysis);
              const legacyStage = operationsStages[planetId];
              const pillName = liveStage
                ? liveStage.stageTitle.split(" - ")[0]
                : legacyStage.name;
              const pillMeta = liveStage
                ? "Live analysis"
                : `${legacyStage.label} | Zone ${legacyStage.zone}`;
              const pillToday = liveStage ? liveStage.stageMeta : legacyStage.todaySummary;
              return (
                <button
                  key={planetId}
                  type="button"
                  className={`${styles.planetPill} ${
                    planetId === selectedOperationsPlanetId ? styles.planetPillActive : ""
                  }`}
                  onClick={() => setSelectedOperationsPlanetId(planetId)}
                >
                  <div className={styles.planetPillName}>{pillName}</div>
                  <div className={styles.planetPillMeta}>{pillMeta}</div>
                  <div className={styles.planetPillToday}>{pillToday}</div>
                </button>
              );
            })}
          </div>

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
                      <div key={`${platoon.id}-${slot.name}`} className={styles.slotCard}>
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

            {selectedStage.missing ? (
              <div className={styles.missingCard}>
                <div className={styles.missingTitle}>{selectedStage.missing.title}</div>
                {selectedStage.missing.lines.map((line) => (
                  <div key={line} className={styles.missingLine}>
                    {line}
                  </div>
                ))}
              </div>
            ) : null}
          </article>
        </div>
      </div>
    </section>
  );
}

export function GuidesPage() {
  const guildSummary = usePlannerStore((state) => state.guildSummary);
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

  const guideDetail =
    guideMissionDetails[
      guideMissionKey(
        selectedGuideMission.planetId,
        selectedGuideMission.missionId,
      )
    ] ?? guideMissionDetails[guideMissionKey("mustafar", "cm1")];

  const phaseGroups = Array.from(new Set(guidePlanets.map((planet) => planet.phase))).sort(
    (left, right) => left - right,
  );
  const guideMemberOptions =
    guildSummary?.members.map((member) => member.displayName) ?? guideMembers;

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
              {guideMemberOptions.map((member) => (
                <option key={member} value={member}>
                  {member}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className={styles.actionRow}>
          <button type="button" className={styles.secondaryButton}>
            Save Guide
          </button>
          <button type="button" className={styles.secondaryButton}>
            Load Guide
          </button>
        </div>
      </div>

      <div className={styles.guideLayout}>
        <aside className={styles.guideSidebar}>
          {phaseGroups.map((phase) => (
            <Fragment key={phase}>
              <div className={styles.phaseHeader}>Phase {phase}</div>
              {guidePlanets
                .filter((planet) => planet.phase === phase)
                .map((planet) => {
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
                        <span className={styles.guidePlanetName}>{planet.name}</span>
                        <span className={styles.guidePlanetCount}>{planet.squadCount}</span>
                      </button>

                      {isExpanded ? (
                        <div>
                          {planet.missions.map((mission) => {
                            const active =
                              selectedGuideMission.planetId === planet.id &&
                              selectedGuideMission.missionId === mission.id;

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
                                  {mission.type === "special"
                                    ? "SM"
                                    : mission.type === "fleet"
                                      ? "FL"
                                      : "CM"}
                                </span>
                                <span>{mission.label}</span>
                                <span className={styles.guidePlanetCount}>{mission.squadCount}</span>
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
          <div className={styles.missionPanelHero}>
            <div>
              <div className={styles.missionPanelTitle}>
                {guideDetail.planetName} - {guideDetail.missionName}
              </div>
              <div className={styles.missionPanelMeta}>
                {guideDetail.missionTypeLabel} | {guideDetail.requirement}
              </div>
              <div className={styles.missionPanelCopy}>{guideDetail.summary}</div>
            </div>
            <button
              type="button"
              className={styles.primaryButton}
              onClick={() => openGuideEditor("auto")}
            >
              Add Squad
            </button>
          </div>

          {guideDetail.squads.map((squad) => (
            <article key={squad.id} className={styles.squadCard}>
              <div className={styles.squadCardHeader}>
                <div>
                  <div className={styles.squadCardTitle}>{squad.title}</div>
                  <div className={styles.readinessText}>{squad.readiness}</div>
                </div>
                <span className={guideDifficultyClassName(squad.difficulty)}>
                  {squad.difficulty}
                </span>
              </div>

              <div className={styles.squadSection}>
                <span className={styles.squadSectionLabel}>Leader</span>
                <span className={styles.squadSectionValue}>{squad.leader}</span>
              </div>
              <div className={styles.squadSection}>
                <span className={styles.squadSectionLabel}>Members</span>
                <span className={styles.squadSectionValue}>{squad.members.join(", ")}</span>
              </div>

              {squad.omicrons.length ? (
                <div className={styles.omicronList}>
                  {squad.omicrons.map((omicron) => (
                    <span key={omicron} className={styles.omicronBadge}>
                      {omicron}
                    </span>
                  ))}
                </div>
              ) : null}

              <div className={styles.squadNotes}>{squad.notes}</div>
              <button
                type="button"
                className={styles.linkButton}
                onClick={() => openGuideEditor(squad.difficulty)}
              >
                {squad.videoLabel}
              </button>
            </article>
          ))}
        </div>
      </div>

      {guideEditorOpen ? (
        <div className={styles.modalBackdrop}>
          <div className={styles.modalCard}>
            <div className={styles.modalHeader}>
              <div className={styles.modalTitle}>Add Squad</div>
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
                      guideEditorDifficulty === difficulty ? styles.difficultyButtonActive : ""
                    }`}
                    onClick={() => setGuideEditorDifficulty(difficulty)}
                  >
                    {difficulty}
                  </button>
                ))}
              </div>
            </div>

            <label className={styles.modalField}>
              <span className={styles.label}>Squad Leader</span>
              <input className={styles.modalInput} defaultValue="Lord Vader" />
            </label>

            <div className={styles.modalSlotsGrid}>
              {["Member 2", "Member 3", "Member 4", "Member 5"].map((label) => (
                <label key={label} className={styles.modalField}>
                  <span className={styles.label}>{label}</span>
                  <input className={styles.modalInput} defaultValue={label === "Member 2" ? "Maul" : ""} />
                </label>
              ))}
            </div>

            <div className={styles.modalField}>
              <div className={styles.label}>Required Territory Battle Omicrons</div>
              <div className={styles.omicronChecklist}>
                {guideModalOmicrons.map((omicron) => (
                  <label key={omicron} className={styles.checklistItem}>
                    <input type="checkbox" defaultChecked={omicron === "Reva - Inquisitorius"} />
                    <span>{omicron}</span>
                  </label>
                ))}
              </div>
            </div>

            <label className={styles.modalField}>
              <span className={styles.label}>Notes / Strategy</span>
              <textarea
                className={styles.modalInput}
                defaultValue="Strategy notes, tips, mod recommendations..."
                rows={4}
              />
            </label>

            <label className={styles.modalField}>
              <span className={styles.label}>YouTube URL</span>
              <input className={styles.modalInput} defaultValue="https://youtube.com/watch?v=preview" />
            </label>

            <div className={styles.modalFooter}>
              <button type="button" className={styles.secondaryButton} onClick={closeGuideEditor}>
                Cancel
              </button>
              <button type="button" className={styles.primaryButton}>
                Save Squad
              </button>
            </div>
          </div>
        </div>
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

  const liveRosterMembers = buildRosterMembers(guildSummary, guildRosters);
  const rosterMember =
    liveRosterMembers.find((member) => member.id === selectedRosterMemberId) ??
    rosterUnitsForDisplay(selectedRosterMemberId);
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
  const rosterOptions = liveRosterMembers.length ? liveRosterMembers : rosterMembers;

  return (
    <section className={styles.panel}>
      <div className={styles.rosterTopBar}>
        <div className={styles.rosterSelectWrap}>
          <select
            className={styles.selectControl}
            value={selectedRosterMemberId}
            onChange={(event) => setSelectedRosterMemberId(event.currentTarget.value)}
          >
            {rosterOptions.map((member) => (
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
          </select>
        </div>

        <div className={styles.summaryText}>{rosterMember.summary}</div>
      </div>

      <div className={styles.sortBar}>
        {[
          ["name", "Character"],
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
          {filteredCharacters.map((unit) => (
            <div key={unit.name} className={styles.rosterRow}>
              <span>{unit.name}</span>
              <span>{unit.type}</span>
              <span>{unit.stars}</span>
              <span>{unit.level}</span>
              <span>{unit.power}</span>
              <span className={styles.abilityList}>{unit.abilities.join(" | ")}</span>
            </div>
          ))}
        </div>
      </div>

      <div className={styles.rosterSection}>
        <div className={styles.rosterSectionHeader}>
          <span className={styles.rosterSectionTitle}>
            Ships ({filteredShips.length})
          </span>
        </div>
        <div className={styles.rosterList}>
          {filteredShips.map((unit) => (
            <div key={unit.name} className={styles.rosterRow}>
              <span>{unit.name}</span>
              <span>{unit.type}</span>
              <span>{unit.stars}</span>
              <span>{unit.level}</span>
              <span>{unit.power}</span>
              <span className={styles.abilityList}>{unit.abilities.join(" | ")}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
