from typing import List, Tuple
import random
from Genome.agent_genome import Genome
from Gene.gene import Gene

class Crossover:
    """
    Variable-length position-aware crossover.
    Inherits prompt length dynamically from parents and transfers whole slots.
    """
    def __init__(self, max_k: int = 6, min_k: int = 1):
        self.max_k = max_k
        self.min_k = min_k

    def mate(self, parent1: Genome, parent2: Genome) -> Tuple[Genome, Genome]:
        child1_genes = self._mix_genes(parent1, parent2)
        child2_genes = self._mix_genes(parent2, parent1)

        return Genome(child1_genes), Genome(child2_genes)

    def _mix_genes(self, primary: Genome, secondary: Genome) -> List[Gene]:
        # Choose child length bounded between parents or within limits
        child_k = random.randint(
            max(self.min_k, min(primary.k, secondary.k)),
            min(self.max_k, max(primary.k, secondary.k))
        )

        child_genes = []
        for i in range(child_k):
            # If position exists in both, pick 50/50
            if i < primary.k and i < secondary.k:
                chosen_parent = primary if random.random() < 0.5 else secondary
                child_genes.append(chosen_parent.genes[i].copy())
            # Otherwise inherit from whichever parent has a gene at position i
            elif i < primary.k:
                child_genes.append(primary.genes[i].copy())
            else:
                child_genes.append(secondary.genes[i].copy())

        return child_genes