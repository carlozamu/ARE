import random
from Genome.agent_genome import Genome
from Gene.gene import Gene
from Data.clutrr_wrapper import CLUTTRGeneticPool

class TwoTierMutation:
    """
    Handles Macro (hop changes), Micro (example ID changes), Order Swaps, and Length adjustments.
    """
    def __init__(
        self,
        pool: CLUTTRGeneticPool,
        p_micro: float = 0.4,    # High prob: Fine-tune example ID
        p_macro: float = 0.15,   # Low prob: Shift hop category
        p_swap: float = 0.2,     # Swap position of two shots
        p_length: float = 0.2,   # Expand or contract prompt length
        max_k: int = 6,
        min_k: int = 1
    ):
        self.pool = pool
        self.p_micro = p_micro
        self.p_macro = p_macro
        self.p_swap = p_swap
        self.p_length = p_length
        self.max_k = max_k
        self.min_k = min_k

    def mutate(self, genome: Genome) -> Genome:
        mutated = genome.copy()
        
        # 1. Micro-Mutation (Fine-tuning specific example ID)
        for i in range(mutated.k):
            if random.random() < self.p_micro:
                current_hop = mutated.genes[i].hop_level
                new_id = self.pool.get_random_example(current_hop)
                mutated.genes[i].example_id = new_id

        # 2. Macro-Mutation (Changing structural hop category)
        for i in range(mutated.k):
            if random.random() < self.p_macro:
                new_hop = self.pool.get_random_hop()
                new_id = self.pool.get_random_example(new_hop)
                mutated.genes[i] = Gene(hop_level=new_hop, example_id=new_id)

        # 3. Order Swap Mutation (Exploring order interactions)
        if mutated.k > 1 and random.random() < self.p_swap:
            idx1, idx2 = random.sample(range(mutated.k), 2)
            mutated.genes[idx1], mutated.genes[idx2] = mutated.genes[idx2], mutated.genes[idx1]

        # 4. Length Shift Mutation (Adding/removing a shot)
        if random.random() < self.p_length:
            self._mutate_length(mutated)

        # Invalidate fitness cache if mutated
        mutated.fitness = None
        return mutated

    def _mutate_length(self, genome: Genome) -> None:
        can_expand = genome.k < self.max_k
        can_contract = genome.k > self.min_k

        if can_expand and can_contract:
            expand = random.random() < 0.5
        else:
            expand = can_expand

        if expand and can_expand:
            # Insert a new gene at a random position
            new_gene = self.pool.create_random_gene()
            insert_pos = random.randint(0, genome.k)
            genome.genes.insert(insert_pos, new_gene)
        elif not expand and can_contract:
            # Remove a random gene
            drop_pos = random.randint(0, genome.k - 1)
            genome.genes.pop(drop_pos)