"""
ERA: Evolving Reasoning Agents
Baseline Execution Script (No Primer + Logging)
"""
import asyncio
import os
import sys
import time
import gc
import torch
from tqdm.asyncio import tqdm

# Get the absolute path of the directory one level up (RAE)
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

# Append it to sys.path if it's not already there
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# --- Internal Modules ---
from Fitness.fitness import Fitness
from Data.clutrr import CLUTTRManager
from Utils.LLM import LLM
from Utils.utilities import just_log, log_and_print

# AUTO-GENERATED PROMPT TEMPLATES

PROMPT_TEMPLATE = {
    'uniform_median0': f"""<start_of_turn>user
Story: [Dorothy] and her sisters [Katherine] went to the spa. [Erica], another sister of [Dorothy], had to babysit and could n't join them. [Mary]'s daughter [Erica] went to grab dinner. [Mary]'s husband, [Daniel], was not happy about it. [Erica]'s son, [Michael], went to have lunch with her sister, [Katherine].
CRITICAL TASK: State the family relationship. Output EXACTLY ONE WORD from the list above. Michael is Daniel's?<end_of_turn>
<start_of_turn>model
grandson<end_of_turn>
<start_of_turn>user
Story: [Dorothy] went to lunch with her son [Arthur] and her sister [Bonnie]. [Mary] spent a great day shopping with her daughter, [Bonnie]. [Lilly] went to her brother [Warren]'s birthday party [Arthur] went to the game with his sister [Lilly]. [Seth] played chess with his brother [Warren].
CRITICAL TASK: State the family relationship. Output EXACTLY ONE WORD from the list above. Seth is Mary's?<end_of_turn>
<start_of_turn>model
grandson<end_of_turn>
<start_of_turn>user
Story: [Mary] had to work a double shift and needed someone to watch her son [Robert]. Luckily his sister [Erica] was free. [Erica]'s husband, [Joseph], went skiing with his son, [Ross]. [Ross] and his brother [Michael] went to the park to play basketball. [Mary] and her daughter [Bonnie] went to see a movie yesterday and then got ice cream afterwards.
CRITICAL TASK: State the family relationship. Output EXACTLY ONE WORD from the list above. Michael is Bonnie's?<end_of_turn>
<start_of_turn>model
nephew<end_of_turn>
"""
}

# --- Configuration ---
MODEL_NAME = "google/gemma-3-1b-it" 
BASE_URL = "http://localhost:8000"  
MAX_CONCURRENT_REQUESTS = 50

def force_cleanup():
    print("\n🧹 Performing Memory Cleanup...")
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
    print("✅ GPU Memory Released.")

async def _evaluate_single_problem(idx, problem, llm_client, fitness, semaphore):
    """Worker function with index tracking for debug printing."""
    async with semaphore:
        prompt = problem['question']

        try:
            generated_ans = await llm_client.generate_text(user_prompt=prompt, temperature=0.0)
            #if idx % 100 == 0:
                #print(f"Processed {idx} - Answer: '{generated_ans}'")
            token_used = (len(prompt) + len(generated_ans)) // 4
        except Exception as e:
            print(f"Error executing few-shot prompt: {e}")
            generated_ans = ""
            token_used = len(prompt) // 4

        # Clean the generated answer for word counting and logging
        clean_ans = generated_ans.strip()
        
        # 1. Get the exact word count
        answer_length = len(clean_ans.split())

        expected = problem['answer']
        is_correct = False
        
        if problem.get('task_type') == 'cluttr':
            mapped_response = CLUTTRManager.map_to_relation(clean_ans.lower())
            is_correct = (mapped_response == expected)
        else:
            is_correct = (clean_ans.lower() == expected.strip().lower())

        score = fitness.calculator.compute_score(
            is_correct=is_correct,
            token_count=token_used,
            answer_length=answer_length
        )
        
        return is_correct, score, answer_length

