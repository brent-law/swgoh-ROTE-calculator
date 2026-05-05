use crate::models::{
    GuildRosters, OpsDefinitions, PlannerAlgorithmMeta, PlannerAlgorithmScore,
    PlannerBonusPlanetDayResult, PlannerChainDayResult, PlannerCompletedPlatoon,
    PlannerDayResult, PlannerMissionDefinition, PlannerMissionEstimate,
    PlannerOptimizationProgressEvent, PlannerOptimizationResponse, PlannerOpsAssignmentEntry,
    PlannerOpsAssignmentGroup, PlannerOpsDaySummary, PlannerOpsPlanetDaySummary,
    PlannerOpsPlanetStats, PlannerOpsSummary, PlannerPlanetCard, PlannerPlanetCardMap,
    PlannerPlanetDefinition, PlannerPlanetState, PlannerProjectionResponse,
    PlannerReferenceResponse, PlannerSettings, PlannerSummary, PlatoonAnalysisMap,
    PlatoonRequirement,
};
use std::collections::{HashMap, HashSet};
use std::time::{SystemTime, UNIX_EPOCH};

const OPT_GENES: usize = 18;
const OPS_MEMBER_DAILY_CAP: i64 = 10;

#[derive(Debug, Clone)]
struct OpsCandidate {
    key: String,
    ally_code: String,
    name: String,
    rarity: i64,
    relic: i64,
}

#[derive(Debug, Clone)]
struct PlanetProgressState {
    idx: usize,
    banked: i64,
}

#[derive(Debug, Clone, Default)]
struct BonusActivationState {
    eligible: bool,
    active_from_day: i64,
    unlocked_on_day: i64,
    banked: i64,
    done: bool,
}

#[allow(dead_code)]
#[derive(Debug, Clone, Default)]
struct OpsSlotAssignment {
    ally_code: String,
    unit_key: String,
    day: i64,
}

#[derive(Debug, Clone)]
struct OpsPlatoonState {
    completed: bool,
    completed_day: i64,
    filled: Vec<bool>,
    assignments: Vec<Option<OpsSlotAssignment>>,
}

#[derive(Debug, Clone, Default)]
struct OpsPlanetState {
    completed_platoons: i64,
    completed_points: i64,
    platoons: Vec<OpsPlatoonState>,
}

#[derive(Debug, Clone, Default)]
struct OpsSimulationState {
    planets: HashMap<String, OpsPlanetState>,
}

#[derive(Debug, Clone)]
struct PlanetPriority {
    pid: String,
    priority: i64,
    label: String,
}

#[derive(Debug, Clone, Default)]
struct OptimizationBest {
    genome: Vec<i64>,
    score: i64,
}

#[derive(Debug, Clone)]
struct PlannerEngine {
    settings: PlannerSettings,
    planet_map: HashMap<String, PlannerPlanetDefinition>,
    ds_chain: Vec<String>,
    mx_chain: Vec<String>,
    ls_chain: Vec<String>,
    bonus_planets: Vec<String>,
    ops_defs: OpsDefinitions,
    candidates_by_def: HashMap<String, Vec<OpsCandidate>>,
    candidates_by_name: HashMap<String, Vec<OpsCandidate>>,
}

#[derive(Debug, Clone)]
struct SimpleRng {
    state: u64,
}

impl SimpleRng {
    fn seeded() -> Self {
        let seed = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_nanos() as u64)
            .unwrap_or(0x9E37_79B9_7F4A_7C15);
        Self {
            state: seed ^ 0xA5A_55A5_AD3C_5B79D,
        }
    }

    fn next_u64(&mut self) -> u64 {
        let mut x = self.state;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.state = x;
        x
    }

    fn next_f64(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 / ((1u64 << 53) as f64)
    }

    fn next_bool(&mut self) -> bool {
        self.next_u64() & 1 == 1
    }

    fn usize_below(&mut self, upper: usize) -> usize {
        if upper <= 1 {
            return 0;
        }
        (self.next_u64() as usize) % upper
    }

    fn i64_inclusive(&mut self, low: i64, high: i64) -> i64 {
        if high <= low {
            return low;
        }
        low + ((self.next_u64() % ((high - low + 1) as u64)) as i64)
    }
}

#[derive(Debug, Clone, Default)]
struct AppliedAssignments {
    slots_filled: i64,
    completed: bool,
    points_earned: i64,
    assignments: Vec<PlannerOpsAssignmentEntry>,
}

#[derive(Debug, Clone, Default)]
struct CapabilityReport {
    can_cm: i64,
    total: i64,
    label: String,
}

#[derive(Debug, Clone, Default)]
struct MissionBuckets {
    combat: Vec<PlannerMissionDefinition>,
    fleet: Vec<PlannerMissionDefinition>,
    special: Vec<PlannerMissionDefinition>,
    combat_fallback_count: i64,
    fleet_fallback_count: i64,
}

#[derive(Debug, Clone, Default)]
struct SimulatedPlan {
    days: Vec<PlannerDayResult>,
    total_stars: i64,
    ops_summary: PlannerOpsSummary,
    active_bonus_count: i64,
}

pub fn planner_reference() -> PlannerReferenceResponse {
    PlannerReferenceResponse {
        planets: planner_planets(),
        algorithms: planner_algorithms(),
    }
}

pub fn build_projection(
    settings: &PlannerSettings,
    rosters: &GuildRosters,
    analysis: Option<&PlatoonAnalysisMap>,
) -> PlannerProjectionResponse {
    let planets = planner_planets();
    let mut cards = PlannerPlanetCardMap::new();
    let mut estimated_stars = 0i64;
    let mut eligible_bonus_count = 0i64;
    let mut ops_filled = 0i64;
    let mut ops_total = 0i64;
    let mut ops_points = 0i64;
    let scanned_members = rosters.len() as i64;

    for planet in &planets {
        let state = planet_state(settings, &planet.id);
        let bonus_locked = planet.chain == "bonus" && !bonus_unlocked(settings, planet);
        if planet.chain == "bonus" && !bonus_locked {
            eligible_bonus_count += 1;
        }

        let mission_meta = mission_buckets(planet);
        let active_members = active_member_count(settings);
        let cm_rate = effective_cm_rate(settings, planet);
        let fleet_rate = effective_fleet_rate(settings, planet);
        let cm_expected = active_members as f64 * cm_rate;
        let fleet_expected = active_members as f64 * fleet_rate;
        let cm_points = if mission_meta.combat.is_empty() {
            round_to_i64(cm_expected) * planet.cm_points * mission_meta.combat_fallback_count
        } else {
            mission_meta
                .combat
                .iter()
                .map(|mission| project_combat_points(mission, cm_expected))
                .sum::<i64>()
        };
        let fleet_points = if mission_meta.fleet.is_empty() {
            round_to_i64(fleet_expected) * planet.fleet_points * mission_meta.fleet_fallback_count
        } else {
            mission_meta
                .fleet
                .iter()
                .map(|mission| project_fleet_points(mission, fleet_expected))
                .sum::<i64>()
        };

        let (planet_ops_filled, planet_ops_total) = analysis
            .and_then(|map| map.get(&planet.id))
            .map(|entries| {
                (
                    entries.iter().filter(|entry| entry.fillable).count() as i64,
                    entries.len() as i64,
                )
            })
            .unwrap_or((0, 0));
        let total_points = cm_points + fleet_points + (planet_ops_filled * planet.ops_val);
        let stars = if bonus_locked {
            0
        } else {
            stars_at(planet, total_points)
        };
        let progress = if planet.stars[2] > 0 {
            (total_points as f64 / planet.stars[2] as f64 * 100.0).clamp(0.0, 100.0)
        } else {
            0.0
        };
        let status = if bonus_locked {
            String::from("locked")
        } else if stars >= 3 {
            String::from("s3")
        } else if stars == 2 {
            String::from("s2")
        } else if stars == 1 {
            String::from("s1")
        } else {
            String::from("s0")
        };
        let capability = capability_badge(rosters, planet);
        let recommended_cm_rate = if capability.total > 0 {
            ((capability.can_cm as f64 / capability.total as f64) * 100.0).round() as i64
        } else {
            0
        };
        let recommended_fleet_rate = ((recommended_cm_rate as f64) * 0.85).round() as i64;
        let note = if bonus_locked {
            String::from("Bonus locked")
        } else if stars >= 3 {
            String::from("3 stars achievable")
        } else {
            format!(
                "{} pts needed for next star",
                format_number(
                    (planet.stars.get(stars as usize).copied().unwrap_or(planet.stars[2]) - total_points)
                        .max(0)
                )
            )
        };
        let operations_note = if planet_ops_total > 0 {
            format!("{} / {} platoons fillable", planet_ops_filled, planet_ops_total)
        } else if analysis.is_some() {
            String::from("No platoon definitions for this planet.")
        } else {
            String::from("Scan rosters to project platoons.")
        };

        let cm_display = display_rate_or_count(settings, &state, planet, true);
        let fleet_display = display_rate_or_count(settings, &state, planet, false);
        let combat_missions = mission_meta
            .combat
            .iter()
            .map(|mission| PlannerMissionEstimate {
                id: mission.id.clone(),
                label: mission.label.clone(),
                completion: cm_display.clone(),
                points: project_combat_points(mission, cm_expected),
            })
            .collect::<Vec<_>>();
        let fleet_missions = mission_meta
            .fleet
            .iter()
            .map(|mission| PlannerMissionEstimate {
                id: mission.id.clone(),
                label: mission.label.clone(),
                completion: fleet_display.clone(),
                points: project_fleet_points(mission, fleet_expected),
            })
            .collect::<Vec<_>>();

        ops_filled += planet_ops_filled;
        ops_total += planet_ops_total;
        ops_points += planet_ops_filled * planet.ops_val;
        estimated_stars += if planet.chain == "bonus" {
            stars.min(1)
        } else {
            stars
        };

        cards.insert(
            planet.id.clone(),
            PlannerPlanetCard {
                id: planet.id.clone(),
                name: planet.name.clone(),
                align: planet.align.clone(),
                chain: planet.chain.clone(),
                zone: planet.zone,
                phase: planet.phase,
                status,
                capability: capability.label,
                estimate: total_points,
                target: planet.stars[2],
                progress,
                note,
                bonus_locked,
                capability_count: capability.can_cm,
                capability_total: capability.total,
                recommended_cm_rate,
                recommended_fleet_rate,
                operations_filled: planet_ops_filled,
                operations_total: planet_ops_total,
                operations_note,
                combat_missions,
                fleet_missions,
                special_missions: mission_meta.special,
            },
        );
    }

    PlannerProjectionResponse {
        summary: PlannerSummary {
            estimated_stars,
            max_possible_stars: 54 + eligible_bonus_count,
            bonus_eligible_count: eligible_bonus_count,
            bonus_active_count: eligible_bonus_count,
            ops_filled,
            ops_total,
            ops_points,
            scanned_members,
            roster_coverage: if settings.guild_members > 0 {
                format!("{}/{} scanned", scanned_members, settings.guild_members)
            } else {
                String::from("No guild loaded")
            },
        },
        planet_cards: cards,
    }
}

