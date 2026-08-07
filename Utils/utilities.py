import gc
import os
import re
from typing import List, Dict, Any, Tuple
import matplotlib.pyplot as plt
import numpy as np
import torch
import pickle
import glob

# --- 1. Plotting Utility ---
class Plotter:
    """
    Encapsulates plotting logic for the VL-HSMA framework.
    Analyzes prompt length efficiency and marginal hop performance.
    """
    def __init__(self):
        # Professional, high-contrast color palette
        self.scatter_color = '#1f77b4'       # Blue for population data points
        self.mean_color = '#d62728'          # Red for statistical means
        self.zs_color = '#000000'            # Black for Zero-Shot
        self.fs_color = '#AC9201'            # Gold for Few-Shot
        self.marker_size = 60

    def _parse_baseline_F(self, baseline_data: dict) -> float:
        """Safely extracts fitness whether passed as a tuple or dict."""
        if not baseline_data:
            return 0.0
        return float(baseline_data.get("fitness", 0.0))

    def _setup_base_plot(self, title: str, xlabel: str, ylabel: str):
        """Standardizes the aesthetic boilerplate for all graphs."""
        plt.figure(figsize=(11, 7), facecolor='#FAFAFA')
        ax = plt.gca()
        ax.set_facecolor('#FAFAFA')
        
        # Subdued grid lines
        ax.grid(True, linestyle='--', color='#E0E0E0', alpha=0.8, zorder=0)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#333333')
        ax.spines['bottom'].set_color('#333333')

        plt.title(title, fontsize=16, fontweight='bold', color='#1A1A1A', pad=20)
        plt.xlabel(xlabel, fontsize=12, fontweight='medium', color='#333333', labelpad=10)
        plt.ylabel(ylabel, fontsize=12, fontweight='medium', color='#333333', labelpad=10)
        
        return ax

    def _plot_baselines(self, ax, zs_fitness: float, fs_fitness: float, x_min: float, x_max: float):
        """Draws horizontal reference lines for baselines spanning the graph."""
        ax.hlines(zs_fitness, xmin=x_min, xmax=x_max, colors=self.zs_color,
                  linestyles='dashed', linewidth=2, label=f'Zero-Shot ({zs_fitness:.1f})', zorder=3)
        ax.hlines(fs_fitness, xmin=x_min, xmax=x_max, colors=self.fs_color,
                  linestyles='dashed', linewidth=2, label=f'Few-Shot ({fs_fitness:.1f})', zorder=3)

    def plot_length_vs_fitness(
        self, 
        population: List[Genome], 
        zero_shot_stats: dict, 
        few_shots_stats: dict, 
        generation_idx: int, 
        output_dir="Utils/Logs/PlotsLength"
    ) -> str:
        """
        Graph 1: Sequence Length (k) vs. Fitness.
        Demonstrates the Pareto efficiency of adding more examples to the prompt.
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        zs_fitness = self._parse_baseline_F(zero_shot_stats)
        fs_fitness = self._parse_baseline_F(few_shots_stats)

        # 1. Extract data mapping k to fitness
        k_values = []
        fitness_values = []
        
        for ind in population:
            if ind.fitness is not None:
                k_values.append(ind.k)
                fitness_values.append(ind.fitness)

        ax = self._setup_base_plot(
            title=f"Generation {generation_idx}: Sequence Length (k) vs. Fitness",
            xlabel="Prompt Length (Number of Examples)",
            ylabel="Fitness Score"
        )

        if not k_values:
            plt.close()
            return ""

        # 2. Add structural jitter to X-axis for dense scatter visibility
        # Example: a genome with k=3 will be plotted somewhere between 2.85 and 3.15
        jittered_k = [k + np.random.uniform(-0.15, 0.15) for k in k_values]
        
        plt.scatter(jittered_k, fitness_values, color=self.scatter_color, 
                    alpha=0.6, s=self.marker_size, edgecolors='white', linewidth=0.5, zorder=4, label='Genomes')

        # 3. Calculate and plot the mean fitness for each discrete length k
        unique_ks = sorted(list(set(k_values)))
        means_x = []
        means_y = []
        for k in unique_ks:
            subset_fitness = [f for length, f in zip(k_values, fitness_values) if length == k]
            means_x.append(k)
            means_y.append(np.mean(subset_fitness))

        # Connect the means to show the trend curve
        plt.plot(means_x, means_y, color=self.mean_color, marker='D', markersize=8, 
                 linewidth=2, label='Mean Fitness per k', zorder=5)

        # 4. Axes & Baselines
        min_k, max_k = min(unique_ks), max(unique_ks)
        self._plot_baselines(ax, zs_fitness, fs_fitness, x_min=max(0, min_k-1), x_max=max_k+1)

        plt.xlim(max(0, min_k - 0.5), max_k + 0.5)
        plt.xticks(unique_ks)
        plt.ylim(0, max(100, max(fitness_values) * 1.1)) # Scaled dynamically up to 100+
        
        plt.legend(loc='upper left', bbox_to_anchor=(1.02, 1), frameon=True, facecolor='white')
        plt.tight_layout()

        filename = f"{output_dir}/gen_{generation_idx}_length_vs_fitness.png"
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close()
        
        return filename

    def plot_hop_vs_marginal_fitness(
        self, 
        population: List[Genome], 
        zero_shot_stats: dict, 
        few_shots_stats: dict, 
        generation_idx: int, 
        output_dir="Utils/Logs/PlotsHop"
    ) -> str:
        """
        Graph 2: Hop Level vs. Marginal Fitness.
        Extracts every individual gene to calculate the weighted impact of specific hop categories.
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        zs_fitness = self._parse_baseline_F(zero_shot_stats)
        fs_fitness = self._parse_baseline_F(few_shots_stats)

        # 1. Unpack genomes into (hop, genome_fitness) pairs
        hop_values = []
        marginal_fitnesses = []
        
        for ind in population:
            if ind.fitness is not None:
                # If a genome has [3, 3, 6] scoring 30, it adds (3,30), (3,30), and (6,30)
                for gene in ind.genes:
                    hop_values.append(gene.hop_level)
                    marginal_fitnesses.append(ind.fitness)

        ax = self._setup_base_plot(
            title=f"Generation {generation_idx}: Marginal Fitness by Hop Level",
            xlabel="Example Complexity (Hop Level)",
            ylabel="Marginal Genome Fitness"
        )

        if not hop_values:
            plt.close()
            return ""

        # 2. Add structural jitter to X-axis
        jittered_hops = [h + np.random.uniform(-0.15, 0.15) for h in hop_values]
        
        plt.scatter(jittered_hops, marginal_fitnesses, color=self.scatter_color, 
                    alpha=0.5, s=self.marker_size, edgecolors='white', linewidth=0.5, zorder=4, label='Gene Occurrences')

        # 3. Calculate and plot the marginal mean (weighted by frequency exactly as you designed)
        unique_hops = sorted(list(set(hop_values)))
        means_x = []
        means_y = []
        for h in unique_hops:
            subset_fitness = [f for hop, f in zip(hop_values, marginal_fitnesses) if hop == h]
            means_x.append(h)
            means_y.append(np.mean(subset_fitness))

        # Connect the means to show how performance drops/rises as hop complexity scales
        plt.plot(means_x, means_y, color=self.mean_color, marker='s', markersize=8, 
                 linewidth=2, label='Mean Marginal Fitness', zorder=5)

        # 4. Axes & Baselines
        min_h, max_h = min(unique_hops), max(unique_hops)
        self._plot_baselines(ax, zs_fitness, fs_fitness, x_min=min_h-1, x_max=max_h+1)

        plt.xlim(min_h - 0.5, max_h + 0.5)
        plt.xticks(unique_hops)
        plt.ylim(0, max(100, max(marginal_fitnesses) * 1.1)) 
        
        plt.legend(loc='upper left', bbox_to_anchor=(1.02, 1), frameon=True, facecolor='white')
        plt.tight_layout()

        filename = f"{output_dir}/gen_{generation_idx}_hop_vs_marginal_fitness.png"
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close()
        
        return filename
    
