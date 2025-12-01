# MAC-SQL Evaluation Report

## 1. Introduction

This report presents the evaluation of the MAC-SQL (Multi-Agent Collaborative Framework for Text-to-SQL) on two benchmark datasets: **BIRD** and **Spider**. The evaluation follows the methodology described in the MAC-SQL paper, using two primary metrics:

- **EX (Execution Accuracy)**: The proportion of questions where the predicted SQL returns identical results to the ground-truth SQL
- **VES (Valid Efficiency Score)**: Measures the efficiency of valid SQLs by comparing execution times (BIRD only)

Additionally, we perform **error analysis** to categorize prediction failures into 8 distinct error types.

---

## 2. Evaluation Metrics

### 2.1 Execution Accuracy (EX)

Execution Accuracy measures the correctness of generated SQL queries by comparing their execution results against ground truth queries.

**Formula:**
```
EX = (Number of queries with matching results) / (Total number of queries) × 100%
```

A prediction is considered correct if `set(pred_results) == set(gold_results)`, which allows for different row orderings.

### 2.2 Valid Efficiency Score (VES)

VES measures not just correctness but also efficiency of the generated SQL queries. It only applies to "valid" SQLs (those that return correct results).

**Formula:**
```
VES = (1/N) × Σ sqrt(gold_time / pred_time) × 100
```

Where:
- N = total number of queries
- gold_time = execution time of ground truth SQL
- pred_time = execution time of predicted SQL
- Only valid (correct) SQLs contribute non-zero values

A VES > 100 indicates the predicted SQL is more efficient than ground truth.

### 2.3 Difficulty Levels

**BIRD Dataset:**
- Simple
- Moderate  
- Challenging

**Spider Dataset:**
- Easy
- Medium
- Hard
- Extra

---

## 3. Experimental Setup

### 3.1 Datasets

| Dataset | Train | Dev | Test | Databases | Domains |
|---------|-------|-----|------|-----------|---------|
| BIRD | 9,428 | 1,534 | 1,534 | 95 | 37 |
| Spider | 7,000 | 1,034 | - | 200 | 138 |

### 3.2 Evaluation Subsets (BIRD)

For comprehensive evaluation, we created 10 subsets from the BIRD development set:

| Subset | Databases | Description |
|--------|-----------|-------------|
| subset_1 | california_schools, financial | Financial & Schools |
| subset_2 | card_games, codebase_community | Gaming & Community |
| subset_3 | thrombosis_prediction, european_football_2 | Healthcare & Sports |
| subset_4 | formula_1, superhero | Racing & Entertainment |
| subset_5 | debit_card_specializing, student_club | Financial & Student |
| subset_6 | toxicology, retail_world | Scientific & Retail |
| subset_7 | california_schools | Single Database |
| subset_8 | california_schools, card_games, codebase_community | Mixed Small |
| subset_9 | financial, european_football_2, formula_1, thrombosis_prediction | Large Mixed |
| subset_10 | All (sampled) | Full Dev Sample |

### 3.3 Model Configuration

- **Base Model**: GPT-4 (gpt-4-1106-preview)
- **Framework**: MAC-SQL with Selector, Decomposer, and Refiner agents
- **Few-shot Examples**: 3-shot prompting

---

## 4. Results

### 4.1 BIRD Dataset Results

#### Execution Accuracy (EX) by Difficulty

| Difficulty | Count | Accuracy (%) |
|------------|-------|--------------|
| Simple | - | - |
| Moderate | - | - |
| Challenging | - | - |
| **Total** | - | **-** |

*Note: Fill in actual results after running evaluation*

#### Valid Efficiency Score (VES) by Difficulty

| Difficulty | Count | VES |
|------------|-------|-----|
| Simple | - | - |
| Moderate | - | - |
| Challenging | - | - |
| **Total** | - | **-** |

### 4.2 Spider Dataset Results

#### Execution Accuracy (EX) by Difficulty

| Difficulty | Count | Accuracy (%) |
|------------|-------|--------------|
| Easy | - | - |
| Medium | - | - |
| Hard | - | - |
| Extra | - | - |
| **Total** | - | **-** |

### 4.3 Comparison with Baselines

| Method | BIRD Dev EX | BIRD Dev VES | Spider Dev EX |
|--------|-------------|--------------|---------------|
| GPT-4 (zero-shot) | 46.35 | 49.77 | - |
| DIN-SQL+GPT-4 | 50.72 | 58.79 | 82.80 |
| DAIL-SQL+GPT-4 | 54.76 | 56.08 | 84.40 |
| **MAC-SQL+GPT-4** | **59.39** | **66.39** | **86.75** |

*Source: MAC-SQL Paper Table 1 & 2*

---

## 5. Error Analysis

### 5.1 Error Categories

Based on the MAC-SQL paper, we categorize errors into 8 types:

1. **Gold Error** (30% BIRD, 22% Spider)
   - Ground truth SQL is incorrectly labeled
   - Mismatch between question/evidence and gold SQL

2. **Database Misunderstand** (10% BIRD, 10% Spider)
   - Misunderstanding of database structure or cell values
   - Wrong foreign key relationships

3. **Semantic Correct** (14% BIRD, 22% Spider)
   - Predicted SQL answers the question correctly
   - Different column order or additional columns returned

4. **Question Misunderstand** (26% BIRD, 18% Spider)
   - Model misinterprets the logic of the question
   - Example: interpreting "and" as "or"

5. **Evidence Misunderstand** (8% BIRD, 4% Spider)
   - Predicted SQL doesn't use or misuses the provided evidence
   - BIRD-specific due to evidence annotations

6. **Dirty Database Values** (8% BIRD, 8% Spider)
   - Database values contain noise or inconsistencies
   - Special characters, encoding issues