pub fn run_optimizer(
    settings: &PlannerSettings,
    rosters: &GuildRosters,
    ops_defs: Option<&OpsDefinitions>,
    algorithm: &str,
    mut on_progress: impl FnMut(PlannerOptimizationProgressEvent),
) -> PlannerOptimizationResponse {
    let engine = PlannerEngine::new(
        settings.clone(),
        rosters,
        ops_defs.cloned().unwrap_or_default(),
    );
    let selected_algorithm = normalize_algorithm(algorithm);
    let algorithm_keys = if selected_algorithm == "all" {
        vec!["greedy", "sa", "pso", "ga", "adam"]
    } else {
        vec![selected_algorithm.as_str()]
    };
    let run_count = algorithm_keys.len().max(1) as f64;
    let mut scores = Vec::<PlannerAlgorithmScore>::new();

    on_progress(PlannerOptimizationProgressEvent {
        phase: String::from("starting"),
        selected_algorithm: selected_algorithm.clone(),
        algorithm: algorithm_keys[0].to_string(),
        overall_fraction: 0.0,
        algorithm_fraction: 0.0,
        best_score: 0,
        message: String::from("Preparing optimization run..."),
    });

    let mut best_algorithm = algorithm_keys[0].to_string();
    let mut best_result: Option<OptimizationBest> = None;

    for (algorithm_idx, key) in algorithm_keys.iter().enumerate() {
        let mut report_algorithm_progress = |algorithm_fraction: f64, best_score: i64| {
            let bounded_fraction = algorithm_fraction.clamp(0.0, 1.0);
            let overall_fraction = ((algorithm_idx as f64) + bounded_fraction) / run_count;
            on_progress(PlannerOptimizationProgressEvent {
                phase: String::from("progress"),
                selected_algorithm: selected_algorithm.clone(),
                algorithm: (*key).to_string(),
                overall_fraction: overall_fraction.clamp(0.0, 1.0),
                algorithm_fraction: bounded_fraction,
                best_score,
                message: optimization_progress_message(key, bounded_fraction, best_score),
            });
        };

        report_algorithm_progress(0.0, best_result.as_ref().map(|result| result.score).unwrap_or(0));
        let result = engine.run_algorithm(key, &mut report_algorithm_progress);
        scores.push(score_entry(key, result.score));
        if best_result
            .as_ref()
            .map(|current| result.score > current.score)
            .unwrap_or(true)
        {
            best_algorithm = (*key).to_string();
            best_result = Some(result);
        }
    }

    let best = best_result.unwrap_or_else(|| engine.run_greedy(&mut |_, _| {}));

    let simulated = engine.simulate_genome_plan(&best.genome, true);
    let scanned_members = rosters.len() as i64;
    let eligible_bonus_count = engine
        .bonus_planets
        .iter()
        .filter(|pid| {
            engine
                .planet_map
                .get(*pid)
                .map(|planet| bonus_unlocked(settings, planet))
                .unwrap_or(false)
        })
        .count() as i64;

    let response = PlannerOptimizationResponse {
        selected_algorithm,
        best_algorithm,
        total_stars: simulated.total_stars,
        summary: PlannerSummary {
            estimated_stars: simulated.total_stars,
            max_possible_stars: 54 + eligible_bonus_count,
            bonus_eligible_count: eligible_bonus_count,
            bonus_active_count: simulated.active_bonus_count,
            ops_filled: simulated.ops_summary.total_completed,
            ops_total: simulated.ops_summary.total_platoons,
            ops_points: simulated.ops_summary.total_points,
            scanned_members,
            roster_coverage: if settings.guild_members > 0 {
                format!("{}/{} scanned", scanned_members, settings.guild_members)
            } else {
                String::from("No guild loaded")
            },
        },
        algorithm_scores: scores,
        day_plan: simulated.days,
        ops_summary: simulated.ops_summary,
    };

    on_progress(PlannerOptimizationProgressEvent {
        phase: String::from("complete"),
        selected_algorithm: response.selected_algorithm.clone(),
        algorithm: response.best_algorithm.clone(),
        overall_fraction: 1.0,
        algorithm_fraction: 1.0,
        best_score: response.total_stars,
        message: optimization_completion_message(
            response.total_stars,
            &response.best_algorithm,
            &response.algorithm_scores,
        ),
    });

    response
}

impl PlannerEngine {
    fn new(settings: PlannerSettings, rosters: &GuildRosters, ops_defs: OpsDefinitions) -> Self {
        let planets = planner_planets();
        let planet_map = planets
            .iter()
            .cloned()
            .map(|planet| (planet.id.clone(), planet))
            .collect::<HashMap<_, _>>();

        Self {
            settings,
            planet_map,
            ds_chain: planets
                .iter()
                .filter(|planet| planet.chain == "ds")
                .map(|planet| planet.id.clone())
                .collect(),
            mx_chain: planets
                .iter()
                .filter(|planet| planet.chain == "mx")
                .map(|planet| planet.id.clone())
                .collect(),
            ls_chain: planets
                .iter()
                .filter(|planet| planet.chain == "ls")
                .map(|planet| planet.id.clone())
                .collect(),
            bonus_planets: planets
                .iter()
                .filter(|planet| planet.chain == "bonus")
                .map(|planet| planet.id.clone())
                .collect(),
            ops_defs,
            candidates_by_def: build_ops_candidate_pool(rosters),
            candidates_by_name: build_ops_candidate_name_pool(rosters),
        }
    }

    fn run_algorithm(
        &self,
        algorithm: &str,
        on_progress: &mut dyn FnMut(f64, i64),
    ) -> OptimizationBest {
        match normalize_algorithm(algorithm).as_str() {
            "ga" => self.run_ga(on_progress),
            "sa" => self.run_sa(on_progress),
            "pso" => self.run_pso(on_progress),
            "adam" => self.run_adam(on_progress),
            _ => self.run_greedy(on_progress),
        }
    }

    fn run_greedy(&self, on_progress: &mut dyn FnMut(f64, i64)) -> OptimizationBest {
        on_progress(0.5, 0);
        let genome = self.greedy_genome();
        let score = self.eval_genome(&genome);
        on_progress(1.0, score);
        OptimizationBest { genome, score }
    }

    fn run_ga(&self, on_progress: &mut dyn FnMut(f64, i64)) -> OptimizationBest {
        let population_size = 160usize;
        let generations = 140usize;
        let elite = 8usize;
        let mutation_rate = 0.12f64;
        let mut rng = SimpleRng::seeded();

        let greedy = self.greedy_genome();
        let mut population = Vec::<Vec<i64>>::with_capacity(population_size);
        population.push(greedy.clone());
        while population.len() < population_size {
            population.push(random_genome(&mut rng));
        }

        let mut scores = population
            .iter()
            .map(|genome| self.eval_genome(genome))
            .collect::<Vec<_>>();
        let mut best = OptimizationBest {
            genome: greedy,
            score: i64::MIN,
        };
        for (idx, score) in scores.iter().enumerate() {
            if *score > best.score {
                best = OptimizationBest {
                    genome: population[idx].clone(),
                    score: *score,
                };
            }
        }

        for generation in 0..generations {
            if generation % 12 == 0 {
                on_progress(generation as f64 / generations as f64, best.score);
            }
            let mut ranked = population
                .iter()
                .cloned()
                .zip(scores.iter().copied())
                .collect::<Vec<_>>();
            ranked.sort_by(|left, right| right.1.cmp(&left.1));

            let mut next_population = ranked
                .iter()
                .take(elite)
                .map(|entry| entry.0.clone())
                .collect::<Vec<_>>();

            while next_population.len() < population_size {
                let parent_a = tournament_pick(&population, &scores, &mut rng);
                let parent_b = tournament_pick(&population, &scores, &mut rng);
                let mut child = parent_a
                    .iter()
                    .enumerate()
                    .map(|(idx, gene)| if rng.next_bool() { *gene } else { parent_b[idx] })
                    .collect::<Vec<_>>();

                for gene in &mut child {
                    if rng.next_f64() < mutation_rate {
                        *gene = rng.i64_inclusive(0, 3);
                    }
                }
                if rng.next_f64() < 0.05 {
                    let day = rng.usize_below(6);
                    for ci in 0..3 {
                        child[day * 3 + ci] = rng.i64_inclusive(0, 3);
                    }
                }
                next_population.push(child);
            }

            population = next_population;
            scores = population
                .iter()
                .map(|genome| self.eval_genome(genome))
                .collect::<Vec<_>>();
            for (idx, score) in scores.iter().enumerate() {
                if *score > best.score {
                    best = OptimizationBest {
                        genome: population[idx].clone(),
                        score: *score,
                    };
                }
            }
        }

        on_progress(1.0, best.score);
        best
    }

    fn run_sa(&self, on_progress: &mut dyn FnMut(f64, i64)) -> OptimizationBest {
        let iterations = 8_000usize;
        let t0 = 120.0f64;
        let tf = 0.05f64;
        let cooling = (tf / t0).powf(1.0 / iterations as f64);
        let mut rng = SimpleRng::seeded();

        let mut current = self.greedy_genome();
        let mut current_score = self.eval_genome(&current);
        let mut best = OptimizationBest {
            genome: current.clone(),
            score: current_score,
        };
        let mut temperature = t0;

        for iteration in 0..iterations {
            if iteration % 400 == 0 {
                on_progress(iteration as f64 / iterations as f64, best.score);
            }
            let mut neighbor = current.clone();
            let mutation_count = if temperature > t0 * 0.5 {
                rng.i64_inclusive(2, 4)
            } else {
                rng.i64_inclusive(1, 2)
            };
            for _ in 0..mutation_count {
                let idx = rng.usize_below(OPT_GENES);
                neighbor[idx] = rng.i64_inclusive(0, 3);
            }

            let neighbor_score = self.eval_genome(&neighbor);
            let delta = neighbor_score - current_score;
            if delta > 0 || rng.next_f64() < ((delta as f64) / temperature).exp() {
                current = neighbor;
                current_score = neighbor_score;
            }
            if current_score > best.score {
                best = OptimizationBest {
                    genome: current.clone(),
                    score: current_score,
                };
            }
            temperature *= cooling;
        }

        on_progress(1.0, best.score);
        best
    }

    fn run_pso(&self, on_progress: &mut dyn FnMut(f64, i64)) -> OptimizationBest {
        let swarm_size = 48usize;
        let iterations = 220usize;
        let w = 0.72f64;
        let c1 = 1.49f64;
        let c2 = 1.49f64;
        let mut rng = SimpleRng::seeded();
        let base = self.greedy_genome();

        let mut particles = (0..swarm_size)
            .map(|idx| {
                let pos = if idx < 3 {
                    base.iter()
                        .map(|gene| *gene as f64 + (rng.next_f64() - 0.5) * 0.5)
                        .collect::<Vec<_>>()
                } else {
                    (0..OPT_GENES)
                        .map(|_| rng.next_f64() * 3.0)
                        .collect::<Vec<_>>()
                };
                let vel = (0..OPT_GENES)
                    .map(|_| (rng.next_f64() - 0.5) * 1.5)
                    .collect::<Vec<_>>();
                (pos, vel, Vec::<f64>::new(), i64::MIN)
            })
            .collect::<Vec<_>>();

        let mut global_best = base.iter().map(|gene| *gene as f64).collect::<Vec<_>>();
        let mut global_score = self.eval_genome(&base);

        for particle in &mut particles {
            let genome = particle.0.iter().copied().map(clamp_gene).collect::<Vec<_>>();
            let score = self.eval_genome(&genome);
            particle.2 = particle.0.clone();
            particle.3 = score;
            if score > global_score {
                global_score = score;
                global_best = particle.0.clone();
            }
        }

        for iteration in 0..iterations {
            if iteration % 20 == 0 {
                on_progress(iteration as f64 / iterations as f64, global_score);
            }
            for particle in &mut particles {
                for idx in 0..OPT_GENES {
                    let r1 = rng.next_f64();
                    let r2 = rng.next_f64();
                    particle.1[idx] = w * particle.1[idx]
                        + c1 * r1 * (particle.2[idx] - particle.0[idx])
                        + c2 * r2 * (global_best[idx] - particle.0[idx]);
                    particle.1[idx] = particle.1[idx].clamp(-2.0, 2.0);
                    particle.0[idx] = (particle.0[idx] + particle.1[idx]).clamp(0.0, 3.0);
                }

                let genome = particle.0.iter().copied().map(clamp_gene).collect::<Vec<_>>();
                let score = self.eval_genome(&genome);
                if score > particle.3 {
                    particle.2 = particle.0.clone();
                    particle.3 = score;
                }
                if score > global_score {
                    global_score = score;
                    global_best = particle.0.clone();
                }
            }
        }

        let best = OptimizationBest {
            genome: global_best.into_iter().map(clamp_gene).collect(),
            score: global_score,
        };
        on_progress(1.0, best.score);
        best
    }