# --- 2. History Utility ---
class HistoryTracker:
    """
    Maintains a structured history and handles rolling, multi-file checkpoints
    so evolution can be safely interrupted and rolled back to specific generations.
    """
    def __init__(self, checkpoint_dir: str = "vlhsma_checkpoints"):
        self.checkpoint_dir = checkpoint_dir
        
        # Create the directory if it doesn't exist to keep the root folder clean
        if not os.path.exists(self.checkpoint_dir):
            os.makedirs(self.checkpoint_dir)
            
        self.history: List[Tuple[List[Genome], Dict[str, Any]]] = []

    def record_generation(self, population: List['Genome'], zero_shot_stats: Dict, few_shots_stats: Dict) -> None:
        """
        Appends the current generation's flat population and baselines to the run history.
        """
        self.history.append((population, {
            "zero_shot": zero_shot_stats,
            "few_shot": few_shots_stats
        }))

    def save_checkpoint(self, generation_idx: int, population: List['Genome'], zero_shot_stats: Dict, few_shots_stats: Dict) -> None:
        """
        Saves a discrete, atomic state file for the specific generation.
        """
        state = {
            "generation_idx": generation_idx,
            "population": population,
            "zero_shot_stats": zero_shot_stats,
            "few_shots_stats": few_shots_stats,
            "history": self.history
        }
        
        # Name the file explicitly by its generation
        filepath = os.path.join(self.checkpoint_dir, f"vlhsma_checkpoint_gen_{generation_idx}.pkl")
        
        # Use a temporary file to guarantee atomic writes (prevents corruption on sudden crash)
        temp_file = filepath + ".tmp"
        
        with open(temp_file, 'wb') as f:
            pickle.dump(state, f)
            
        os.replace(temp_file, filepath)

    def load_checkpoint(self) -> Dict[str, Any]:
        """
        Scans the checkpoint directory, finds the file with the highest generation 
        number, and loads it.
        """
        if not os.path.exists(self.checkpoint_dir):
            return None
            
        # Find all files matching the checkpoint pattern
        search_pattern = os.path.join(self.checkpoint_dir, "vlhsma_checkpoint_gen_*.pkl")
        checkpoint_files = glob.glob(search_pattern)
        
        if not checkpoint_files:
            return None
            
        # Extract the integer from the filename to safely find the true maximum
        def get_gen_number(filepath: str) -> int:
            match = re.search(r'gen_(\d+)\.pkl$', filepath)
            return int(match.group(1)) if match else -1

        # Locate the file with the highest generation integer
        latest_checkpoint = max(checkpoint_files, key=get_gen_number)
        
        print(f"📂 Found rollback checkpoints. Loading highest available state: {os.path.basename(latest_checkpoint)}")
        
        with open(latest_checkpoint, 'rb') as f:
            state = pickle.load(f)
            
        # Truncate the loaded history array to match the loaded generation.
        # This prevents phantom logs from deleted future generations from remaining in memory.
        loaded_gen = state["generation_idx"]
        self.history = state.get("history", [])[:loaded_gen]
        
        return state
    
