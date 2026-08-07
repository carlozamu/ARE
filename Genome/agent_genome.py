from typing import List, Optional, Tuple
from Gene.gene import Gene

class Genome:
    """
    Represents a full variable-length few-shot prompt configuration.
    """
    def __init__(self, genes: List[Gene]):
        self.genes = genes
        self.fitness: Optional[float] = None  # Cached fitness evaluation

    @property
    def k(self) -> int:
        """Returns current prompt length (number of shots)."""
        return len(self.genes)

    def copy(self) -> 'Genome':
        cloned_genes = [gene.copy() for gene in self.genes]
        cloned = Genome(cloned_genes)
        cloned.fitness = self.fitness
        return cloned

    def get_sequence_pattern(self) -> Tuple[int, ...]:
        """Returns the macro sequence of hop levels (e.g., (3, 3, 7))."""
        return tuple(g.hop_level for g in self.genes)

    def __repr__(self) -> str:
        pattern = self.get_sequence_pattern()
        return f"Genome(k={self.k}, hops={pattern}, fitness={self.fitness})"

    def get_samples(self) -> str:
        """Returns the list of sample texts from the genes in a single string ready to be injected in the prompt."""
        examples_string = ""
        for gene in self.genes:
            if gene.problem is None or gene.answer is None or gene.names is None:
                raise ValueError(f"Gene {gene} has missing problem or answer.")
            examples_string += f"""<start_of_turn>user
Story: {gene.problem}
CRITICAL TASK: State the family relationship. Output EXACTLY ONE WORD from the list above. {gene.names[0]} is {gene.names[1]}'s?<end_of_turn>
<start_of_turn>model
{gene.answer}<end_of_turn>
"""

        return examples_string
            