    fn run_adam(&self, on_progress: &mut dyn FnMut(f64, i64)) -> OptimizationBest {
        let agent_count = 10usize;
        let iterations = 90usize;
        let lr = 0.28f64;
        let b1 = 0.9f64;
        let b2 = 0.999f64;
        let eps = 1e-8f64;
        let step = 0.45f64;
        let mut rng = SimpleRng::seeded();
        let base = self.greedy_genome();

        let mut agents = (0..agent_count)
            .map(|idx| {
                let pos = if idx < 3 {
                    base.iter()
                        .map(|gene| *gene as f64 + (rng.next_f64() - 0.5) * 0.35)
                        .collect::<Vec<_>>()
                } else {
                    (0..OPT_GENES)
                        .map(|_| rng.next_f64() * 3.0)
                        .collect::<Vec<_>>()
                };
                (
                    pos,
                    vec![0.0; OPT_GENES],
                    vec![0.0; OPT_GENES],
                    0usize,
                )
            })
            .collect::<Vec<_>>();

        let mut best = OptimizationBest {
            genome: base.clone(),
            score: self.eval_genome(&base),
        };

        for iteration in 0..iterations {
            for agent_idx in 0..agents.len() {
                if ((iteration * agent_count) + agent_idx) % 4 == 0 {
                    on_progress(
                        (iteration as f64 + (agent_idx as f64 / agent_count as f64))
                            / iterations as f64,
                        best.score,
                    );
                }

                let agent = &mut agents[agent_idx];
                let current = agent.0.iter().copied().map(clamp_gene).collect::<Vec<_>>();
                let base_score = self.eval_genome(&current);
                if base_score > best.score {
                    best = OptimizationBest {
                        genome: current.clone(),
                        score: base_score,
                    };
                }

                let delta = (0..OPT_GENES)
                    .map(|_| if rng.next_bool() { 1.0 } else { -1.0 })
                    .collect::<Vec<_>>();
                let plus = agent
                    .0
                    .iter()
                    .enumerate()
                    .map(|(idx, value)| (*value + step * delta[idx]).clamp(0.0, 3.0))
                    .map(clamp_gene)
                    .collect::<Vec<_>>();
                let minus = agent
                    .0
                    .iter()
                    .enumerate()
                    .map(|(idx, value)| (*value - step * delta[idx]).clamp(0.0, 3.0))
                    .map(clamp_gene)
                    .collect::<Vec<_>>();
                let plus_score = self.eval_genome(&plus);
                let minus_score = self.eval_genome(&minus);
                if plus_score > best.score {
                    best = OptimizationBest {
                        genome: plus.clone(),
                        score: plus_score,
                    };
                }
                if minus_score > best.score {
                    best = OptimizationBest {
                        genome: minus.clone(),
                        score: minus_score,
                    };
                }

                agent.3 += 1;
                let t = agent.3 as f64;
                let scale = (plus_score - minus_score) as f64 / (2.0 * step);
                for idx in 0..OPT_GENES {
                    let gradient = scale * delta[idx];
                    agent.1[idx] = b1 * agent.1[idx] + (1.0 - b1) * gradient;
                    agent.2[idx] = b2 * agent.2[idx] + (1.0 - b2) * gradient * gradient;
                    let m_hat = agent.1[idx] / (1.0 - b1.powf(t));
                    let v_hat = agent.2[idx] / (1.0 - b2.powf(t));
                    let pull = (best.genome[idx] as f64 - current[idx] as f64) * 0.05;
                    agent.0[idx] = (agent.0[idx] + lr * m_hat / (v_hat.sqrt() + eps) + pull)
                        .clamp(0.0, 3.0);
                }
            }
        }

        on_progress(1.0, best.score);
        best
    }

    fn greedy_genome(&self) -> Vec<i64> {
        let mut genome = vec![1; OPT_GENES];
        for day in 0..6usize {
            let options = if day == 5 { [1, 2, 3, -1] } else { [0, 1, 2, 3] };
            let mut best_combo = [1, 1, 1];
            let mut best_score = i64::MIN;

            for ds in options.into_iter().filter(|value| *value >= 0) {
                for mx in options.into_iter().filter(|value| *value >= 0) {
                    for ls in options.into_iter().filter(|value| *value >= 0) {
                        let mut candidate = genome.clone();
                        candidate[day * 3] = ds;
                        candidate[day * 3 + 1] = mx;
                        candidate[day * 3 + 2] = ls;
                        let score = self.eval_genome(&candidate);
                        if score > best_score {
                            best_score = score;
                            best_combo = [ds, mx, ls];
                        }
                    }
                }
            }

            genome[day * 3] = best_combo[0];
            genome[day * 3 + 1] = best_combo[1];
            genome[day * 3 + 2] = best_combo[2];
        }
        genome
    }

    fn eval_genome(&self, genome: &[i64]) -> i64 {
        self.simulate_genome_plan(genome, false).total_stars
    }

    fn simulate_genome_plan(&self, genome: &[i64], detailed: bool) -> SimulatedPlan {
        let mut state = HashMap::<String, PlanetProgressState>::new();
        state.insert(String::from("ds"), PlanetProgressState { idx: 0, banked: 0 });
        state.insert(String::from("mx"), PlanetProgressState { idx: 0, banked: 0 });
        state.insert(String::from("ls"), PlanetProgressState { idx: 0, banked: 0 });
        let mut bonus_state = create_bonus_activation_state(&self.settings, &self.planet_map);
        let mut ops_state = self.create_operations_sim_state(detailed);
        let mut days = Vec::<PlannerDayResult>::new();
        let mut total_stars = 0i64;

        for day_idx in 0..6usize {
            let day = day_idx as i64 + 1;
            let gp_day = self.gp_for_day(day);
            let mut notices = Vec::<String>::new();
            let active_bonus_planets = self.get_active_bonus_planets_for_day(&bonus_state, day);

            let mut preview_priorities = Vec::<PlanetPriority>::new();
            let mut active_planets = HashMap::<String, PlannerPlanetDefinition>::new();
            let mut targets = HashMap::<String, i64>::new();

            for (chain_key, chain_ids) in [
                ("ds", &self.ds_chain),
                ("mx", &self.mx_chain),
                ("ls", &self.ls_chain),
            ] {
                let progress = state.get(chain_key).cloned().unwrap_or(PlanetProgressState {
                    idx: chain_ids.len(),
                    banked: 0,
                });
                if progress.idx >= chain_ids.len() {
                    continue;
                }
                let planet = self
                    .planet_map
                    .get(&chain_ids[progress.idx])
                    .cloned()
                    .unwrap_or_default();
                let gene = genome[day_idx * 3 + chain_offset(chain_key)];
                let priority = if gene == 0 {
                    10
                } else if gene >= 3 {
                    130
                } else if gene == 2 {
                    120
                } else {
                    110
                };
                preview_priorities.push(PlanetPriority {
                    pid: planet.id.clone(),
                    priority,
                    label: if gene == 0 {
                        String::from("Preload")
                    } else {
                        format!("Commit {}*", gene.max(1))
                    },
                });
                active_planets.insert(chain_key.to_string(), planet);
                targets.insert(chain_key.to_string(), gene);
            }
            for (planet, _) in &active_bonus_planets {
                preview_priorities.push(PlanetPriority {
                    pid: planet.id.clone(),
                    priority: 5,
                    label: String::from("Bonus"),
                });
            }

            let day_ops =
                self.allocate_operations_for_day(day, &preview_priorities, &mut ops_state, detailed);
            let mut ops_points_by_planet = HashMap::<String, i64>::new();
            for (pid, planet) in &day_ops.planets {
                if planet.points_earned > 0 {
                    ops_points_by_planet.insert(pid.clone(), planet.points_earned);
                }
            }

            let mut bases = HashMap::<String, i64>::new();
            let mut gp_need = HashMap::<String, i64>::new();
            for chain_key in ["ds", "mx", "ls"] {
                let Some(planet) = active_planets.get(chain_key) else {
                    continue;
                };
                let banked = state.get(chain_key).map(|entry| entry.banked).unwrap_or(0);
                let base =
                    banked + self.mission_only_points(&planet.id) + *ops_points_by_planet.get(&planet.id).unwrap_or(&0);
                let gene = *targets.get(chain_key).unwrap_or(&-1);
                bases.insert(chain_key.to_string(), base);
                gp_need.insert(
                    chain_key.to_string(),
                    if gene <= 0 {
                        0
                    } else {
                        (planet.stars[(gene - 1) as usize] - base).max(0)
                    },
                );
            }

            let total_need = gp_need.values().sum::<i64>();
            let ratio = if total_need > gp_day {
                gp_day as f64 / total_need as f64
            } else {
                1.0
            };

            let mut day_result = PlannerDayResult {
                day,
                gp_avail: gp_day,
                gp_used: 0,
                stars_day: 0,
                chains: HashMap::new(),
                notices: Vec::new(),
                bonus_planets: Vec::new(),
                ops_points: day_ops.points_earned,
                ops_completed: day_ops.completed_platoons.clone(),
                ops_planets: day_ops.planets.clone(),
            };

            for chain_key in ["ds", "mx", "ls"] {
                let Some(planet) = active_planets.get(chain_key) else {
                    day_result.chains.insert(
                        chain_key.to_string(),
                        PlannerChainDayResult {
                            key: chain_key.to_string(),
                            status: String::from("complete"),
                            ..PlannerChainDayResult::default()
                        },
                    );
                    continue;
                };

                let gene = *targets.get(chain_key).unwrap_or(&-1);
                let base = *bases.get(chain_key).unwrap_or(&0);
                let mission_pts = self.mission_only_points(&planet.id);
                let ops_pts = *ops_points_by_planet.get(&planet.id).unwrap_or(&0);
                let carry_in_pts = state.get(chain_key).map(|entry| entry.banked).unwrap_or(0);

                if gene == 0 {
                    let safe_banked = base.min(planet.stars[0] - 1);
                    if let Some(progress) = state.get_mut(chain_key) {
                        progress.banked = safe_banked;
                    }
                    day_result.chains.insert(
                        chain_key.to_string(),
                        PlannerChainDayResult {
                            key: chain_key.to_string(),
                            status: String::from("preload"),
                            planet_id: Some(planet.id.clone()),
                            planet_name: Some(planet.name.clone()),
                            align: Some(planet.align.clone()),
                            banked: safe_banked,
                            tomorrow_est: safe_banked + mission_pts,
                            threshold1star: planet.stars[0],
                            carry_in_pts,
                            mission_pts,
                            ops_pts,
                            ..PlannerChainDayResult::default()
                        },
                    );
                    continue;
                }

                let gp_alloc = round_to_i64(*gp_need.get(chain_key).unwrap_or(&0) as f64 * ratio);
                let pts = base + gp_alloc;
                let stars = stars_at(planet, pts);
                if stars >= 1 {
                    if let Some(progress) = state.get_mut(chain_key) {
                        progress.idx += 1;
                        progress.banked = 0;
                    }
                    schedule_unlocked_bonus_planets(
                        &mut bonus_state,
                        &self.planet_map,
                        &planet.id,
                        day,
                        &mut notices,
                    );
                } else if let Some(progress) = state.get_mut(chain_key) {
                    progress.banked = base;
                }

                day_result.gp_used += gp_alloc;
                day_result.stars_day += stars;
                day_result.chains.insert(
                    chain_key.to_string(),
                    PlannerChainDayResult {
                        key: chain_key.to_string(),
                        status: if stars >= 1 {
                            String::from("commit")
                        } else {
                            String::from("building")
                        },
                        planet_id: Some(planet.id.clone()),
                        planet_name: Some(planet.name.clone()),
                        align: Some(planet.align.clone()),
                        pts,
                        gp_deployed: gp_alloc,
                        stars,
                        pct_of3: ((pts as f64 / planet.stars[2] as f64) * 100.0)
                            .round()
                            .clamp(0.0, 100.0) as i64,
                        carry_in_pts,
                        mission_pts,
                        ops_pts,
                        ..PlannerChainDayResult::default()
                    },
                );
            }

            let mut spare_gp = (gp_day - day_result.gp_used).max(0);
            for (planet, activation) in active_bonus_planets {
                let mission_pts = self.mission_only_points(&planet.id);
                let carry_in_pts = activation.banked;
                let ops_pts = *ops_points_by_planet.get(&planet.id).unwrap_or(&0);
                let base = activation.banked + mission_pts + ops_pts;
                let gp_needed = (planet.stars[2] - base).max(0);
                let gp_used = spare_gp.min(gp_needed);
                spare_gp -= gp_used;
                day_result.gp_used += gp_used;
                let pts = base + gp_used;
                let stars = stars_at(&planet, pts);
                let carry_over = if stars >= 1 {
                    0
                } else {
                    pts.min(planet.stars[0] - 1)
                };

                if let Some(state_entry) = bonus_state.get_mut(&planet.id) {
                    if stars >= 1 {
                        state_entry.done = true;
                        state_entry.banked = 0;
                    } else {
                        state_entry.banked = carry_over;
                    }
                }

                day_result.bonus_planets.push(PlannerBonusPlanetDayResult {
                    planet_id: planet.id.clone(),
                    planet_name: planet.name.clone(),
                    align: planet.align.clone(),
                    pts,
                    stars,
                    carry_in_pts,
                    mission_pts,
                    ops_pts,
                    gp_deployed: gp_used,
                    carry_over,
                    active_from_day: activation.active_from_day,
                    unlocked_on_day: activation.unlocked_on_day,
                });
                day_result.stars_day += stars;
            }

            total_stars += day_result.stars_day;
            day_result.notices = notices;
            days.push(day_result);
        }

        let ops_days = days
            .iter()
            .map(|day| PlannerOpsDaySummary {
                day: day.day,
                points_earned: day.ops_points,
                slots_filled: day.ops_planets.values().map(|planet| planet.slots_filled).sum(),
                completed_platoons: day.ops_completed.clone(),
                planets: day.ops_planets.clone(),
            })
            .collect::<Vec<_>>();
        let ops_summary = self.summarize_operations_state(&ops_state, &ops_days);
        let active_bonus_count = get_active_bonus_planet_ids_from_days(&days).len() as i64;

        SimulatedPlan {
            days,
            total_stars,
            ops_summary,
            active_bonus_count,
        }
    }

