import random
from Genome.agent_genome import Genome
from Gene.gene import Gene
from Data.clutrr_wrapper import CLUTTRGeneticPool


class TwoTierMutation:
    """
    Handles Macro (hop changes), Micro (example ID changes), Order Swaps, and Length adjustments
    for multi-attribute Gene objects.
    """
    def __init__(
        self,
        pool: CLUTTRGeneticPool,
        p_micro: float = 0.4,    # Fine-tune example within the same hop
        p_macro: float = 0.15,   # Shift hop category entirely
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
        has_changed = False

        # 1. Micro-Mutation (Sampling a new example under the existing hop level)
        for i in range(mutated.k):
            if random.random() < self.p_micro:
                current_hop = mutated.genes[i].hop_level
                mutated.genes[i] = self.pool.create_random_gene(hop_level=current_hop)
                has_changed = True

        # 2. Macro-Mutation (Changing structural hop category entirely)
        for i in range(mutated.k):
            if random.random() < self.p_macro:
                new_hop = self.pool.get_random_hop()
                mutated.genes[i] = self.pool.create_random_gene(hop_level=new_hop)
                has_changed = True

        # 3. Order Swap Mutation (Exploring positional sequence effects)
        if mutated.k > 1 and random.random() < self.p_swap:
            idx1, idx2 = random.sample(range(mutated.k), 2)
            mutated.genes[idx1], mutated.genes[idx2] = mutated.genes[idx2], mutated.genes[idx1]
            has_changed = True

        # 4. Length Shift Mutation (Adding/removing a shot)
        if random.random() < self.p_length:
            length_changed = self._mutate_length(mutated)
            if length_changed:
                has_changed = True

        # Invalidate fitness cache if any mutation operation occurred
        if has_changed:
            mutated.fitness = None

        return mutated

    def _mutate_length(self, genome: Genome) -> bool:
        can_expand = genome.k < self.max_k
        can_contract = genome.k > self.min_k

        if not can_expand and not can_contract:
            return False

        expand = random.random() < 0.5 if (can_expand and can_contract) else can_expand

        if expand and can_expand:
            # Create a fully populated Gene via the pool
            new_gene = self.pool.create_random_gene()
            insert_pos = random.randint(0, genome.k)
            genome.genes.insert(insert_pos, new_gene)
            return True
            
        elif not expand and can_contract:
            drop_pos = random.randint(0, genome.k - 1)
            genome.genes.pop(drop_pos)
            return True

        return False