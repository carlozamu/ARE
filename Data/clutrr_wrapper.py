import random
import re
from typing import Dict, List, Optional
from Gene.gene import Gene
from Data.clutrr import CLUTTRManager
# Assuming CLUTTRManager is imported here

class CLUTTRGeneticPool:
    """
    An adapter that wraps the CLUTTRManager to provide O(1) random sampling 
    and protocol compliance for the Variable-Length Hierarchical Sequence Memetic Algorithm.
    """
    def __init__(self, manager: CLUTTRManager, source_split: str = "train"):
        self.manager = manager
        # Structure: { hop_level: { example_id: dict_of_data } }
        self.pool_data: Dict[int, Dict[int, dict]] = {}
        self.available_hops: List[int] = []
        
        self._build_index(source_split)

    def _build_index(self, split: str) -> None:
        """
        Pre-computes and indexes the dataset to avoid string parsing during the GA loop.
        Groups data by hop_level and assigns integer IDs.
        """
        if self.manager.dataset is None or split not in self.manager.dataset:
            raise ValueError(f"Dataset split '{split}' not found or dataset not loaded.")

        data_split = self.manager.dataset[split]
        print(f"Indexing {len(data_split)} examples from '{split}' for genetic pooling...")

        # We use a running integer counter because standard CLUTRR IDs are strings, 
        # but our Gene class expects an integer example_id.
        internal_id_counter = 0

        for item in data_split:
            story = item.get("story", "")
            query = item.get("query", "")
            target = item.get("target_text", "")
            task_name = item.get("task_name", "")
            
            # 1. Extract hop level
            try:
                hop_level = int(task_name.split(".")[1])
            except (IndexError, ValueError):
                continue  # Skip malformed data
            
            # 2. Extract Names (Reusing your CLUTTRManager logic)
            clean_query = query.replace("(", "").replace(")", "").replace("'", "")
            try:
                name1, name2 = [name.strip() for name in clean_query.split(',')]
            except ValueError:
                name1, name2 = "Person A", "Person B"
                
            # 3. Store in structured format
            if hop_level not in self.pool_data:
                self.pool_data[hop_level] = {}
                
            self.pool_data[hop_level][internal_id_counter] = {
                "example_id": internal_id_counter,
                "original_id": item.get("id", None), # Keep original ID for reference if needed
                "problem": story,
                "answer": target,
                "names": (name1, name2)
            }
            
            internal_id_counter += 1

        self.available_hops = list(self.pool_data.keys())
        print(f"Index built successfully. Available hop levels: {sorted(self.available_hops)}")

    # --- DatasetPoolProtocol Implementation ---

    def get_random_hop(self) -> int:
        """Returns a random available hop category."""
        return random.choice(self.available_hops)

    def get_example(self, hop_level: int, example_id: int) -> dict:
        """Retrieves a specific example's full data dict."""
        if hop_level not in self.pool_data:
            raise KeyError(f"Hop level {hop_level} does not exist in the pool.")
        if example_id not in self.pool_data[hop_level]:
            raise KeyError(f"Example ID {example_id} does not exist in hop level {hop_level}.")
            
        return self.pool_data[hop_level][example_id]

    def get_random_example_data(self, hop_level: int) -> dict:
        """Returns a random full data dict for a given hop level."""
        if hop_level not in self.pool_data:
            raise KeyError(f"Hop level {hop_level} does not exist in the pool.")
            
        # random.choice doesn't work directly on dict_values, so we pick a random key
        random_id = random.choice(list(self.pool_data[hop_level].keys()))
        return self.pool_data[hop_level][random_id]

    def create_random_gene(self, hop_level: Optional[int] = None) -> Gene:
        """Constructs and returns a fully populated Gene object."""
        if hop_level is None:
            hop_level = self.get_random_hop()
            
        example_data = self.get_random_example_data(hop_level)
        
        return Gene(
            hop_level=hop_level,
            example_id=example_data["example_id"],
            problem=example_data["problem"],
            answer=example_data["answer"],
            names=example_data["names"]
        )