    fn create_operations_sim_state(&self, _detailed: bool) -> OpsSimulationState {
        let mut planets = HashMap::<String, OpsPlanetState>::new();
        for (pid, platoons) in &self.ops_defs {
            planets.insert(
                pid.clone(),
                OpsPlanetState {
                    completed_platoons: 0,
                    completed_points: 0,
                    platoons: platoons
                        .iter()
                        .map(|platoon| OpsPlatoonState {
                            completed: false,
                            completed_day: 0,
                            filled: vec![false; platoon.len()],
                            assignments: vec![None; platoon.len()],
                        })
                        .collect(),
                },
            );
        }
        OpsSimulationState { planets }
    }

    fn get_active_bonus_planets_for_day(
        &self,
        bonus_state: &HashMap<String, BonusActivationState>,
        day: i64,
    ) -> Vec<(PlannerPlanetDefinition, BonusActivationState)> {
        self.bonus_planets
            .iter()
            .filter_map(|pid| {
                let state = bonus_state.get(pid)?;
                if !state.eligible
                    || state.done
                    || state.active_from_day <= 0
                    || day < state.active_from_day
                {
                    return None;
                }
                self.planet_map
                    .get(pid)
                    .cloned()
                    .map(|planet| (planet, state.clone()))
            })
            .collect()
    }

    fn gp_for_day(&self, day: i64) -> i64 {
        let total = self.settings.guild_gp.max(0) as f64;
        let idx = (day - 1).clamp(0, 5) as usize;
        let raw = self.settings.daily_undep.get(idx).copied().unwrap_or(0.0);
        if self.settings.undep_mode == "flat" {
            round_to_i64((total - raw).max(0.0))
        } else {
            round_to_i64((total * (1.0 - raw / 100.0)).max(0.0))
        }
    }

    fn mission_only_points(&self, pid: &str) -> i64 {
        let Some(planet) = self.planet_map.get(pid) else {
            return 0;
        };
        let active = active_member_count(&self.settings) as f64;
        let cm_rate = effective_cm_rate(&self.settings, planet);
        let fleet_rate = effective_fleet_rate(&self.settings, planet);
        let mission_meta = mission_buckets(planet);
        let cm_expected = active * cm_rate;
        let fleet_expected = active * fleet_rate;
        let fallback_combat_total = mission_meta.combat_fallback_count * planet.cm_points;
        let fallback_fleet_total = mission_meta.fleet_fallback_count * planet.fleet_points;

        let cm_points = if mission_meta.combat.is_empty() {
            round_to_i64(cm_expected) * fallback_combat_total
        } else {
            mission_meta
                .combat
                .iter()
                .map(|mission| project_combat_points(mission, cm_expected))
                .sum()
        };
        let fleet_points = if mission_meta.fleet.is_empty() {
            round_to_i64(fleet_expected) * fallback_fleet_total
        } else {
            mission_meta
                .fleet
                .iter()
                .map(|mission| project_fleet_points(mission, fleet_expected))
                .sum()
        };

        cm_points + fleet_points
    }

    fn allocate_operations_for_day(
        &self,
        day: i64,
        priorities: &[PlanetPriority],
        ops_state: &mut OpsSimulationState,
        detailed: bool,
    ) -> PlannerOpsDaySummary {
        if self.ops_defs.is_empty() || self.candidates_by_def.is_empty() {
            return PlannerOpsDaySummary::default();
        }

        let mut assigned_units = HashSet::<String>::new();
        let mut summary = PlannerOpsDaySummary {
            day,
            ..PlannerOpsDaySummary::default()
        };

        let mut ordered = priorities.to_vec();
        ordered.sort_by(|left, right| {
            right
                .priority
                .cmp(&left.priority)
                .then_with(|| left.pid.cmp(&right.pid))
        });

        for priority in ordered {
            let Some(planet_def) = self.ops_defs.get(&priority.pid) else {
                continue;
            };
            let Some(planet_meta) = self.planet_map.get(&priority.pid) else {
                continue;
            };
            let Some(planet_state) = ops_state.planets.get_mut(&priority.pid) else {
                continue;
            };
            let mut planet_usage = HashMap::<String, i64>::new();
            let mut planet_summary = PlannerOpsPlanetDaySummary {
                priority: priority.priority,
                label: priority.label.clone(),
                ..PlannerOpsPlanetDaySummary::default()
            };

            loop {
                let mut fillable = Vec::<(usize, Vec<PlannerOpsAssignmentEntry>, i64, i64)>::new();
                for (platoon_idx, platoon_slots) in planet_def.iter().enumerate() {
                    let platoon_state = &planet_state.platoons[platoon_idx];
                    if platoon_state.completed {
                        continue;
                    }
                    let Some(preview) = self.preview_platoon_completion(
                        platoon_slots,
                        platoon_state,
                        &assigned_units,
                        &planet_usage,
                        day,
                    ) else {
                        continue;
                    };
                    let filled_now = platoon_state.filled.iter().filter(|filled| **filled).count() as i64;
                    let remaining = platoon_slots.len() as i64 - filled_now;
                    fillable.push((platoon_idx, preview, filled_now, remaining));
                }

                if fillable.is_empty() {
                    break;
                }

                fillable.sort_by(|left, right| {
                    right
                        .2
                        .cmp(&left.2)
                        .then_with(|| left.3.cmp(&right.3))
                        .then_with(|| (left.1.len() as i64).cmp(&(right.1.len() as i64)))
                        .then_with(|| left.0.cmp(&right.0))
                });

                let (platoon_idx, assignments, _, _) = fillable.remove(0);
                let applied = self.apply_ops_assignments(
                    &priority.pid,
                    platoon_idx,
                    planet_meta.ops_val,
                    planet_state,
                    &mut assigned_units,
                    &mut planet_usage,
                    assignments,
                    detailed,
                );
                self.accumulate_ops_summary(
                    platoon_idx,
                    &applied,
                    &priority.pid,
                    &mut planet_summary,
                    &mut summary,
                );
            }

            let mut partial_order = planet_def
                .iter()
                .enumerate()
                .filter_map(|(platoon_idx, platoon_slots)| {
                    let platoon_state = &planet_state.platoons[platoon_idx];
                    if platoon_state.completed
                        || !self.can_eventually_complete_platoon(
                            platoon_slots,
                            platoon_state,
                        )
                    {
                        return None;
                    }
                    let filled_now = platoon_state.filled.iter().filter(|filled| **filled).count() as i64;
                    Some((platoon_idx, filled_now, platoon_slots.len() as i64 - filled_now))
                })
                .collect::<Vec<_>>();
            partial_order.sort_by(|left, right| {
                right
                    .1
                    .cmp(&left.1)
                    .then_with(|| left.2.cmp(&right.2))
                    .then_with(|| left.0.cmp(&right.0))
            });

            for (platoon_idx, _, _) in partial_order {
                let applied = self.fill_platoon_partially(
                    &priority.pid,
                    platoon_idx,
                    planet_meta.ops_val,
                    planet_def[platoon_idx].as_slice(),
                    planet_state,
                    &mut assigned_units,
                    &mut planet_usage,
                    day,
                    detailed,
                );
                self.accumulate_ops_summary(
                    platoon_idx,
                    &applied,
                    &priority.pid,
                    &mut planet_summary,
                    &mut summary,
                );
            }

            if planet_summary.slots_filled > 0
                || planet_state.completed_platoons > 0
                || !planet_summary.assignments.is_empty()
            {
                summary.planets.insert(priority.pid.clone(), planet_summary);
            }
        }

        summary
    }

    fn summarize_operations_state(
        &self,
        ops_state: &OpsSimulationState,
        day_summaries: &[PlannerOpsDaySummary],
    ) -> PlannerOpsSummary {
        let mut total_completed = 0i64;
        let mut total_platoons = 0i64;
        let mut total_points = 0i64;
        let active_bonus_ids = get_active_bonus_planet_ids_from_ops_days(day_summaries);
        let mut planet_stats = HashMap::<String, PlannerOpsPlanetStats>::new();

        for (pid, planet_def) in &self.ops_defs {
            let Some(planet_meta) = self.planet_map.get(pid) else {
                continue;
            };
            if planet_meta.chain == "bonus" && !active_bonus_ids.contains(pid) {
                continue;
            }
            let planet_state = ops_state.planets.get(pid);
            let completed_platoons = planet_state.map(|state| state.completed_platoons).unwrap_or(0);
            let total_slots = planet_def.iter().map(|platoon| platoon.len() as i64).sum::<i64>();
            let slots_filled = planet_state
                .map(|state| {
                    state
                        .platoons
                        .iter()
                        .map(|platoon| platoon.filled.iter().filter(|filled| **filled).count() as i64)
                        .sum::<i64>()
                })
                .unwrap_or(0);
            let points = completed_platoons * planet_meta.ops_val;
            planet_stats.insert(
                pid.clone(),
                PlannerOpsPlanetStats {
                    completed_platoons,
                    total_platoons: planet_def.len() as i64,
                    total_slots,
                    slots_filled,
                    points,
                },
            );
            total_completed += completed_platoons;
            total_platoons += planet_def.len() as i64;
            total_points += points;
        }

        PlannerOpsSummary {
            total_completed,
            total_platoons,
            total_points,
            planet_stats,
            days: day_summaries.to_vec(),
        }
    }

    fn preview_platoon_completion(
        &self,
        platoon_slots: &[PlatoonRequirement],
        platoon_state: &OpsPlatoonState,
        assigned_units: &HashSet<String>,
        planet_usage: &HashMap<String, i64>,
        day: i64,
    ) -> Option<Vec<PlannerOpsAssignmentEntry>> {
        let mut temp_assigned = assigned_units.clone();
        let mut temp_usage = planet_usage.clone();
        let mut pending = platoon_slots
            .iter()
            .enumerate()
            .filter(|(idx, _)| !platoon_state.filled[*idx])
            .map(|(idx, requirement)| {
                let available = self
                    .get_assignable_ops_candidates(requirement, &temp_assigned, &temp_usage)
                    .len();
                (idx, requirement.clone(), available)
            })
            .collect::<Vec<_>>();
        pending.sort_by(|left, right| {
            left.2
                .cmp(&right.2)
                .then_with(|| left.1.name.cmp(&right.1.name))
        });

        let mut assignments = Vec::<PlannerOpsAssignmentEntry>::new();
        for (req_idx, requirement, _) in pending {
            let candidates =
                self.get_assignable_ops_candidates(&requirement, &temp_assigned, &temp_usage);
            let chosen = choose_best_ops_candidate(&candidates, &requirement, &temp_usage)?;
            temp_assigned.insert(chosen.unit_key());
            *temp_usage.entry(chosen.ally_code.clone()).or_insert(0) += 1;
            assignments.push(PlannerOpsAssignmentEntry {
                day,
                req_idx: req_idx as i64,
                def_id: requirement.def_id.clone(),
                name: requirement.name.clone(),
                min_relic: requirement.min_relic,
                min_rarity: requirement.min_rarity,
                ally_code: chosen.ally_code.clone(),
                unit_key: chosen.unit_key(),
            });
        }

        Some(assignments)
    }

