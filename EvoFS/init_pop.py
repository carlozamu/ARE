"""
Population Initialization Module.
Creates the minimal "Generation 0" starting point.
"""
import random
from typing import Dict, List

from Data.clutrr_wrapper import CLUTTRGeneticPool
from Fitness.fitness import Fitness
from Genome.agent_genome import Genome

async def initialize_population(
    num_individuals: int, 
    dataset_pool: CLUTTRGeneticPool, 
    problems_pool: List[Dict], 
    fitness_evaluator: Fitness,
    min_k: int = 1,
    max_k: int = 6
) -> List[Genome]:
    """
    Initializes Generation 0 with a diverse set of random variable-length 
    few-shot prompt configurations and evaluates them.
    """
    population: List[Genome] = []
    
    print(f"🌱 Initializing Generation 0 with {num_individuals} diverse random genomes...")
    
    # 1. Create a structurally diverse starting population
    for _ in range(num_individuals):
        # Pick a random prompt length for this individual
        k = random.randint(min_k, max_k)
        
        # Populate the sequence with random genes (dataset examples)
        genes = [dataset_pool.create_random_gene() for _ in range(k)]
        
        genome = Genome(genes=genes)
        population.append(genome)

    # 2. Evaluate the entire initial population concurrently.
    # The fitness_evaluator natively handles the chunked concurrency and GPU semaphore limits.
    await fitness_evaluator.evaluate_population(population, problems_pool)

    # Sanity check: Ensure evaluation succeeded
    evaluated_count = sum(1 for ind in population if ind.fitness is not None)
    print(f"✅ Initialization complete. Successfully evaluated {evaluated_count}/{num_individuals} genomes.")

    return population