# --- 3. Logging Utility ---
def log_and_print(message: str, log_file: str = "Utils/Logs/generation_logger.md"):
    print(message)
    
    # Ensure the logs directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Append the message to the markdown file
    with open(log_file, "a", encoding="utf-8") as f:
        # We strip leading newlines to avoid weird markdown formatting gaps, 
        # but keep the newline at the end for the next log.
        f.write(message.lstrip('\n') + "\n\n")

def just_log(message: str, log_file: str = "few_shots_results_0.txt"):    
    # Ensure the logs directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Append the message to the markdown file
    with open(log_file, "a", encoding="utf-8") as f:
        # We strip leading newlines to avoid weird markdown formatting gaps, 
        # but keep the newline at the end for the next log.
        f.write(message.lstrip('\n') + "\n\n")

def clear_log_file(log_file: str = "Utils/Logs/generation_logger.md"):
    """
    Clears the contents of the log file before a fresh run.
    If the file or directory does not exist, it safely initializes them.
    """
    # 1. Ensure the directory exists first, just in case this function 
    # is called before log_and_print has a chance to create it.
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # 2. Open in 'w' mode. This instantly wipes all existing content.
    # We use 'pass' because we don't need to write anything; the act 
    # of opening it in 'w' mode does all the work.
    with open(log_file, "w", encoding="utf-8") as f:
        pass

