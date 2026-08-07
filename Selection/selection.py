"""
Selection logic for the Reasoning Agent Engine (RAE).
Provides Rank-Based Selection and Multi-Tier Diversity Preserving Selection.
"""
from abc import ABC, abstractmethod
from typing import List, Protocol, TypeVar, Tuple
import numpy as np


class Evolvable(Protocol):
    """Protocol defining the minimum requirements for a genome in the selection process."""
    fitness: float


T = TypeVar('T', bound=Evolvable)


class SelectionStrategy(ABC):
    """Base class establishing the contract for parent selection."""

    @abstractmethod
    def select(self, population: List[T], num_parents: int) -> List[T]:
        """Selects a specified number of parents from the population."""
        pass

    def _validate_population(self, population: List[T]) -> None:
        """Ensures the population is valid and compatible."""
        if not population:
            raise ValueError("Population cannot be empty.")
        if not all(hasattr(ind, 'fitness') for ind in population):
            raise ValueError("Each individual in the population must have a 'fitness' attribute.")


class LinearRankSelection(SelectionStrategy):
    """
    Fixed and mathematically correct Linear Rank-Based Parent Selection (Baker, 1985).
    Sorts population by fitness and assigns selection probabilities linearly based on rank.
    """

    def __init__(self, selection_pressure: float = 1.5):
        """
        Args:
            selection_pressure: Controls bias towards top performers.
                Range: [1.0, 2.0].
                1.0 = purely uniform random selection (no pressure).
                2.0 = maximum bias toward Rank 1 (best).
        """
        if not (1.0 <= selection_pressure <= 2.0):
            raise ValueError("Selection pressure must be between 1.0 and 2.0")
        self.selection_pressure = selection_pressure

    def select(self, population: List[T], num_parents: int) -> List[T]:
        self._validate_population(population)

        n = len(population)
        if n == 1:
            return [population[0]] * num_parents

        # 1. Sort ascending by fitness: Index 0 is worst (Rank 1), Index n-1 is best (Rank n)
        sorted_pop = sorted(population, key=lambda x: x.fitness, reverse=False)

        # 2. Vectorized Baker Linear Ranking Calculation
        # Rank array r ranges from 1 (worst) to n (best)
        ranks = np.arange(1, n + 1)
        s = self.selection_pressure

        # Standard Baker formula: P(r) = (2 - s)/n + 2*r*(s - 1) / (n * (n - 1))
        probabilities = (2 - s) / n + (2 * ranks * (s - 1)) / (n * (n - 1))

        # Normalize to account for floating point errors
        probabilities /= probabilities.sum()

        # 3. Sample parents with replacement
        selected_indices = np.random.choice(
            n,
            size=num_parents,
            replace=True,
            p=probabilities
        )

        return [sorted_pop[idx] for idx in selected_indices]


class TwoTierMacroDiversitySelection(SelectionStrategy):
    """
    Selection strategy specifically designed for Variable-Length Hop-Sequence GAs.
    
    Prevents premature convergence by grouping individuals into niches based on their
    Macro Hop-Sequence Pattern (e.g., (3, 3, 7)), performing rank selection within niches,
    and sampling across distinct macro-patterns to preserve structural diversity.
    """

    def __init__(self, selection_pressure: float = 1.5, max_per_niche_ratio: float = 0.3):
        """
        Args:
            selection_pressure: Rank selection pressure within/across niches [1.0, 2.0].
            max_per_niche_ratio: Maximum fraction of total parents that can come from 
                                 a single hop-sequence pattern.
        """
        self.rank_selector = LinearRankSelection(selection_pressure=selection_pressure)
        self.max_per_niche_ratio = max_per_niche_ratio

    def select(self, population: List[T], num_parents: int) -> List[T]:
        self._validate_population(population)

        # 1. Group population into niches based on macro-sequence pattern
        # Assumes individual has get_sequence_pattern() or falls back to hop extraction
        niches = {}
        for ind in population:
            if hasattr(ind, 'get_sequence_pattern'):
                pattern = ind.get_sequence_pattern()
            else:
                pattern = tuple(getattr(g, 'hop_level', g) for g in getattr(ind, 'genes', []))

            if pattern not in niches:
                niches[pattern] = []
            niches[pattern].append(ind)

        # 2. Select top representatives from each niche to avoid one hop pattern taking over
        cap_per_niche = max(1, int(num_parents * self.max_per_niche_ratio))
        parent_pool = []

        for pattern, niche_pop in niches.items():
            # Perform rank selection within the niche
            k_select = min(len(niche_pop), cap_per_niche)
            niche_parents = self.rank_selector.select(niche_pop, num_parents=k_select)
            parent_pool.extend(niche_parents)

        # 3. Sample final parents from the diverse parent pool using rank selection
        return self.rank_selector.select(parent_pool, num_parents=num_parents)