    fn fill_platoon_partially(
        &self,
        pid: &str,
        platoon_idx: usize,
        reward_points: i64,
        platoon_slots: &[PlatoonRequirement],
        planet_state: &mut OpsPlanetState,
        assigned_units: &mut HashSet<String>,
        planet_usage: &mut HashMap<String, i64>,
        day: i64,
        detailed: bool,
    ) -> AppliedAssignments {
        let platoon_state = &mut planet_state.platoons[platoon_idx];
        if platoon_state.completed {
            return AppliedAssignments::default();
        }

        let mut pending = platoon_slots
            .iter()
            .enumerate()
            .filter(|(idx, _)| !platoon_state.filled[*idx])
            .map(|(idx, requirement)| {
                let available = self
                    .get_assignable_ops_candidates(requirement, assigned_units, planet_usage)
                    .len();
                (idx, requirement.clone(), available)
            })
            .collect::<Vec<_>>();
        pending.sort_by(|left, right| {
            left.2
                .cmp(&right.2)
                .then_with(|| left.1.name.cmp(&right.1.name))
        });

        let mut assignments = Vec::<PlannerOpsAssignmentEntry>::new();
        for (req_idx, requirement, _) in pending {
            let candidates =
                self.get_assignable_ops_candidates(&requirement, assigned_units, planet_usage);
            let Some(chosen) = choose_best_ops_candidate(&candidates, &requirement, planet_usage) else {
                continue;
            };
            assigned_units.insert(chosen.unit_key());
            *planet_usage.entry(chosen.ally_code.clone()).or_insert(0) += 1;
            platoon_state.filled[req_idx] = true;
            if detailed {
                platoon_state.assignments[req_idx] = Some(OpsSlotAssignment {
                    ally_code: chosen.ally_code.clone(),
                    unit_key: chosen.unit_key(),
                    day,
                });
            }
            assignments.push(PlannerOpsAssignmentEntry {
                day,
                req_idx: req_idx as i64,
                def_id: requirement.def_id.clone(),
                name: requirement.name.clone(),
                min_relic: requirement.min_relic,
                min_rarity: requirement.min_rarity,
                ally_code: chosen.ally_code.clone(),
                unit_key: chosen.unit_key(),
            });
        }

        let completed = platoon_state.filled.iter().all(|filled| *filled);
        let mut points_earned = 0;
        if completed && !platoon_state.completed {
            platoon_state.completed = true;
            platoon_state.completed_day = day;
            planet_state.completed_platoons += 1;
            planet_state.completed_points += reward_points;
            points_earned = reward_points;
        }

        let _ = pid;
        AppliedAssignments {
            slots_filled: assignments.len() as i64,
            completed,
            points_earned,
            assignments,
        }
    }

    fn apply_ops_assignments(
        &self,
        _pid: &str,
        platoon_idx: usize,
        reward_points: i64,
        planet_state: &mut OpsPlanetState,
        assigned_units: &mut HashSet<String>,
        planet_usage: &mut HashMap<String, i64>,
        assignments: Vec<PlannerOpsAssignmentEntry>,
        detailed: bool,
    ) -> AppliedAssignments {
        if assignments.is_empty() {
            return AppliedAssignments::default();
        }

        let platoon_state = &mut planet_state.platoons[platoon_idx];
        let mut slots_filled = 0i64;
        for assignment in &assignments {
            let idx = assignment.req_idx.max(0) as usize;
            assigned_units.insert(assignment.unit_key.clone());
            *planet_usage.entry(assignment.ally_code.clone()).or_insert(0) += 1;
            if idx < platoon_state.filled.len() {
                platoon_state.filled[idx] = true;
                if detailed {
                    platoon_state.assignments[idx] = Some(OpsSlotAssignment {
                        ally_code: assignment.ally_code.clone(),
                        unit_key: assignment.unit_key.clone(),
                        day: assignment.day,
                    });
                }
            }
            slots_filled += 1;
        }

        let completed = platoon_state.filled.iter().all(|filled| *filled);
        let mut points_earned = 0;
        if completed && !platoon_state.completed {
            platoon_state.completed = true;
            platoon_state.completed_day = assignments[0].day;
            planet_state.completed_platoons += 1;
            planet_state.completed_points += reward_points;
            points_earned = reward_points;
        }

        AppliedAssignments {
            slots_filled,
            completed,
            points_earned,
            assignments,
        }
    }

    fn can_eventually_complete_platoon(
        &self,
        platoon_slots: &[PlatoonRequirement],
        platoon_state: &OpsPlatoonState,
    ) -> bool {
        let mut grouped = HashMap::<String, (PlatoonRequirement, i64)>::new();
        for (idx, requirement) in platoon_slots.iter().enumerate() {
            if platoon_state.filled[idx] {
                continue;
            }
            let key = format!(
                "{}|{}|{}",
                canonical_defid(&requirement.def_id),
                requirement.min_rarity,
                requirement.min_relic
            );
            let entry = grouped.entry(key).or_insert((requirement.clone(), 0));
            entry.1 += 1;
        }

        grouped.into_values().all(|(requirement, need)| {
            self.potential_ops_candidates(&requirement).len() as i64 >= need
        })
    }

    fn potential_ops_candidates(&self, requirement: &PlatoonRequirement) -> Vec<OpsCandidate> {
        let def_id = canonical_defid(&requirement.def_id);
        let mut candidates = self
            .candidates_by_def
            .get(&def_id)
            .cloned()
            .unwrap_or_default();
        if candidates.is_empty() {
            candidates = self
                .candidates_by_name
                .get(&normalize_ops_name(&requirement.name))
                .cloned()
                .unwrap_or_default();
        }
        candidates
            .into_iter()
            .filter(|candidate| {
                candidate.rarity >= requirement.min_rarity
                    && candidate.relic >= requirement.min_relic
            })
            .collect()
    }

    fn get_assignable_ops_candidates(
        &self,
        requirement: &PlatoonRequirement,
        assigned_units: &HashSet<String>,
        planet_usage: &HashMap<String, i64>,
    ) -> Vec<OpsCandidate> {
        self.potential_ops_candidates(requirement)
            .into_iter()
            .filter(|candidate| {
                !assigned_units.contains(&candidate.unit_key())
                    && planet_usage
                        .get(&candidate.ally_code)
                        .copied()
                        .unwrap_or(0)
                        < OPS_MEMBER_DAILY_CAP
            })
            .collect()
    }

    fn accumulate_ops_summary(
        &self,
        platoon_idx: usize,
        applied: &AppliedAssignments,
        pid: &str,
        planet_summary: &mut PlannerOpsPlanetDaySummary,
        day_summary: &mut PlannerOpsDaySummary,
    ) {
        if applied.slots_filled == 0 {
            return;
        }
        planet_summary.slots_filled += applied.slots_filled;
        day_summary.slots_filled += applied.slots_filled;
        if !applied.assignments.is_empty() {
            planet_summary.assignments.push(PlannerOpsAssignmentGroup {
                platoon_idx: platoon_idx as i64,
                completed: applied.completed,
                points_earned: applied.points_earned,
                entries: applied.assignments.clone(),
            });
        }
        if applied.completed {
            planet_summary.completed_today += 1;
            planet_summary.points_earned += applied.points_earned;
            day_summary.points_earned += applied.points_earned;
            day_summary.completed_platoons.push(PlannerCompletedPlatoon {
                pid: pid.to_string(),
                platoon_idx: platoon_idx as i64,
                points: applied.points_earned,
            });
        }
    }
}

impl OpsCandidate {
    fn unit_key(&self) -> String {
        self.key.clone()
    }
}

fn score_entry(algorithm: &str, score: i64) -> PlannerAlgorithmScore {
    PlannerAlgorithmScore {
        algorithm: algorithm.to_string(),
        label: algorithm_label(algorithm),
        score,
    }
}

fn optimization_progress_message(algorithm: &str, fraction: f64, best_score: i64) -> String {
    let percent = (fraction.clamp(0.0, 1.0) * 100.0).round() as i64;
    let mut message = format!(
        "{} - {}% complete",
        algorithm_label(algorithm),
        percent.clamp(0, 100),
    );
    if best_score > 0 {
        message.push_str(&format!(" | best so far: {best_score} stars"));
    }
    message
}

fn optimization_completion_message(
    best_score: i64,
    best_algorithm: &str,
    scores: &[PlannerAlgorithmScore],
) -> String {
    let mut message = format!(
        "Complete - Best: {} stars ({})",
        best_score,
        algorithm_label(best_algorithm),
    );
    if scores.len() > 1 {
        let summary = scores
            .iter()
            .map(|entry| format!("{}: {} stars", entry.label, entry.score))
            .collect::<Vec<_>>()
            .join(" | ");
        if !summary.is_empty() {
            message.push_str(" | ");
            message.push_str(&summary);
        }
    }
    message
}

fn build_ops_candidate_pool(rosters: &GuildRosters) -> HashMap<String, Vec<OpsCandidate>> {
    let mut pool = HashMap::<String, Vec<OpsCandidate>>::new();
    for (ally_code, roster) in rosters {
        for unit in roster {
            let def_id = canonical_defid(&unit.def_id);
            if def_id.is_empty() {
                continue;
            }
            pool.entry(def_id.clone()).or_default().push(OpsCandidate {
                key: format!("{ally_code}|{def_id}"),
                ally_code: ally_code.clone(),
                name: unit.name.clone(),
                rarity: unit.rarity,
                relic: if unit.combat_type == 2 { 0 } else { unit.relic },
            });
        }
    }
    for candidates in pool.values_mut() {
        candidates.sort_by(|left, right| {
            left.rarity
                .cmp(&right.rarity)
                .then_with(|| left.relic.cmp(&right.relic))
                .then_with(|| left.ally_code.cmp(&right.ally_code))
        });
    }
    pool
}

fn build_ops_candidate_name_pool(rosters: &GuildRosters) -> HashMap<String, Vec<OpsCandidate>> {
    let mut pool = HashMap::<String, Vec<OpsCandidate>>::new();
    for (ally_code, roster) in rosters {
        for unit in roster {
            let normalized_name = normalize_ops_name(&unit.name);
            if normalized_name.is_empty() {
                continue;
            }
            let def_id = canonical_defid(&unit.def_id);
            pool.entry(normalized_name).or_default().push(OpsCandidate {
                key: format!("{ally_code}|{def_id}"),
                ally_code: ally_code.clone(),
                name: unit.name.clone(),
                rarity: unit.rarity,
                relic: if unit.combat_type == 2 { 0 } else { unit.relic },
            });
        }
    }
    for candidates in pool.values_mut() {
        candidates.sort_by(|left, right| {
            left.rarity
                .cmp(&right.rarity)
                .then_with(|| left.relic.cmp(&right.relic))
                .then_with(|| left.ally_code.cmp(&right.ally_code))
        });
    }
    pool
}

fn choose_best_ops_candidate(
    candidates: &[OpsCandidate],
    _requirement: &PlatoonRequirement,
    planet_usage: &HashMap<String, i64>,
) -> Option<OpsCandidate> {
    let mut ordered = candidates.to_vec();
    ordered.sort_by(|left, right| {
        planet_usage
            .get(&left.ally_code)
            .copied()
            .unwrap_or(0)
            .cmp(&planet_usage.get(&right.ally_code).copied().unwrap_or(0))
            .then_with(|| left.relic.cmp(&right.relic))
            .then_with(|| left.rarity.cmp(&right.rarity))
            .then_with(|| left.name.cmp(&right.name))
            .then_with(|| left.ally_code.cmp(&right.ally_code))
    });
    ordered.into_iter().next()
}