7. **Schema Linking Error** (2% BIRD, 8% Spider)
   - Wrong table or column selection
   - Incorrect joins

8. **Other** (2% BIRD, 8% Spider)
   - Uncategorizable errors

### 5.2 Error Distribution Charts

[Include pie charts generated by generate_error_charts.py]

**BIRD Error Distribution:**
- Gold Error: 30%
- Question Misunderstand: 26%
- Semantic Correct: 14%
- Database Misunderstand: 10%
- Evidence Misunderstand: 8%
- Dirty Database Values: 8%
- Schema Linking Error: 2%
- Other: 2%

**Spider Error Distribution:**
- Gold Error: 22%
- Semantic Correct: 22%
- Question Misunderstand: 18%
- Database Misunderstand: 10%
- Schema Linking Error: 8%
- Dirty Database Values: 8%
- Other: 8%
- Evidence Misunderstand: 4%

### 5.3 Key Observations

1. **Gold Errors are significant**: 30% of BIRD and 22% of Spider errors are due to incorrect ground truth annotations.

2. **Semantic Correct shows evaluation limitations**: 14-22% of "errors" are actually correct answers with different formatting.

3. **Question understanding is challenging**: 18-26% of errors stem from misinterpreting user intent.

4. **Schema linking is better on BIRD**: Only 2% vs 8% on Spider, possibly due to BIRD's evidence annotations.

5. **Evidence utilization needs improvement**: 8% of BIRD errors relate to evidence misuse.

---

## 6. Ablation Study

Impact of individual MAC-SQL components (from paper):

| Method | Simple | Moderate | Challenging | All |
|--------|--------|----------|-------------|-----|
| MAC-SQL | 65.73 | 52.69 | 40.28 | **59.39** |
| w/o Selector | 65.73 | 52.04 | 35.14 | 57.28 (↓2.11) |
| w/o Decomposer | 61.51 | 48.82 | 38.89 | 55.54 (↓3.85) |
| w/o Refiner | 63.24 | 44.52 | 33.33 | 54.76 (↓4.63) |

**Key Findings:**
- **Refiner** has the largest impact (-4.63%)
- **Decomposer** significantly helps with complex queries (-3.85%)
- **Selector** is crucial for challenging queries (-5.14% on challenging)

---

## 7. How to Reproduce Results

### 7.1 Prerequisites

```bash
# Create environment
conda create -n macsql python=3.9 -y
conda activate macsql
pip install -r requirements.txt
pip install func_timeout matplotlib numpy

# Set API keys
export OPENAI_API_BASE="YOUR_API_BASE"
export OPENAI_API_KEY="YOUR_API_KEY"
```

### 7.2 Prepare Data

```bash
# Download data.zip and extract to ./data/
# For BIRD subsets:
python prepare_bird_subsets.py --input_dev_json ./data/bird/dev.json \
                               --output_dir ./data/bird/subsets/

# For single subset (legacy):
python prepare_bird_subset.py --databases california_schools card_games codebase_community
```

### 7.3 Generate Predictions

```bash
# BIRD
python run.py --dataset_name bird \
              --input_file ./data/bird/dev_subset_8.json \
              --db_path ./data/bird/dev_databases/ \
              --tables_json_path ./data/bird/dev_tables.json \
              --output_file ./outputs/bird_subset_8/output_dev.jsonl

# Spider
python run.py --dataset_name spider \
              --input_file ./data/spider/dev.json \
              --db_path ./data/spider/database/ \
              --tables_json_path ./data/spider/tables.json \
              --output_file ./outputs/spider/output_dev.jsonl
```

### 7.4 Run Evaluation

```bash
# BIRD (with EX, VES, and error analysis)
./evaluate_bird_subset.sh subset_8 --error-analysis

# Spider (with error analysis)
./evaluate_spider.sh --error-analysis

# Or use the comprehensive runner for all subsets
./run_comprehensive_evaluation.sh
```

### 7.5 Generate Visualizations

```bash
python ./evaluation/generate_error_charts.py \
    --bird_analysis ./outputs/bird_subset_8/error_analysis.json \
    --spider_analysis ./outputs/spider/error_analysis.json \
    --output_dir ./outputs/charts/ \
    --create_comparison
```

---

## 8. Output Files

After evaluation, you will find:

| File | Description |
|------|-------------|
| `eval_result_dev.json` | Per-query results with predictions and correctness |
| `ves_result_dev.json` | VES scores by difficulty (BIRD only) |
| `evaluation_report.json` | Summary statistics |
| `error_analysis.json` | Error categorization results |
| `error_analysis_chart.png` | Pie chart visualization |

---

## 9. Conclusion

The MAC-SQL framework achieves state-of-the-art results on both BIRD and Spider benchmarks:

- **BIRD Test Set**: 59.59% EX, 67.68% VES
- **Spider Dev Set**: 86.75% EX

The multi-agent collaboration approach (Selector + Decomposer + Refiner) demonstrates significant improvements over single-pass methods, with each component contributing meaningfully to the overall performance.

Error analysis reveals that:
1. A significant portion of "errors" are actually due to gold annotation issues or semantic equivalence
2. Question understanding remains the primary challenge
3. The framework excels at schema linking, particularly with evidence annotations

---

## 10. References

1. Wang, B., Ren, C., Yang, J., et al. (2023). MAC-SQL: A Multi-Agent Collaborative Framework for Text-to-SQL. arXiv:2312.11242

2. Li, J., Hui, B., Qu, G., et al. (2023). Can LLM Already Serve as A Database Interface? A BIG Bench for Large-scale Database Grounded Text-to-SQLs.

3. Yu, T., Zhang, R., Yang, K., et al. (2018). Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task.

---

*Report generated using MAC-SQL Evaluation Framework*