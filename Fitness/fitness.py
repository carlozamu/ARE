import asyncio
from typing import List, Dict, Tuple
from Genome.agent_genome import Genome
from Utils.LLM import LLM
from Data.clutrr import CLUTTRManager

PERCENTAGE_FAILURE_THRESHOLD = 0.7 

class Fitness:
    def __init__(self, llm: LLM, use_reasoning: bool = False) -> None:
        self.use_reasoning = use_reasoning
        self.llm = llm
        self.best_accuracy = 0.0
        self.avg_accuracy = 0.0
    
    async def _evaluate_single_problem(self, examples_str: str, problem: Dict) -> Tuple[float, int, bool]:
        """Evaluates a single problem using a pre-computed examples string to save CPU."""
        story = problem['metadata']['story']
        query = problem['metadata']['query']
        
        # 1. Build prompt natively using the CLUTTRManager
        prompt = CLUTTRManager.build_prompt_clutrr_few_shots(story, query, examples_str)
        
        # 2. High-speed token approximation (1 token ≈ 4 characters) 
        # Avoids loading a slow CPU tokenizer in the async hot-path
        prompt_tokens = len(prompt) // 4 
        
        try:
            # Low temperature for classification, minimal max_tokens for a single-word output
            generated_ans = await self.llm.generate_text(
                user_prompt=prompt, 
                temperature=0.0,
                max_tokens=5 
            )
            response_tokens = max(1, len(generated_ans) // 4)
        except Exception as e:
            print(f"Error executing LLM: {e}")
            generated_ans = ""
            response_tokens = 0

        token_used = prompt_tokens + response_tokens
        expected = problem['answer']
        
        # 3. Grade Answer
        if problem.get('task_type') == 'cluttr':
            mapped_response = CLUTTRManager.map_to_relation(generated_ans.strip().lower())
            is_correct = (mapped_response == expected)
        else:
            is_correct = (generated_ans.strip().lower() == expected.strip().lower())
            
        # 4. Compute Score
        score = 1.0 if is_correct else 0.0

        return score, token_used, is_correct
    
    async def _evaluate_individual_full(self, individual: Genome, problem_pool: List[Dict]) -> Tuple[List[int], float]:
        """
        Evaluates an individual using throttled Chunked Concurrency.
        """
        try:
            examples_str = individual.get_samples()
        except Exception as e:
            print(f"Failed to generate samples for genome: {e}")
            individual.fitness = 0.01
            return [], 0.0

        total_score = 0.0
        total_correct = 0
        problems_evaluated = 0
        token_usages = []
        failed_count = 0
        
        # DOWN-TUNED: Smaller chunks reduce parallel requests sent to the LLM
        chunk_size = 3 
        
        for i in range(0, len(problem_pool), chunk_size):
            chunk = problem_pool[i : i + chunk_size]
            
            tasks = [self._evaluate_single_problem(examples_str, p) for p in chunk]
            results = await asyncio.gather(*tasks)
            
            for score, tokens, is_correct in results:
                total_score += score
                problems_evaluated += 1
                if tokens > 0:
                    token_usages.append(tokens)
                if is_correct:
                    total_correct += 1
                if score < 0.1:
                    failed_count += 1
            
            if failed_count > len(problem_pool) * PERCENTAGE_FAILURE_THRESHOLD:
                break 
                
            # THERMAL RELIEF: Give the GPU a brief moment to clear VRAM buffers between chunks
            await asyncio.sleep(0.2)
        
        avg_score = (total_score / problems_evaluated) * 100 if problems_evaluated > 0 else 0.0
        accuracy = (total_correct / problems_evaluated) * 100 if problems_evaluated > 0 else 0.0
        avg_tokens = sum(token_usages) / len(token_usages) if token_usages else 0.0
        
        individual.fitness = float(max(0.01, avg_score))
        individual.accuracy = accuracy
        individual.avg_tokens = avg_tokens
    
        return token_usages, accuracy

    async def evaluate_population(self, population: List[Genome], problem_pool: List[Dict]):
        """
        Dispatches individuals through a strict Semaphore to prevent GPU power spikes.
        """
        if not problem_pool:
            raise ValueError("Problem pool cannot be empty.")
        
        tbe_individuals = [ind for ind in population if ind.fitness is None]
        if not tbe_individuals:
            return
            
        print(f"Evaluating population: {len(tbe_individuals)} new genomes on {len(problem_pool)} problems...")

        # STRICT LIMITER: Only allow 3 genomes to be evaluated concurrently.
        # Combined with chunk_size=3, the absolute maximum concurrent requests to the GPU is 9.
        hardware_semaphore = asyncio.Semaphore(30)

        async def _bounded_evaluate(individual):
            async with hardware_semaphore:
                return await self._evaluate_individual_full(individual, problem_pool)

        tasks = [_bounded_evaluate(individual) for individual in tbe_individuals]
        results = await asyncio.gather(*tasks)

        all_token_usages = []
        all_accuracies = []
        for individual_tokens, accuracy in results:
            all_token_usages.extend(individual_tokens)
            if individual_tokens:
                all_accuracies.append(accuracy)
            
        if all_accuracies:
            max_accuracy = max(all_accuracies)
            if max_accuracy > self.best_accuracy:
                self.best_accuracy = max_accuracy
            self.avg_accuracy = sum(all_accuracies) / len(all_accuracies)
