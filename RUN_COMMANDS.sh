#!/bin/bash
# =============================================================================
# MAC-SQL COMPLETE EVALUATION GUIDE
# =============================================================================
# Model: GPT-4.1-nano (Very cheap: ~$0.10/1M input, $0.40/1M output)
# Estimated cost for 400 questions: $0.50 - $2.00
#
# STEPS THAT COST MONEY:
#   ✅ Step 2 (Generate BIRD predictions) - Uses API
#   ✅ Step 5 (Generate Spider predictions) - Uses API
#
# STEPS THAT ARE FREE:
#   ❌ Step 1 (Prepare subset) - Local only
#   ❌ Step 3 (BIRD Evaluation) - Local only
#   ❌ Step 4 (BIRD Error Analysis) - Local only
#   ❌ Step 6 (Spider Evaluation) - Local only
#   ❌ Step 7 (Spider Error Analysis) - Local only
#   ❌ Step 8 (Generate Charts) - Local only
# =============================================================================

# First, activate your virtual environment and set API key
# Run these commands in your terminal:

# cd /path/to/MAC-SQL
# source venv/bin/activate
# export OPENAI_API_KEY="sk-your-key-here"

# =============================================================================
# STEP 1: PREPARE BIRD SUBSET (~400 questions) - FREE
# =============================================================================
# This creates a subset with about 400 questions from BIRD

python prepare_bird_subset.py --list  # First, see available databases

# Then create subset with these databases (adjust to get ~400 questions):
python prepare_bird_subset.py \
    --databases california_schools financial card_games codebase_community thrombosis_prediction

# This creates:
# - data/bird/dev_subset_8.json (questions)
# - data/bird/dev_gold_subset_8.sql (gold answers)

# =============================================================================
# STEP 2: GENERATE BIRD PREDICTIONS - COSTS ~$0.50-1.00
# =============================================================================
# This calls GPT-4.1-nano API to generate SQL predictions

mkdir -p outputs/bird

python run.py \
    --dataset_name bird \
    --input_file ./data/bird/dev_subset_8.json \
    --db_path ./data/bird/dev_databases/ \
    --tables_json_path ./data/bird/dev_tables.json \
    --output_file ./outputs/bird/output_dev.jsonl \
    --log_file ./outputs/bird/log.txt

# This creates:
# - outputs/bird/output_dev.jsonl (raw predictions)
# - outputs/bird/predict_dev.json (formatted for evaluation)

# =============================================================================
# STEP 3: RUN BIRD EVALUATION (EX + VES) - FREE
# =============================================================================

# 3a. EX (Execution Accuracy) Evaluation
python ./evaluation/evaluation_bird_ex.py \
    --db_root_path ./data/bird/dev_databases/ \
    --predicted_sql_json_path ./outputs/bird/predict_dev.json \
    --data_mode dev \
    --ground_truth_sql_path ./data/bird/dev_gold_subset_8.sql \
    --num_cpus 4 \
    --mode_predict gpt \
    --diff_json_path ./data/bird/dev_subset_8.json \
    --meta_time_out 30.0

# Creates: outputs/bird/eval_result_dev.json

# 3b. VES (Efficiency) Evaluation - Takes longer, be patient
python ./evaluation/evaluation_bird_ves.py \
    --db_root_path ./data/bird/dev_databases/ \
    --predicted_sql_json_path ./outputs/bird/predict_dev.json \
    --data_mode dev \
    --ground_truth_sql_path ./data/bird/dev_gold_subset_8.sql \
    --num_cpus 4 \
    --meta_time_out 60 \
    --mode_gt gt \
    --mode_predict gpt \
    --diff_json_path ./data/bird/dev_subset_8.json

# Creates: outputs/bird/ves_result_dev.json

# =============================================================================
# STEP 4: RUN BIRD ERROR ANALYSIS - FREE
# =============================================================================

python ./evaluation/error_analysis.py \
    --eval_result_path ./outputs/bird/eval_result_dev.json \
    --db_root_path ./data/bird/dev_databases/ \
    --output_path ./outputs/bird/error_analysis.json \
    --dataset_name bird \
    --sample_size 100 \
    --generate_chart

# Creates:
# - outputs/bird/error_analysis.json
# - outputs/bird/error_analysis_chart.png (PIE CHART!)

# =============================================================================
# STEP 5: GENERATE SPIDER PREDICTIONS - COSTS ~$0.50-1.00
# =============================================================================

# First, create Spider subset (~400 questions)
python prepare_spider_subset.py

mkdir -p outputs/spider

python run.py \
    --dataset_name spider \
    --input_file ./data/spider/dev_subset.json \
    --db_path ./data/spider/database/ \
    --tables_json_path ./data/spider/tables.json \
    --output_file ./outputs/spider/output_dev.jsonl \
    --log_file ./outputs/spider/log.txt

# =============================================================================
# STEP 6: RUN SPIDER EVALUATION - FREE
# =============================================================================

python ./evaluation/evaluation_spider_ex.py \
    --gold ./data/spider/dev_gold_subset.sql \
    --pred ./outputs/spider/pred_dev.sql \
    --db ./data/spider/database/ \
    --table ./data/spider/tables.json \
    --dev_json ./data/spider/dev_subset.json \
    --output_dir ./outputs/spider/ \
    --num_cpus 4 \
    --meta_time_out 30.0

# Creates: outputs/spider/eval_result_dev.json

# =============================================================================
# STEP 7: RUN SPIDER ERROR ANALYSIS - FREE
# =============================================================================

python ./evaluation/error_analysis.py \
    --eval_result_path ./outputs/spider/eval_result_dev.json \
    --db_root_path ./data/spider/database/ \
    --output_path ./outputs/spider/error_analysis.json \
    --dataset_name spider \
    --sample_size 100 \
    --generate_chart

# Creates:
# - outputs/spider/error_analysis.json
# - outputs/spider/error_analysis_chart.png (PIE CHART!)

# =============================================================================
# STEP 8: GENERATE COMPARISON CHARTS - FREE
# =============================================================================

mkdir -p outputs/charts

python ./evaluation/generate_error_charts.py \
    --bird_analysis ./outputs/bird/error_analysis.json \
    --spider_analysis ./outputs/spider/error_analysis.json \
    --output_dir ./outputs/charts/ \
    --create_comparison

# Creates:
# - outputs/charts/bird_error_distribution.png
# - outputs/charts/spider_error_distribution.png
# - outputs/charts/error_distribution_comparison.png (SIDE BY SIDE!)
# - outputs/charts/error_distribution_summary.txt

# =============================================================================
# DONE! Check outputs folder for all results
# =============================================================================