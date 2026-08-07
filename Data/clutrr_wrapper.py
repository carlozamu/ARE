import random
import re
from typing import Dict, List, Optional
from Gene.gene import Gene
from Data.clutrr import CLUTTRManager


class CLUTTRGeneticPool:
    """
    An adapter that wraps the CLUTTRManager to provide O(1) random sampling 
    and protocol compliance for the Variable-Length Hierarchical Sequence Memetic Algorithm.
    """
    def __init__(self, manager: CLUTTRManager, source_split: str = "all"):
        self.manager = manager
        # Structure: { hop_level: { example_id: dict_of_data } }
        self.pool_data: Dict[int, Dict[int, dict]] = {}
        self.available_hops: List[int] = []
        
        self._build_index(source_split)

    def _build_index(self, split_request: str) -> None:
        """
        Pre-computes and indexes the dataset. 
        If split_request is 'all', it aggregates train, validation, and test splits.
        """
        if self.manager.dataset is None:
            raise ValueError("Dataset not loaded in manager.")

        # Determine which splits to map
        if split_request == "all":
            splits_to_index = list(self.manager.dataset.keys())
        else:
            if split_request not in self.manager.dataset:
                raise ValueError(f"Dataset split '{split_request}' not found.")
            splits_to_index = [split_request]

        print(f"Indexing examples from splits: {splits_to_index} for genetic pooling...")

        internal_id_counter = 0

        for split in splits_to_index:
            data_split = self.manager.dataset[split]
            for item in data_split:
                story = item.get("story", "")
                query = item.get("query", "")
                target = item.get("target_text", "")
                task_name = item.get("task_name", "")
                
                # Extract hop level
                try:
                    hop_level = int(task_name.split(".")[1])
                except (IndexError, ValueError):
                    continue  # Skip malformed data
                
                # Extract Names
                clean_query = query.replace("(", "").replace(")", "").replace("'", "")
                try:
                    name1, name2 = [name.strip() for name in clean_query.split(',')]
                except ValueError:
                    name1, name2 = "Person A", "Person B"
                    
                # Store in structured format
                if hop_level not in self.pool_data:
                    self.pool_data[hop_level] = {}
                    
                self.pool_data[hop_level][internal_id_counter] = {
                    "example_id": internal_id_counter,
                    "original_id": item.get("id", None), 
                    "problem": story,
                    "answer": target,
                    "names": (name1, name2)
                }
                
                internal_id_counter += 1

        self.available_hops = list(self.pool_data.keys())
        print(f"Index built successfully. Available hop levels: {sorted(self.available_hops)}")
        print(f"Total examples loaded into genetic pool: {internal_id_counter}")

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