fn create_bonus_activation_state(
    settings: &PlannerSettings,
    planet_map: &HashMap<String, PlannerPlanetDefinition>,
) -> HashMap<String, BonusActivationState> {
    planet_map
        .values()
        .filter(|planet| planet.chain == "bonus")
        .map(|planet| {
            (
                planet.id.clone(),
                BonusActivationState {
                    eligible: bonus_unlocked(settings, planet),
                    active_from_day: 0,
                    unlocked_on_day: 0,
                    banked: 0,
                    done: false,
                },
            )
        })
        .collect()
}

fn schedule_unlocked_bonus_planets(
    bonus_state: &mut HashMap<String, BonusActivationState>,
    planet_map: &HashMap<String, PlannerPlanetDefinition>,
    source_planet_id: &str,
    day: i64,
    notices: &mut Vec<String>,
) {
    for planet in planet_map.values().filter(|planet| planet.chain == "bonus") {
        let Some(state) = bonus_state.get_mut(&planet.id) else {
            continue;
        };
        if !state.eligible
            || state.done
            || state.active_from_day > 0
            || planet.unlocked_by.as_deref() != Some(source_planet_id)
        {
            continue;
        }
        let active_from_day = day + 1;
        if active_from_day > 6 {
            continue;
        }
        state.active_from_day = active_from_day;
        state.unlocked_on_day = day;
        let source_name = planet_map
            .get(source_planet_id)
            .map(|planet| planet.name.clone())
            .unwrap_or_else(|| title_case(source_planet_id));
        notices.push(format!(
            "{} unlocks on Day {} after {} reaches 1-star.",
            planet.name, active_from_day, source_name
        ));
    }
}

fn get_active_bonus_planet_ids_from_days(days: &[PlannerDayResult]) -> HashSet<String> {
    let mut ids = HashSet::<String>::new();
    for day in days {
        for bonus in &day.bonus_planets {
            ids.insert(bonus.planet_id.clone());
        }
    }
    ids
}

fn get_active_bonus_planet_ids_from_ops_days(days: &[PlannerOpsDaySummary]) -> HashSet<String> {
    let mut ids = HashSet::<String>::new();
    for day in days {
        for pid in day.planets.keys() {
            ids.insert(pid.clone());
        }
    }
    ids
}

fn active_member_count(settings: &PlannerSettings) -> i64 {
    settings.guild_members.clamp(1, 50)
}

fn planet_state(settings: &PlannerSettings, pid: &str) -> PlannerPlanetState {
    settings
        .planet_state
        .get(pid)
        .cloned()
        .unwrap_or_default()
}

fn effective_cm_rate(settings: &PlannerSettings, planet: &PlannerPlanetDefinition) -> f64 {
    let state = planet_state(settings, &planet.id);
    if settings.cm_mode == "count" {
        if let Some(override_count) = state.cm_count_override {
            return (override_count / active_member_count(settings) as f64).clamp(0.0, 1.0);
        }
        return ((settings.cm_base - settings.cm_falloff * chain_depth(&planet.id) as f64) / 100.0)
            .clamp(0.0, 1.0);
    }
    if let Some(override_rate) = state.cm_rate_override {
        return (override_rate / 100.0).clamp(0.0, 1.0);
    }
    ((settings.cm_base - settings.cm_falloff * chain_depth(&planet.id) as f64) / 100.0)
        .clamp(0.0, 1.0)
}

fn effective_fleet_rate(settings: &PlannerSettings, planet: &PlannerPlanetDefinition) -> f64 {
    let state = planet_state(settings, &planet.id);
    if settings.cm_mode == "count" {
        if let Some(override_count) = state.fleet_count_override {
            return (override_count / active_member_count(settings) as f64).clamp(0.0, 1.0);
        }
        return ((settings.fleet_base - settings.fleet_falloff * chain_depth(&planet.id) as f64)
            / 100.0)
            .clamp(0.0, 1.0);
    }
    if let Some(override_rate) = state.fleet_rate_override {
        return (override_rate / 100.0).clamp(0.0, 1.0);
    }
    ((settings.fleet_base - settings.fleet_falloff * chain_depth(&planet.id) as f64) / 100.0)
        .clamp(0.0, 1.0)
}

fn mission_buckets(planet: &PlannerPlanetDefinition) -> MissionBuckets {
    MissionBuckets {
        combat: planet
            .missions
            .iter()
            .filter(|mission| mission.mission_type == "combat")
            .cloned()
            .collect(),
        fleet: planet
            .missions
            .iter()
            .filter(|mission| mission.mission_type == "fleet")
            .cloned()
            .collect(),
        special: planet
            .missions
            .iter()
            .filter(|mission| {
                mission.mission_type == "special" || mission.mission_type == "special_unlock"
            })
            .cloned()
            .collect(),
        combat_fallback_count: planet
            .missions
            .iter()
            .filter(|mission| mission.mission_type == "combat")
            .count() as i64,
        fleet_fallback_count: planet
            .missions
            .iter()
            .filter(|mission| mission.mission_type == "fleet")
            .count() as i64,
    }
}

fn project_combat_points(mission: &PlannerMissionDefinition, expected_completions: f64) -> i64 {
    let full = mission.points.unwrap_or_default();
    let single = mission.points_single.unwrap_or(full);
    if full <= 0 {
        return 0;
    }
    if single > 0 && single < full {
        let full_clears = expected_completions.floor() as i64;
        let partial = if expected_completions - full_clears as f64 >= 0.5 {
            single
        } else {
            0
        };
        return full_clears * full + partial;
    }
    round_to_i64(expected_completions) * full
}

fn project_fleet_points(mission: &PlannerMissionDefinition, expected_completions: f64) -> i64 {
    let full = mission.points.unwrap_or_default();
    if full <= 0 {
        return 0;
    }
    round_to_i64(expected_completions) * full
}

fn stars_at(planet: &PlannerPlanetDefinition, points: i64) -> i64 {
    planet
        .stars
        .iter()
        .enumerate()
        .filter(|(_, threshold)| points >= **threshold)
        .map(|(idx, _)| idx as i64 + 1)
        .max()
        .unwrap_or(0)
}

fn bonus_unlocked(settings: &PlannerSettings, planet: &PlannerPlanetDefinition) -> bool {
    let Some(source_id) = planet.unlocked_by.as_deref() else {
        return true;
    };
    let source_state = planet_state(settings, source_id);
    if source_state.sm_ready {
        return true;
    }
    source_state.sm_count >= planet.unlocked_at.unwrap_or_default()
}

fn capability_badge(rosters: &GuildRosters, planet: &PlannerPlanetDefinition) -> CapabilityReport {
    if rosters.is_empty() {
        return CapabilityReport {
            can_cm: 0,
            total: 0,
            label: String::from("No roster scan yet"),
        };
    }

    let can_cm = rosters
        .values()
        .filter(|roster| {
            roster
                .iter()
                .filter(|unit| unit.combat_type == 1 && unit.rarity >= 7 && unit.relic >= planet.min_relic)
                .count()
                >= 5
        })
        .count() as i64;
    let total = rosters.len() as i64;
    let pct = if total > 0 {
        round_to_i64((can_cm as f64 / total as f64) * 100.0)
    } else {
        0
    };

    CapabilityReport {
        can_cm,
        total,
        label: format!("{can_cm}/{total} can do R{}+ CMs ({pct}%)", planet.min_relic),
    }
}

fn display_rate_or_count(
    settings: &PlannerSettings,
    state: &PlannerPlanetState,
    planet: &PlannerPlanetDefinition,
    combat: bool,
) -> String {
    if settings.cm_mode == "count" {
        let count = if combat {
            state
                .cm_count_override
                .unwrap_or(active_member_count(settings) as f64 * effective_cm_rate(settings, planet))
        } else {
            state.fleet_count_override.unwrap_or(
                active_member_count(settings) as f64 * effective_fleet_rate(settings, planet),
            )
        };
        return format!("{}", round_to_i64(count));
    }

    let rate = if combat {
        state
            .cm_rate_override
            .unwrap_or(effective_cm_rate(settings, planet) * 100.0)
    } else {
        state
            .fleet_rate_override
            .unwrap_or(effective_fleet_rate(settings, planet) * 100.0)
    };
    format!("{}%", round_to_i64(rate))
}

fn normalize_algorithm(value: &str) -> String {
    match value.trim().to_lowercase().as_str() {
        "ga" | "genetic" | "genetic-algorithm" => String::from("ga"),
        "sa" | "annealing" | "simulated-annealing" => String::from("sa"),
        "pso" | "particle-swarm" => String::from("pso"),
        "adam" => String::from("adam"),
        "all" => String::from("all"),
        _ => String::from("greedy"),
    }
}

fn algorithm_label(value: &str) -> String {
    planner_algorithms()
        .into_iter()
        .find(|entry| entry.id == normalize_algorithm(value))
        .map(|entry| entry.label)
        .unwrap_or_else(|| title_case(value))
}

fn random_genome(rng: &mut SimpleRng) -> Vec<i64> {
    (0..OPT_GENES).map(|_| rng.i64_inclusive(0, 3)).collect()
}

fn tournament_pick(population: &[Vec<i64>], scores: &[i64], rng: &mut SimpleRng) -> Vec<i64> {
    let mut best_idx = rng.usize_below(population.len());
    for _ in 1..6 {
        let idx = rng.usize_below(population.len());
        if scores[idx] > scores[best_idx] {
            best_idx = idx;
        }
    }
    population[best_idx].clone()
}

fn clamp_gene(value: f64) -> i64 {
    value.round().clamp(0.0, 3.0) as i64
}

fn chain_depth(pid: &str) -> usize {
    match pid {
        "mustafar" | "corellia" | "coruscant" => 0,
        "geonosis" | "felucia" | "bracca" => 1,
        "dathomir" | "tatooine" | "kashyyyk" | "zeffo" => 2,
        "medstation" | "kessel" | "lothal" | "mandalore" => 3,
        "malachor" | "vandor" | "kafrene" => 4,
        "deathstar" | "hoth" | "scarif" => 5,
        _ => 3,
    }
}

fn chain_offset(chain_key: &str) -> usize {
    match chain_key {
        "ds" => 0,
        "mx" => 1,
        "ls" => 2,
        _ => 0,
    }
}

fn canonical_defid(value: &str) -> String {
    value
        .split(':')
        .next()
        .unwrap_or_default()
        .trim()
        .to_uppercase()
}

fn normalize_ops_name(value: &str) -> String {
    let mut out = String::new();
    for ch in value.chars() {
        if ch == '&' {
            out.push_str("and");
            continue;
        }
        if ch.is_alphanumeric() {
            for lower in ch.to_lowercase() {
                out.push(lower);
            }
        }
    }
    out
}

fn round_to_i64(value: f64) -> i64 {
    value.round().max(0.0) as i64
}

fn format_number(value: i64) -> String {
    let mut chars = value.max(0).to_string().chars().rev().collect::<Vec<_>>();
    let mut out = String::new();
    while !chars.is_empty() {
        for _ in 0..3 {
            let Some(ch) = chars.pop() else {
                break;
            };
            out.push(ch);
        }
        if !chars.is_empty() {
            out.push(',');
        }
    }
    out
}

