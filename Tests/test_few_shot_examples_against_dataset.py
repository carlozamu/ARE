import re
import numpy as np
import pandas as pd
from datasets import load_dataset
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from rapidfuzz.distance import Levenshtein

# ==========================================
# 1. GLOBAL VARIABLES & EXAMPLES
# ==========================================

# The three few-shot examples from your prompt
EXAMPLE_1 = "Seth] and his grandmother [Mary] went to the science museum. They both had fun, and learned some things, too. [Arthur] enjoys going fishing with his brother. His name is [Warren]. [Seth] and his brother [Warren] always played pranks on each other [Warren] was disappointed that his father, [Alvin], would n't be at the play to see him perform. [Warren] took his son [Alvin] out to play gold later that night. [Warren] played chess with his brother [Arthur]."
EXAMPLE_2 = "[Ross] went to his brother [Michael]'s Birthday party [Ronald]'s aunt [Erica] likes to drink a little bit too much wine at family gatherings. [Patrick] asked his brother [Ross] if he would come help him fix his car next weekend. [Erica] was mad at her son, [Michael]. She found he'd been stealing from her purse. [Robert] would n't let his son [James] go to the park by himself. [James]'s brother [Ronald] offered to go with him."
EXAMPLE_3 = "[Patrick]'s father, [Joseph], went bowling with his sister, [Katherine]. [Katherine] and her son [Ronald] went out to lunch together yesterday. [Alfredo] went to the Farmer's market with his mother [Erica] and his brother [Patrick]. [Ronald] went to the game with his sister [Charlsie]."
# Kinship terms to mask (including plurals and synonyms)
KINSHIP_TERMS = [
    "aunt", "son-in-law", "grandfather", "brother", "sister",
    "father", "mother", "grandmother", "uncle", "daughter-in-law",
    "grandson", "granddaughter", "father-in-law", "mother-in-law",
    "nephew", "son", "daughter", "niece", "grandma", "grandpa", 
    "mom", "dad", "sis", "bro", "husband", "wife"
]

# Pronouns to mask
PRONOUNS = ["he", "she", "him", "her", "his", "hers", "they", "them", "their"]

# Thresholds defined in our methodology
TFIDF_THRESHOLD = 0.80
LEV_THRESHOLD = 0.85

# ==========================================
# 2. DATA NORMALIZATION (ABSTRACTIVE MASKING)
# ==========================================

def mask_structure(text: str) -> str:
    """
    Strips semantics (entities, pronouns, kinship) to isolate syntactic structure.
    """
    if not text:
        return ""
    
    text = text.lower()
    
    # 1. Mask Bracketed Entities (e.g., [Ashley] -> <ENT>)
    text = re.sub(r'\[.*?\]', '<ENT>', text)
    
    # 2. Mask Pronouns (using word boundaries \b to avoid replacing parts of words)
    pronoun_pattern = r'\b(' + '|'.join(PRONOUNS) + r')\b'
    text = re.sub(pronoun_pattern, '<PRON>', text)
    
    # 3. Mask Kinship Terms
    kin_pattern = r'\b(' + '|'.join(KINSHIP_TERMS) + r')s?\b' # Added s? to catch plurals
    text = re.sub(kin_pattern, '<KIN>', text)
    
    # Clean up excess whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ==========================================
# 3. CORE PROCESSING LOGIC
# ==========================================