async def run_few_shots():
    print("\n--- Initializing ERA Few-Shot ---")
    
    llm_client = LLM(model_name=MODEL_NAME, base_url=BASE_URL)
    dataset_manager = CLUTTRManager(split_config="gen_train234_test2to10")
    fitness = Fitness(llm=llm_client)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(script_dir, "few_shots_results_5.txt")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    with open(log_file, "w", encoding="utf-8") as f:
        pass
    
    for name, examples in PROMPT_TEMPLATE.items():
        start_time = time.time()
        # 2. Fetch the ENTIRE dataset
        log_and_print(f"Fetching the COMPLETE dataset for stratified few-shot with examples {name}", log_file)
        initial_problems_pool = dataset_manager.get_entire_dataset_stratified(dataset_manager.build_prompt_clutrr_few_shots, examples)

        print(f"Starting Few-Shot evaluation with {MAX_CONCURRENT_REQUESTS} concurrent workers...\n")
        
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        
        tasks = [
            _evaluate_single_problem(idx, problem, llm_client, fitness, semaphore)
            for idx, problem in enumerate(initial_problems_pool)
        ]
        
        # 3. Fire tasks
        results = await tqdm.gather(*tasks, desc="Evaluating Problems")

        # 4. Stratified Aggregation & Word Count Tracking
        stratified_stats = {}
        total_correct = 0
        total_score = 0.0
        
        # NEW: Variables for tracking word counts
        total_1_word = 0
        total_2_word = 0
        total_words_generated = 0

        for idx, (is_correct, score, answer_length) in enumerate(results):
            length = initial_problems_pool[idx]['metadata']['reasoning_length']
            
            # Update Word Count Metrics
            total_words_generated += answer_length
            if answer_length == 1:
                total_1_word += 1
            elif answer_length == 2:
                total_2_word += 1
            
            # Update Stratified Metrics
            if length not in stratified_stats:
                stratified_stats[length] = {"correct": 0, "total": 0}
                
            stratified_stats[length]["total"] += 1
            total_score += score
            
            if is_correct:
                stratified_stats[length]["correct"] += 1
                total_correct += 1

        execution_time = time.time() - start_time

        # 5. Output the Stratified Report
        total_problems = len(initial_problems_pool)
        
        just_log("\n" + "="*50, log_file)
        just_log("🎯 STRATIFIED FEW SHOTS REPORT", log_file)
        just_log("="*50, log_file)
        just_log(f"Execution Time: {execution_time:.2f} seconds", log_file)
        just_log(f"Total Problems Evaluated: {total_problems}\n",log_file)

        # Sort the dictionary by reasoning length to print in order
        for length in sorted(stratified_stats.keys()):
            stats = stratified_stats[length]
            acc = (stats["correct"] / stats["total"]) * 100 if stats["total"] > 0 else 0
            just_log(f"Level {length:02d} Hops: Accuracy {acc:05.2f}% ({stats['correct']}/{stats['total']})",log_file)

        just_log("-" * 50, log_file)
        overall_accuracy = (total_correct / total_problems) * 100
        overall_fitness = total_score / total_problems
        average_length = total_words_generated / total_problems
        
        just_log(f"Overall Dataset Accuracy: {overall_accuracy:.2f}%", log_file)
        just_log(f"Overall Average Fitness:  {overall_fitness:.4f}", log_file)
        just_log("-" * 50, log_file)
        just_log(f"Average Answer Length:    {average_length:.2f} words", log_file)
        just_log(f"Exactly 1-Word Answers:   {total_1_word} ({(total_1_word/total_problems)*100:.1f}%)", log_file)
        just_log(f"Exactly 2-Word Answers:   {total_2_word} ({(total_2_word/total_problems)*100:.1f}%)", log_file)
        just_log("=" * 50, log_file)
        just_log("\n" * 3, log_file)

if __name__ == "__main__":
    try:
        asyncio.run(run_few_shots())
    finally:
        force_cleanup()