fn title_case(value: &str) -> String {
    value
        .replace(['_', '-'], " ")
        .split_whitespace()
        .map(|word| {
            let mut chars = word.chars();
            match chars.next() {
                Some(first) => {
                    format!("{}{}", first.to_uppercase(), chars.as_str().to_lowercase())
                }
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

fn planner_algorithms() -> Vec<PlannerAlgorithmMeta> {
    vec![
        PlannerAlgorithmMeta {
            id: String::from("greedy"),
            label: String::from("Greedy Enumeration"),
            quality: String::from("5/10 quality"),
            complexity: String::from("2/10 complexity"),
            runtime: String::from("Short runtime"),
            description: String::from("Follows the strongest immediate star gains first. Fastest option, but it can miss better long-range preload paths."),
        },
        PlannerAlgorithmMeta {
            id: String::from("sa"),
            label: String::from("Simulated Annealing"),
            quality: String::from("8/10 quality"),
            complexity: String::from("6/10 complexity"),
            runtime: String::from("Medium runtime"),
            description: String::from("Explores nearby plan variations and occasionally accepts weaker moves early so it can escape local traps."),
        },
        PlannerAlgorithmMeta {
            id: String::from("pso"),
            label: String::from("Particle Swarm"),
            quality: String::from("8/10 quality"),
            complexity: String::from("7/10 complexity"),
            runtime: String::from("Medium-long runtime"),
            description: String::from("Lets many candidate plans move together toward strong focus orders and preload patterns found across the search."),
        },
        PlannerAlgorithmMeta {
            id: String::from("ga"),
            label: String::from("Genetic Algorithm"),
            quality: String::from("9/10 quality"),
            complexity: String::from("8/10 complexity"),
            runtime: String::from("Long runtime"),
            description: String::from("Breeds high-performing plans across generations. Usually one of the strongest choices for balancing stars, focus, and preload value."),
        },
        PlannerAlgorithmMeta {
            id: String::from("adam"),
            label: String::from("Adam Optimizer"),
            quality: String::from("6/10 quality"),
            complexity: String::from("9/10 complexity"),
            runtime: String::from("Very long runtime"),
            description: String::from("Pushes the plan with gradient-like updates in a noisy discrete search space. Powerful when it lands well, but still the least predictable and slowest option here."),
        },
        PlannerAlgorithmMeta {
            id: String::from("all"),
            label: String::from("All Algorithms"),
            quality: String::from("Comparison pass"),
            complexity: String::from("10/10 complexity"),
            runtime: String::from("Extreme runtime"),
            description: String::from("Runs every algorithm in sequence, then keeps the best final path. Highest confidence, longest wait."),
        },
    ]
}

fn planner_planets() -> Vec<PlannerPlanetDefinition> {
    vec![
        planet(
            "mustafar",
            "Mustafar",
            "ds",
            "ds",
            1,
            1,
            200_000,
            400_000,
            10_000_000,
            [116_406_250, 186_250_000, 248_333_333],
            5,
            None,
            None,
            None,
            None,
            vec![
                combat("nute", "Bottom-Left", 100_000, 200_000, "Dark Side or Neutral"),
                combat("wat", "Top", 100_000, 200_000, "Dark Side or Neutral"),
                combat("geo", "Bottom-Right", 100_000, 200_000, "Dark Side or Neutral"),
                combat("lv", "Lord Vader", 100_000, 200_000, "Lord Vader only"),
                fleet(
                    "fleet",
                    "Fleet",
                    400_000,
                    400_000,
                    "7-star ships; Scythe required in the starting lineup",
                ),
            ],
        ),
        planet(
            "geonosis",
            "Geonosis",
            "ds",
            "ds",
            2,
            2,
            250_000,
            500_000,
            11_000_000,
            [148_125_000, 237_000_000, 316_000_000],
            6,
            None,
            None,
            None,
            None,
            vec![
                combat("reek", "Left (Reek)", 125_000, 250_000, "Dark Side or Neutral"),
                combat("acklay", "Bottom (Acklay)", 125_000, 250_000, "Dark Side or Neutral"),
                combat("nexu", "Top (Nexu)", 125_000, 250_000, "Dark Side or Neutral"),
                combat("combat", "Geonosians", 125_000, 250_000, "Geonosian"),
                fleet("fleet", "Fleet", 500_000, 500_000, "7-star ships"),
            ],
        ),
        planet(
            "dathomir",
            "Dathomir",
            "ds",
            "ds",
            3,
            3,
            341_250,
            0,
            13_200_000,
            [158_960_938, 254_337_500, 339_116_667],
            7,
            None,
            None,
            Some("Special Mission"),
            None,
            vec![
                combat("cm1", "Left", 162_500, 341_250, "Dark Side or Neutral"),
                combat("cm2", "Right", 162_500, 341_250, "Dark Side or Neutral"),
                combat("cm3", "Empire", 162_500, 341_250, "Empire"),
                combat(
                    "cm4",
                    "Doctor Aphra",
                    162_500,
                    341_250,
                    "Dark Side or Neutral; Doctor Aphra required as leader",
                ),
                special(
                    "sm",
                    "Merrin",
                    "Nightsister; Merrin required",
                    "50 Mk II Guild Event Tokens",
                ),
            ],
        ),
        planet(
            "medstation",
            "Med Station",
            "ds",
            "ds",
            4,
            4,
            493_594,
            0,
            18_480_000,
            [235_143_105, 400_243_583, 500_304_479],
            8,
            None,
            None,
            Some("Special Mission"),
            None,
            vec![
                combat("cm1", "Brain Worms 1", 219_375, 493_594, "Dark Side or Neutral"),
                combat("cm2", "Brain Worms 2", 219_375, 493_594, "Dark Side or Neutral"),
                combat("cm3", "Brain Worms 3", 219_375, 493_594, "Dark Side or Neutral"),
                combat("cm4", "Droids CM (Left)", 219_375, 493_594, "Dark Side or Neutral"),
                special(
                    "sm",
                    "Inquisitors",
                    "Inquisitorius; Third Sister required as leader. Great Mothers are not allowed",
                    "Special mission reward",
                ),
            ],
        ),
        planet(
            "malachor",
            "Malachor",
            "ds",
            "ds",
            5,
            5,
            721_744,
            0,
            33_264_000,
            [341_250_768, 620_455_942, 729_948_167],
            8,
            None,
            None,
            None,
            None,
            vec![
                combat("cm1", "Bottom-Left", 307_125, 721_744, "Dark Side or Neutral"),
                combat("cm2", "Top-Left", 307_125, 721_744, "Dark Side or Neutral"),
                combat("cm3", "Top-Right", 307_125, 721_744, "Dark Side or Neutral"),
                combat(
                    "cm4",
                    "Eighth / Fifth / Seventh Sister",
                    307_125,
                    721_744,
                    "Dark Side or Neutral; Eighth Brother, Fifth Brother, and Seventh Sister required",
                ),
            ],
        ),
        planet(
            "deathstar",
            "Death Star",
            "ds",
            "ds",
            6,
            6,
            1_151_719,
            2_303_438,
            86_486_400,
            [582_632_425, 1_059_331_682, 1_246_272_567],
            9,
            None,
            None,
            None,
            None,
            vec![
                combat("cm3", "Bottom-Left", 460_668, 1_151_719, "Dark Side or Neutral"),
                combat("cm4", "Bottom-Right", 460_668, 1_151_719, "Dark Side or Neutral"),
                combat(
                    "dv",
                    "Darth Vader",
                    460_668,
                    1_151_719,
                    "Darth Vader only; Darth Vader required as leader",
                ),
                combat(
                    "iden",
                    "Iden Versio",
                    460_668,
                    1_151_719,
                    "Dark Side or Neutral; Iden Versio required",
                ),
                fleet(
                    "fleet",
                    "Fleet",
                    2_303_438,
                    2_303_438,
                    "7-star ships; Imperial TIE Fighter required in the starting lineup",
                ),
            ],
        ),
        planet(
            "corellia",
            "Corellia",
            "mx",
            "mx",
            1,
            1,
            200_000,
            400_000,
            10_000_000,
            [111_718_750, 178_750_000, 238_333_333],
            5,
            None,
            None,
            Some("Special Mission"),
            None,
            vec![
                combat("combat", "Mixed Combat", 100_000, 200_000, "Dark Side or Light Side or Neutral"),
                combat(
                    "jabba",
                    "Jabba the Hutt",
                    100_000,
                    200_000,
                    "Dark Side or Light Side or Neutral; Jabba the Hutt required as leader",
                ),
                combat(
                    "aphra",
                    "Doctor Aphra",
                    100_000,
                    200_000,
                    "Dark Side or Light Side or Neutral; Doctor Aphra required as leader",
                ),
                fleet(
                    "fleet",
                    "Fleet",
                    400_000,
                    400_000,
                    "7-star ships; Lando's Millennium Falcon required in the starting lineup",
                ),
                special(
                    "sm",
                    "Qi'ra + Young Han",
                    "Qi'ra required as leader; Young Han Solo also required",
                    "15 Mk III Guild Tokens",
                ),
            ],
        ),
        planet(
            "felucia",
            "Felucia",
            "mx",
            "mx",
            2,
            2,
            250_000,
            500_000,
            11_000_000,
            [148_125_000, 237_000_000, 316_000_000],
            6,
            None,
            None,
            None,
            None,
            vec![
                combat("combat", "Mixed Combat", 125_000, 250_000, "Dark Side or Light Side or Neutral"),
                combat(
                    "bh",
                    "Young Lando",
                    125_000,
                    250_000,
                    "Dark Side or Light Side or Neutral; Young Lando Calrissian required",
                ),
                combat(
                    "jabba",
                    "Jabba the Hutt",
                    125_000,
                    250_000,
                    "Dark Side or Light Side or Neutral; Jabba the Hutt required as leader",
                ),
                combat(
                    "hondo",
                    "Hondo",
                    125_000,
                    250_000,
                    "Dark Side or Light Side or Neutral; Hondo Ohnaka required",
                ),
                fleet("fleet", "Fleet", 500_000, 500_000, "7-star ships"),
            ],
        ),
        planet(
            "tatooine",
            "Tatooine",
            "mx",
            "mx",
            3,
            3,
            341_250,
            682_500,
            13_200_000,
            [190_953_125, 305_525_000, 407_366_667],
            7,
            None,
            None,
            Some("Unlock Mandalore Special Mission"),
            Some(25),
            vec![
                combat("combat", "Mixed Combat", 162_500, 341_250, "Dark Side or Light Side or Neutral"),
                combat(
                    "jabba",
                    "Jabba the Hutt",
                    162_500,
                    341_250,
                    "Dark Side or Light Side or Neutral; Jabba the Hutt required as leader",
                ),
                combat(
                    "fennec",
                    "Fennec Shand",
                    162_500,
                    341_250,
                    "Dark Side or Light Side or Neutral; Fennec Shand required",
                ),
                fleet(
                    "fleet",
                    "Fleet",
                    682_500,
                    682_500,
                    "7-star ships; Executor required as the capital ship leader",
                ),
                special(
                    "rey",
                    "Reva Unlock",
                    "Inquisitorius; Grand Inquisitor required as leader",
                    "Third Sister shards",
                ),
                special_unlock(
                    "sm",
                    "Unlock Mandalore",
                    "Bo-Katan (Mand'alor) required as leader; The Mandalorian (Beskar Armor) also required",
                    "15 Mk III Guild Tokens",
                    "mandalore",
                ),
            ],
        ),
        planet(
            "kessel",
            "Kessel",
            "mx",
            "mx",
            4,
            4,
            493_594,
            987_188,
            18_480_000,
            [235_143_105, 400_243_583, 500_304_479],
            8,
            None,
            None,
            Some("Special Mission"),
            None,
            vec![
                combat("cm1", "Top-Left", 219_375, 493_594, "Dark Side or Light Side or Neutral"),
                combat("cm2", "Top-Right", 219_375, 493_594, "Dark Side or Light Side or Neutral"),
                combat(
                    "cm3",
                    "Jabba the Hutt",
                    219_375,
                    493_594,
                    "Dark Side or Light Side or Neutral; Jabba the Hutt required as leader",
                ),
                fleet(
                    "fleet",
                    "Fleet",
                    987_188,
                    987_188,
                    "7-star ships; Ghost required in the starting lineup",
                ),
                special(
                    "sm",
                    "Qi'ra + L3-37",
                    "Qi'ra and L3-37 required",
                    "20 Mk III Guild Event Tokens",
                ),
            ],
        ),
        planet(
            "vandor",
            "Vandor",
            "mx",
            "mx",
            5,
            5,
            721_744,
            1_443_488,
            33_264_000,
            [341_250_768, 620_455_942, 729_948_167],
            8,
            None,
            None,
            Some("Special Mission"),
            None,
            vec![
                combat("cm1", "Bottom", 307_125, 721_744, "Dark Side or Light Side or Neutral"),
                combat("cm2", "Top", 307_125, 721_744, "Dark Side or Light Side or Neutral"),
                combat(
                    "cm3",
                    "Jabba the Hutt",
                    307_125,
                    721_744,
                    "Dark Side or Light Side or Neutral; Jabba the Hutt required as leader",
                ),
                fleet("fleet", "Fleet", 1_443_488, 1_443_488, "7-star ships"),
                special(
                    "sm",
                    "Young Han + Vandor Chewie",
                    "Young Han Solo and Vandor Chewbacca required",
                    "20 Mk III Guild Event Tokens",
                ),
            ],
        ),
        planet(
            "hoth",
            "Hoth",
            "mx",
            "mx",
            6,
            6,
            1_151_719,
            2_303_438,
            86_486_400,
            [582_632_425, 1_059_331_682, 1_246_272_567],
            9,
            None,
            None,
            Some("Special Mission"),
            None,
            vec![
                combat("cm1", "Bottom", 460_668, 1_151_719, "Dark Side or Light Side or Neutral"),
                combat(
                    "cm2",
                    "Top-Middle",
                    460_668,
                    1_151_719,
                    "Dark Side or Light Side or Neutral",
                ),
                combat(
                    "cm3",
                    "Jabba the Hutt",
                    460_668,
                    1_151_719,
                    "Dark Side or Light Side or Neutral; Jabba the Hutt required as leader",
                ),
                special(
                    "sm",
                    "Doctor Aphra / BT-1 / 0-0-0",
                    "Dark Side or Light Side or Neutral; Doctor Aphra required as leader, BT-1 and 0-0-0 also required",
                    "Special mission reward",
                ),
                fleet("fleet", "Fleet", 2_303_438, 2_303_438, "7-star ships"),
            ],
        ),
        planet(
            "coruscant",
            "Coruscant",
            "ls",
            "ls",
            1,
            1,
            200_000,
            400_000,
            10_000_000,
            [116_406_250, 186_250_000, 248_333_333],
            5,
            None,
            None,
            None,
            None,
            vec![
                combat("combat", "Light Side Combat 1", 100_000, 200_000, "Light Side or Neutral"),
                combat("combat2", "Light Side Combat 2", 100_000, 200_000, "Light Side or Neutral"),
                combat("jedi", "Jedi", 100_000, 200_000, "Jedi"),
                combat(
                    "mace",
                    "Mace / Kit",
                    100_000,
                    200_000,
                    "Jedi; Mace Windu required as leader, Kit Fisto also required",
                ),
                fleet(
                    "fleet",
                    "Fleet",
                    400_000,
                    400_000,
                    "7-star ships; Outrider required in the starting lineup",
                ),
            ],
        ),
        planet(
            "bracca",
            "Bracca",
            "ls",
            "ls",
            2,
            2,
            250_000,
            500_000,
            11_000_000,
            [142_265_625, 227_625_000, 303_500_000],
            6,
            None,
            None,
            Some("Bracca SM"),
            Some(30),
            vec![
                combat("jtr", "Left", 125_000, 250_000, "Light Side or Neutral"),
                combat("jedi", "Jedi", 125_000, 250_000, "Jedi"),
                combat("open", "Right", 125_000, 250_000, "Light Side or Neutral"),
                fleet("fleet", "Fleet", 500_000, 500_000, "7-star ships"),
                special_unlock(
                    "sm",
                    "Unlock Zeffo",
                    "Cere Junda required as leader; Jedi Knight Cal Kestis or Cal Kestis required as the only other unit",
                    "15 Mk III Guild Tokens",
                    "zeffo",
                ),
            ],
        ),
        planet(
            "kashyyyk",
            "Kashyyyk",
            "ls",
            "ls",
            3,
            3,
            341_250,
            682_500,
            13_200_000,
            [190_953_125, 305_525_000, 407_366_667],
            7,
            None,
            None,
            Some("Special Mission"),
            None,
            vec![
                combat("wookies", "Wookiees", 162_500, 341_250, "Wookiee"),
                combat(
                    "cm2",
                    "Bottom-Left (Imp Officer)",
                    162_500,
                    341_250,
                    "Light Side or Neutral",
                ),
                combat(
                    "cm3",
                    "Top-Right (Mara Jade)",
                    162_500,
                    341_250,
                    "Light Side or Neutral",
                ),
                fleet(
                    "fleet",
                    "Fleet",
                    682_500,
                    682_500,
                    "7-star ships; Profundity required as the capital ship leader",
                ),
                special(
                    "sm",
                    "Saw Gerrera",
                    "Rebel Fighter; Saw Gerrera required as leader",
                    "50 Mk II Guild Event Tokens",
                ),
            ],
        ),
        planet(
            "lothal",
            "Lothal",
            "ls",
            "ls",
            4,
            4,
            493_594,
            987_188,
            18_480_000,
            [246_742_558, 419_987_333, 524_984_167],
            8,
            None,
            None,
            None,
            None,
            vec![
                combat("jmk", "Jedi", 219_375, 493_594, "Jedi"),
                combat("cm2", "Phoenix", 219_375, 493_594, "Phoenix"),
                combat("cm3", "Light Side Combat", 219_375, 493_594, "Light Side or Neutral"),
                fleet("fleet", "Fleet", 987_188, 987_188, "7-star ships"),
            ],
        ),
        planet(
            "kafrene",
            "Kafrene",
            "ls",
            "ls",
            5,
            5,
            721_744,
            1_443_488,
            33_264_000,
            [341_250_768, 620_455_942, 729_948_167],
            8,
            None,
            None,
            None,
            None,
            vec![
                combat("cm1", "Top", 307_125, 721_744, "Light Side or Neutral"),
                combat("cm2", "Middle", 307_125, 721_744, "Light Side or Neutral"),
                combat("cm3", "Bottom", 307_125, 721_744, "Light Side or Neutral"),
                combat(
                    "cm4",
                    "Cassian Andor + K-2SO",
                    307_125,
                    721_744,
                    "Light Side or Neutral; Cassian Andor and K-2SO required",
                ),
                fleet("fleet", "Fleet", 1_443_488, 1_443_488, "7-star ships"),
            ],
        ),
        planet(
            "scarif",
            "Scarif",
            "ls",
            "ls",
            6,
            6,
            1_151_719,
            2_303_438,
            86_486_400,
            [555_710_999, 1_010_383_635, 1_188_686_629],
            9,
            None,
            None,
            None,
            None,
            vec![
                combat("cm1", "Bottom-Left", 460_668, 1_151_719, "Light Side or Neutral"),
                combat("cm2", "Bottom-Right", 460_668, 1_151_719, "Light Side or Neutral"),
                combat(
                    "cm3",
                    "Baze / Chirrut / SRP",
                    460_668,
                    1_151_719,
                    "Light Side or Neutral; Baze Malbus, Chirrut Imwe, and Scarif Rebel Pathfinder required",
                ),
                combat(
                    "cm4",
                    "Cassian / Pao / K-2SO",
                    460_668,
                    1_151_719,
                    "Light Side or Neutral; Cassian Andor, Pao, and K-2SO required",
                ),
                fleet(
                    "fleet",
                    "Fleet",
                    2_303_438,
                    2_303_438,
                    "7-star ships; Profundity required as the capital ship leader",
                ),
            ],
        ),
        planet(
            "mandalore",
            "Mandalore",
            "bonus",
            "bonus",
            4,
            4,
            493_594,
            987_188,
            18_480_000,
            [197_748_650, 316_397_840, 396_497_300],
            8,
            Some("tatooine"),
            Some(25),
            None,
            None,
            vec![
                combat(
                    "dtmg",
                    "Dark Trooper Moff Gideon",
                    219_375,
                    493_594,
                    "Dark Side or Light Side or Neutral; Dark Trooper Moff Gideon required as leader",
                ),
                combat("cm2", "Mixed Combat", 219_375, 493_594, "Dark Side or Light Side or Neutral"),
                combat(
                    "cm4",
                    "Bo-Katan (Mand'alor)",
                    658_125,
                    1_480_782,
                    "Mandalorian; Bo-Katan (Mand'alor) required as leader; all units R9+",
                ),
                fleet(
                    "fleet",
                    "Fleet",
                    987_188,
                    987_188,
                    "7-star ships; Gauntlet Starfighter required in the starting lineup",
                ),
            ],
        ),
        planet(
            "zeffo",
            "Zeffo",
            "bonus",
            "bonus",
            3,
            3,
            341_250,
            682_500,
            13_200_000,
            [143_589_583, 229_743_333, 287_179_167],
            7,
            Some("bracca"),
            Some(30),
            Some("Clone Trooper Special Mission"),
            None,
            vec![
                combat("ufu_top", "UFU Combat 1", 162_500, 341_250, "Unaligned Force User"),
                combat(
                    "cal",
                    "Jedi Knight Cal Kestis",
                    487_500,
                    1_023_750,
                    "Light Side or Neutral; Jedi Knight Cal Kestis required as leader",
                ),
                combat("ls", "Light Side Combat", 162_500, 341_250, "Light Side or Neutral"),
                fleet(
                    "fleet",
                    "Fleet",
                    682_500,
                    682_500,
                    "7-star ships; Negotiator required as the capital ship leader",
                ),
                special("sm", "Clone Trooper", "Clone Trooper", "50 Mk II Guild Event Tokens"),
            ],
        ),
    ]
}

fn planet(
    id: &str,
    name: &str,
    align: &str,
    chain: &str,
    zone: i64,
    phase: i64,
    cm_points: i64,
    fleet_points: i64,
    ops_val: i64,
    stars: [i64; 3],
    min_relic: i64,
    unlocked_by: Option<&str>,
    unlocked_at: Option<i64>,
    sm_label: Option<&str>,
    sm_threshold: Option<i64>,
    missions: Vec<PlannerMissionDefinition>,
) -> PlannerPlanetDefinition {
    PlannerPlanetDefinition {
        id: id.to_string(),
        name: name.to_string(),
        align: align.to_string(),
        chain: chain.to_string(),
        zone,
        phase,
        cm_points,
        fleet_points,
        ops_val,
        stars: stars.to_vec(),
        min_relic,
        unlocked_by: unlocked_by.map(str::to_string),
        unlocked_at,
        sm_label: sm_label.map(str::to_string),
        sm_threshold,
        missions,
    }
}

fn combat(
    id: &str,
    label: &str,
    points_single: i64,
    points: i64,
    units_text: &str,
) -> PlannerMissionDefinition {
    PlannerMissionDefinition {
        id: id.to_string(),
        label: label.to_string(),
        mission_type: String::from("combat"),
        points_single: Some(points_single),
        points: Some(points),
        reward_text: None,
        units_text: units_text.to_string(),
        note: None,
        unlocks: None,
    }
}

fn fleet(
    id: &str,
    label: &str,
    points_single: i64,
    points: i64,
    units_text: &str,
) -> PlannerMissionDefinition {
    PlannerMissionDefinition {
        id: id.to_string(),
        label: label.to_string(),
        mission_type: String::from("fleet"),
        points_single: Some(points_single),
        points: Some(points),
        reward_text: None,
        units_text: units_text.to_string(),
        note: None,
        unlocks: None,
    }
}

fn special(
    id: &str,
    label: &str,
    units_text: &str,
    reward_text: &str,
) -> PlannerMissionDefinition {
    PlannerMissionDefinition {
        id: id.to_string(),
        label: label.to_string(),
        mission_type: String::from("special"),
        points_single: None,
        points: None,
        reward_text: Some(reward_text.to_string()),
        units_text: units_text.to_string(),
        note: None,
        unlocks: None,
    }
}

fn special_unlock(
    id: &str,
    label: &str,
    units_text: &str,
    reward_text: &str,
    unlocks: &str,
) -> PlannerMissionDefinition {
    PlannerMissionDefinition {
        id: id.to_string(),
        label: label.to_string(),
        mission_type: String::from("special_unlock"),
        points_single: None,
        points: None,
        reward_text: Some(reward_text.to_string()),
        units_text: units_text.to_string(),
        note: None,
        unlocks: Some(unlocks.to_string()),
    }
}