def log_generation_to_markdown(population: List['Genome'], 
                               best_accuracy: float, 
                               avg_accuracy: float, 
                               zero_shot_stats: Dict[str, Any], 
                               few_shots_stats: Dict[str, Any], 
                               generation_idx: int,
                               eval_duration: float,
                               log_file: str = "Utils/Logs/generation_logger.md") -> float:
    """
    Evaluates the generation's performance, identifies the top variable-length 
    prompt configurations, and appends a structured Markdown report.
    Returns the global best fitness.
    """
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # 1. Global Computations
    # Ensure all genomes have a valid fitness before sorting (fallback to 0.0)
    valid_population = [ind for ind in population if ind.fitness is not None]
    
    if not valid_population:
        return 0.0

    sorted_pop = sorted(valid_population, key=lambda x: x.fitness, reverse=True)
    global_champion = sorted_pop[0]
    global_best_fitness = global_champion.fitness
    avg_fitness = sum(ind.fitness for ind in valid_population) / len(valid_population)
    
    # 2. Build the Markdown String
    md_lines = []
    
    # --- Header ---
    md_lines.append(f"# 🧬 Generation {generation_idx} Report")
    md_lines.append(f"**Population Size:** {len(valid_population)} | **Global Best Fitness:** {global_best_fitness:.4f}")
    md_lines.append("\n---\n")
    
    # --- Global Performance Table ---
    md_lines.append("### 📊 Macro Performance")
    md_lines.append("| Evaluation | Accuracy | Fitness | Exec Time |")
    md_lines.append("| :--------- | :------: | :-----: | :-------: |")
    md_lines.append(f"| **VL-HSMA (Pop Best/Avg)** | {best_accuracy:.2f}% / {avg_accuracy:.2f}% | Best: {global_best_fitness:.4f} / Avg: {avg_fitness:.4f} | {eval_duration:.2f}s |")
    
    # Safely unpack baseline stats if provided
    if zero_shot_stats:
        md_lines.append(f"| **Zero-Shot Baseline** | {zero_shot_stats.get('accuracy', 0):.2f}% | {zero_shot_stats.get('fitness', 0):.4f} | {zero_shot_stats.get('execution_time', 0):.2f}s |")
    if few_shots_stats:
        md_lines.append(f"| **Few-Shot Baseline**  | {few_shots_stats.get('accuracy', 0):.2f}% | {few_shots_stats.get('fitness', 0):.4f} | {few_shots_stats.get('execution_time', 0):.2f}s |")
    
    md_lines.append("\n---\n")
    
    # --- Structural Champions (Top 3 Genomes) ---
    md_lines.append("### 🏆 Top 3 Prompt Configurations")
    
    # Log the top 3 distinct configurations to observe sequence diversity
    for i, ind in enumerate(sorted_pop[:3]):
        md_lines.append(f"#### Rank {i + 1}")
        md_lines.append(f"- **Fitness:** {ind.fitness:.4f}")
        md_lines.append(f"- **Accuracy:** {ind.accuracy:.2f}%")
        md_lines.append(f"- **Avg Prompt+Response Tokens:** {ind.avg_tokens:.1f}")
        md_lines.append(f"- **Prompt Length ($k$):** {ind.k} examples")
        
        # Format the macro and micro structures clearly
        # Macro: (3, 3, 7)
        md_lines.append(f"- **Macro-Sequence Pattern:** `{ind.get_sequence_pattern()}`")
        
        # Micro: [Hop 3, ID 14] -> [Hop 3, ID 02] -> [Hop 7, ID 88]
        seq_str = " ➔ ".join([f"[Hop {g.hop_level}, ID {g.example_id}]" for g in ind.genes])
        md_lines.append(f"- **Micro-Structure Detail:** `{seq_str}`")
        md_lines.append("\n<br>\n") 
        
    md_lines.append("\n====================================================================\n")

    # 3. Write to File
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
        
    return global_best_fitness
# GPU Utility
def force_cleanup():
    """Releases GPU memory."""
    print("\n🧹 Performing Memory Cleanup...")
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
    print("✅ GPU Memory Released.")

