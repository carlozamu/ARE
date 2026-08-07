"""
VL-HSMA: Variable-Length Hierarchical Sequence Memetic Algorithm
Main Execution Script for Few-Shot Prompt Evolution
"""
import asyncio
import time
import subprocess
import os

# --- Internal Modules ---
from Fitness.fitness import Fitness
from Genome.agent_genome import Genome
from Mutations.mutator import TwoTierMutation
from Crossover.crossover import Crossover
from Selection.selection import TwoTierMacroDiversitySelection
from Data.clutrr import CLUTTRManager
from Data.clutrr_wrapper import CLUTTRGeneticPool
from Population.initializer import initialize_population
from Utils.utilities import log_generation_to_markdown, log_and_print, clear_log_file, Plotter, force_cleanup, HistoryTracker
from Utils.LLM import LLM

# --- Configuration ---
MODEL_NAME = "google/gemma-3-1b-it" 
BASE_URL = "http://localhost:8000"  
MAX_GENERATIONS = 50
MAX_TIME_SECONDS = 3600 * 15 # 15 Hours
TARGET_FITNESS = 95.0        # Higher is better
NUM_INDIVIDUALS = 50
ELITISM_COUNT = 2            # Number of top performers carried over unmodified

async def run_evolution():
    # 1. Initialize API and Core Tools
    llm_client = LLM(model_name=MODEL_NAME, base_url=BASE_URL) 
    fitness_evaluator = Fitness(llm=llm_client, use_reasoning=False)
    
    # 2. Setup Data Pipeline
    dataset_manager = CLUTTRManager(split_config="gen_train234_test2to10")
    dataset = dataset_manager.get_or_create_curated_dataset(6) 
    genetic_pool = CLUTTRGeneticPool(manager=dataset_manager, source_split="train")
    
    # 3. Setup Genetic Operators
    selector = TwoTierMacroDiversitySelection(selection_pressure=1.5, max_per_niche_ratio=0.3)
    crossover_op = Crossover(max_k=6, min_k=1)
    mutator = TwoTierMutation(pool=genetic_pool, p_micro=0.4, p_macro=0.15, p_swap=0.2, p_length=0.2)
    
    plotter = Plotter()
    history_manager = HistoryTracker()
    
    start_time = time.time()
    
    # --- Dummy Baselines (Replace with actual evaluation if needed) ---
    zero_shot_stats = {"accuracy": 15.0, "fitness": 15.0, "execution_time": 0.0}
    few_shots_stats = {"accuracy": 25.0, "fitness": 25.0, "execution_time": 0.0}

    # ==========================================
    # 3. STATE RECOVERY & POPULATION SETUP
    # ==========================================
    checkpoint_state = history_manager.load_checkpoint()

    if checkpoint_state:
        log_and_print("\n🔄 Valid Checkpoint Found. Rehydrating State...")
        generation_idx = checkpoint_state["generation_idx"]
        population = checkpoint_state["population"]
        zero_shot_stats = checkpoint_state["zero_shot_stats"]
        few_shots_stats = checkpoint_state["few_shots_stats"]
        log_and_print(f"✅ Evolution successfully resumed. Targeting Generation {generation_idx}")
    else:
        log_and_print("\n--- Initializing VL-HSMA System ---")
        clear_log_file() 
        generation_idx = 0
        
        start_init_time = time.time()
        population = await initialize_population(
            num_individuals=NUM_INDIVIDUALS, 
            dataset_pool=genetic_pool, 
            problems_pool=dataset, 
            fitness_evaluator=fitness_evaluator,
            min_k=1, max_k=6
        )
        init_duration = time.time() - start_init_time
        
        log_and_print(f"✅ Generation 0 Initialized in {init_duration:.2f}s.")
        
        # Initial Logging & Plotting
        best_acc = max((ind.accuracy for ind in population if ind.accuracy is not None), default=0)
        avg_acc = sum(ind.accuracy for ind in population if ind.accuracy is not None) / max(1, len(population))
        
        log_generation_to_markdown(population, best_acc, avg_acc, zero_shot_stats, few_shots_stats, generation_idx, init_duration)
        history_manager.record_generation(population, zero_shot_stats, few_shots_stats)
        
        plot_path_1 = plotter.plot_length_vs_fitness(population, zero_shot_stats, few_shots_stats, generation_idx)
        plot_path_2 = plotter.plot_hop_vs_marginal_fitness(population, zero_shot_stats, few_shots_stats, generation_idx)
        
        if os.path.exists(plot_path_1): subprocess.Popen(['xdg-open', plot_path_1])
        if os.path.exists(plot_path_2): subprocess.Popen(['xdg-open', plot_path_2])
        
        generation_idx = 1
        history_manager.save_checkpoint(generation_idx, population, zero_shot_stats, few_shots_stats)

    # ==========================================
    # 4. MAIN EVOLUTION LOOP
    # ==========================================
    log_and_print("\n🚀 Starting Evolution Loop...")

    while generation_idx <= MAX_GENERATIONS:
        gen_start_time = time.time()
        
        # A. BREEDING & GENETIC OPERATIONS
        log_and_print(f"\n🧬 Breeding Generation {generation_idx}...")
        
        # Sort population to identify elites
        population.sort(key=lambda x: x.fitness if x.fitness is not None else -1, reverse=True)
        
        next_generation: list[Genome] = []
        
        # 1. Elitism: Preserve the absolute best individuals unchanged
        for i in range(min(ELITISM_COUNT, len(population))):
            next_generation.append(population[i].copy())
            
        # 2. Parent Selection
        parents_needed = NUM_INDIVIDUALS - ELITISM_COUNT
        parents = selector.select(population, parents_needed)
        
        # 3. Crossover & Mutation
        for i in range(0, len(parents), 2):
            if i + 1 < len(parents):
                child1, child2 = crossover_op.mate(parents[i], parents[i+1])
                next_generation.extend([mutator.mutate(child1), mutator.mutate(child2)])
            else:
                next_generation.append(mutator.mutate(parents[i]))
                
        # Truncate to exact population size just in case
        next_generation = next_generation[:NUM_INDIVIDUALS]

        # B. EVALUATION
        log_and_print(f"🧪 Evaluating {len(next_generation)} offspring on {len(dataset)} problems...")
        eval_start_time = time.time()
        await fitness_evaluator.evaluate_population(next_generation, dataset)
        eval_duration = time.time() - eval_start_time
        
        # C. LOGGING & ANALYTICS
        population = next_generation
        
        best_acc = max((ind.accuracy for ind in population if ind.accuracy is not None), default=0)
        avg_acc = sum(ind.accuracy for ind in population if ind.accuracy is not None) / max(1, len(population))
        
        best_fit = log_generation_to_markdown(
            population, best_acc, avg_acc, zero_shot_stats, few_shots_stats, generation_idx, eval_duration
        )
        
        log_and_print(f"\n📊 Generation {generation_idx} Summary:")
        log_and_print(f"ERA run in {eval_duration:.2f}s. Best Accuracy: {best_acc:.2f}%, Best Fitness: {best_fit:.4f}") 
        log_and_print("-" * 30)

        # D. PLOTTING
        history_manager.record_generation(population, zero_shot_stats, few_shots_stats)
        
        plot_path_1 = plotter.plot_length_vs_fitness(population, zero_shot_stats, few_shots_stats, generation_idx)
        plot_path_2 = plotter.plot_hop_vs_marginal_fitness(population, zero_shot_stats, few_shots_stats, generation_idx)
        
        if os.path.exists(plot_path_1): subprocess.Popen(['xdg-open', plot_path_1])
        if os.path.exists(plot_path_2): subprocess.Popen(['xdg-open', plot_path_2])

        # E. CHECKPOINTING & STOP CRITERIA
        generation_idx += 1
        history_manager.save_checkpoint(generation_idx, population, zero_shot_stats, few_shots_stats)

        if best_fit >= TARGET_FITNESS:
            log_and_print(f"\n🏆 SUCCESS: Target Fitness ({TARGET_FITNESS}) reached! Final Best: {best_fit:.4f}")
            break
        if (time.time() - start_time) > MAX_TIME_SECONDS:
            log_and_print(f"\n🛑 STOP: Maximum time limit ({MAX_TIME_SECONDS}s) reached.")
            break

    log_and_print("--- Evolution Finished ---")
    force_cleanup()

    # Final Evaluation Output
    population.sort(key=lambda x: x.fitness if x.fitness is not None else -1, reverse=True)
    best_overall = population[0]
    print(f"🏆 Final Best Prompt Length: {best_overall.k}")
    print(f"🏆 Final Best Macro-Pattern: {best_overall.get_sequence_pattern()}")
    print(f"🏆 Final Best Accuracy: {best_overall.accuracy:.4f}%")

if __name__ == "__main__":
    try:
        asyncio.run(run_evolution())
    finally:
        force_cleanup()