def compute_similarities():
    print("Loading CLUTRR dataset...")
    # Load dataset exactly as in your main script
    dataset = load_dataset("CLUTRR/v1", "gen_train234_test2to10", trust_remote_code=True)
    
    # Pre-mask the global examples
    masked_examples = [mask_structure(ex) for ex in [EXAMPLE_1, EXAMPLE_2, EXAMPLE_3]]
    
    print("\nMasked Examples Representation:")
    for i, ex in enumerate(masked_examples):
        print(f"Ex {i+1}: {ex}")

    # Extract all data into a list of dictionaries for easier Pandas conversion
    records = []
    
    print("\nParsing dataset and applying masking...")
    for split_name in dataset.keys():
        for item in dataset[split_name]:
            target = item.get("target_text", "")
            task_name = item.get("task_name", "")
            story = item.get("story", "")
            
            if not target or not story:
                continue
                
            # Extract reasoning length
            match = re.search(r"task_(\d+)\.(\d+)", task_name)
            if match:
                k_hops = int(match.group(2))
            else:
                continue # Skip malformed
                
            masked_story = mask_structure(story)
            
            records.append({
                "id": item.get("id", "unknown"),
                "split": split_name,
                "k_hops": k_hops,
                "original_story": story,
                "masked_story": masked_story
            })

    # ==========================================
    # --- DEBUG INJECTION START ---
    # ==========================================
    print("\n--- DEBUG: First 3 Processed Dataset Stories ---")
    for i in range(min(3, len(records))):
        print(f"Problem ID: {records[i]['id']} (k={records[i]['k_hops']})")
        print(f"Original: {records[i]['original_story']}")
        print(f"Masked:   {records[i]['masked_story']}\n")
    print("------------------------------------------------\n")
    # ==========================================
    # --- DEBUG INJECTION END ---
    # ==========================================

    df = pd.DataFrame(records)
    print(f"Successfully processed {len(df)} valid problems.")

    # --- TF-IDF & Cosine Similarity Calculation ---
    print("Computing TF-IDF (3-gram) Similarities...")
    # We use (2,3) n-grams to capture multi-word structural components
    vectorizer = TfidfVectorizer(ngram_range=(2, 3))
    
    # Fit on BOTH the dataset and the examples to ensure consistent vocabulary space
    all_texts = df['masked_story'].tolist() + masked_examples
    tfidf_matrix = vectorizer.fit_transform(all_texts)
    
    # Split the matrix back into dataset vs examples
    dataset_tfidf = tfidf_matrix[:-3]
    examples_tfidf = tfidf_matrix[-3:]
    
    # Vectorized cosine similarity (Matrix Multiplication)
    cosine_sims = cosine_similarity(dataset_tfidf, examples_tfidf)
    
    df['tfidf_ex1'] = cosine_sims[:, 0]
    df['tfidf_ex2'] = cosine_sims[:, 1]
    df['tfidf_ex3'] = cosine_sims[:, 2]
    df['tfidf_max_pool'] = df[['tfidf_ex1', 'tfidf_ex2', 'tfidf_ex3']].max(axis=1)

    # --- Normalized Levenshtein Calculation ---
    print("Computing Normalized Levenshtein Similarities...")
    # This loop uses rapidfuzz which is implemented in C++ and highly optimized
    lev_ex1, lev_ex2, lev_ex3 = [], [], []
    
    for story in df['masked_story']:
        lev_ex1.append(Levenshtein.normalized_similarity(story, masked_examples[0]))
        lev_ex2.append(Levenshtein.normalized_similarity(story, masked_examples[1]))
        lev_ex3.append(Levenshtein.normalized_similarity(story, masked_examples[2]))

    df['lev_ex1'] = lev_ex1
    df['lev_ex2'] = lev_ex2
    df['lev_ex3'] = lev_ex3
    df['lev_max_pool'] = df[['lev_ex1', 'lev_ex2', 'lev_ex3']].max(axis=1)

    return df

# ==========================================
# 4. REPORT GENERATION
# ==========================================

def generate_reports(df: pd.DataFrame):
    print("Generating statistical tables...")
    
    def calculate_stats(metric_prefix, threshold):
        # Group by reasoning hops (k)
        stats = df.groupby('k_hops').agg(
            Total_Problems=('id', 'count'),
            Max_Mean=(f'{metric_prefix}_max_pool', 'mean'),
            Max_Median=(f'{metric_prefix}_max_pool', 'median'),
            Ex1_Mean=(f'{metric_prefix}_ex1', 'mean'),
            Ex2_Mean=(f'{metric_prefix}_ex2', 'mean'),
            Ex3_Mean=(f'{metric_prefix}_ex3', 'mean')
        ).round(3)
        
        # Calculate Threshold Counts
        stats['Max_Count_>_Thr'] = df[df[f'{metric_prefix}_max_pool'] > threshold].groupby('k_hops').size().fillna(0).astype(int)
        
        # Add a TOTAL row at the bottom
        total_row = pd.DataFrame({
            'Total_Problems': [len(df)],
            'Max_Mean': [df[f'{metric_prefix}_max_pool'].mean()],
            'Max_Median': [df[f'{metric_prefix}_max_pool'].median()],
            'Ex1_Mean': [df[f'{metric_prefix}_ex1'].mean()],
            'Ex2_Mean': [df[f'{metric_prefix}_ex2'].mean()],
            'Ex3_Mean': [df[f'{metric_prefix}_ex3'].mean()],
            'Max_Count_>_Thr': [(df[f'{metric_prefix}_max_pool'] > threshold).sum()]
        }, index=['TOTAL']).round(3)
        
        stats = pd.concat([stats, total_row])
        
        # Reorder columns to match our agreed upon schema
        return stats[['Total_Problems', 'Max_Mean', 'Max_Median', 'Max_Count_>_Thr', 'Ex1_Mean', 'Ex2_Mean', 'Ex3_Mean']]

    tfidf_stats = calculate_stats('tfidf', TFIDF_THRESHOLD)
    lev_stats = calculate_stats('lev', LEV_THRESHOLD)

    # Save to Markdown file
    with open('similarities.md', 'w') as f:
        f.write("# CLUTRR Few-Shot Syntactic Similarity Report\n\n")
        f.write("## 1. TF-IDF Cosine Similarity (Structure Vectorization)\n")
        f.write(f"*Threshold for Match: > {TFIDF_THRESHOLD}*\n\n")
        f.write(tfidf_stats.to_markdown())
        f.write("\n\n---\n\n")
        f.write("## 2. Normalized Levenshtein Similarity (Edit Distance)\n")
        f.write(f"*Threshold for Match: > {LEV_THRESHOLD}*\n\n")
        f.write(lev_stats.to_markdown())

    # Save raw data to CSV for manual validation later
    df.to_csv('similarities_raw_data.csv', index=False)
    
    print("\n[SUCCESS] Reports generated:")
    print(" 1. similarities.md (Formatted Tables)")
    print(" 2. similarities_raw_data.csv (Raw Dataset for Inspection)")

if __name__ == "__main__":
    df_results = compute_similarities()
    generate_reports(df_results)
    