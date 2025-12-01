#!/bin/bash
# =============================================================================
# SIMPLE MAC-SQL EVALUATION SCRIPT
# =============================================================================
# This script does everything for you step by step.
#
# BEFORE RUNNING THIS SCRIPT:
# 1. Download data.zip from: https://drive.google.com/file/d/1kkkNJSmJkZKeZyDFUDG7c4mnkxsrr-om/view
# 2. Unzip it and replace the 'data' folder in MAC-SQL directory
# 3. Set your OpenAI API key: export OPENAI_API_KEY="sk-your-key-here"
#
# USAGE:
#   ./simple_run.sh bird    # Run BIRD evaluation only
#   ./simple_run.sh spider  # Run Spider evaluation only  
#   ./simple_run.sh both    # Run both evaluations
#   ./simple_run.sh eval    # Only run evaluation (skip prediction - if you already have predictions)
#
# =============================================================================

set -e

# What to run
MODE="${1:-bird}"

echo ""
echo "============================================================"
echo "MAC-SQL SIMPLE EVALUATION RUNNER"
echo "============================================================"
echo "Mode: $MODE"
echo ""

# Check if API key is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ ERROR: OPENAI_API_KEY is not set!"
    echo ""
    echo "Please run this command first:"
    echo "  export OPENAI_API_KEY=\"sk-your-api-key-here\""
    echo ""
    echo "Get your API key from: https://platform.openai.com/api-keys"
    exit 1
fi

# Check if data exists
if [ ! -f "./data/bird/dev.json" ]; then
    echo "❌ ERROR: BIRD data not found!"
    echo ""
    echo "Please download data.zip from:"
    echo "  https://drive.google.com/file/d/1kkkNJSmJkZKeZyDFUDG7c4mnkxsrr-om/view"
    echo ""
    echo "Then unzip it in the MAC-SQL folder."
    exit 1
fi

echo "✅ API key is set"
echo "✅ Data folder found"
echo ""

# =============================================================================
# BIRD EVALUATION
# =============================================================================
if [ "$MODE" = "bird" ] || [ "$MODE" = "both" ]; then
    echo "============================================================"
    echo "STEP 1: Preparing BIRD subset..."
    echo "============================================================"
    
    python prepare_bird_subset.py \
        --databases california_schools card_games codebase_community
    
    echo ""
    echo "============================================================"
    echo "STEP 2: Generating predictions with GPT-4..."
    echo "(This will cost ~$5-10 and take 10-30 minutes)"
    echo "============================================================"
    
    mkdir -p outputs/bird
    
    python run.py \
        --dataset_name bird \
        --input_file ./data/bird/dev_subset_8.json \
        --db_path ./data/bird/dev_databases/ \
        --tables_json_path ./data/bird/dev_tables.json \
        --output_file ./outputs/bird/output.jsonl
    
    echo ""
    echo "============================================================"
    echo "STEP 3: Running EX (Accuracy) Evaluation..."
    echo "============================================================"
    
    python ./evaluation/evaluation_bird_ex.py \
        --db_root_path ./data/bird/dev_databases/ \
        --predicted_sql_json_path ./outputs/bird/predict_dev.json \
        --data_mode dev \
        --ground_truth_sql_path ./data/bird/dev_gold_subset_8.sql \
        --num_cpus 4 \
        --mode_predict gpt \
        --diff_json_path ./data/bird/dev_subset_8.json \
        --meta_time_out 30.0
    
    echo ""
    echo "============================================================"
    echo "STEP 4: Running VES (Efficiency) Evaluation..."
    echo "(This takes longer - be patient)"
    echo "============================================================"
    
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
    
    echo ""
    echo "============================================================"
    echo "STEP 5: Running Error Analysis..."
    echo "============================================================"
    
    python ./evaluation/error_analysis.py \
        --eval_result_path ./outputs/bird/eval_result_dev.json \
        --db_root_path ./data/bird/dev_databases/ \
        --output_path ./outputs/bird/bird_error_analysis.json \
        --dataset_name bird \
        --sample_size 100 \
        --generate_chart
    
    echo ""
    echo "✅ BIRD EVALUATION COMPLETE!"
    echo ""
    echo "Output files in ./outputs/bird/:"
    echo "  - eval_result_dev.json    (detailed results)"
    echo "  - ves_result_dev.json     (efficiency scores)"
    echo "  - bird_error_analysis.json (error categories)"
    echo "  - bird_error_analysis_chart.png (pie chart)"
fi

# =============================================================================
# SPIDER EVALUATION
# =============================================================================
if [ "$MODE" = "spider" ] || [ "$MODE" = "both" ]; then
    echo ""
    echo "============================================================"
    echo "SPIDER EVALUATION"
    echo "============================================================"
    echo ""
    echo "STEP 1: Generating predictions with GPT-4..."
    echo "(This will cost ~$30-60 and take 30-60 minutes)"
    echo "============================================================"
    
    mkdir -p outputs/spider
    
    python run.py \
        --dataset_name spider \
        --input_file ./data/spider/dev.json \
        --db_path ./data/spider/database/ \
        --tables_json_path ./data/spider/tables.json \
        --output_file ./outputs/spider/output.jsonl
    
    echo ""
    echo "============================================================"
    echo "STEP 2: Running Evaluation..."
    echo "============================================================"
    
    python ./evaluation/evaluation_spider_ex.py \
        --gold ./data/spider/dev_gold.sql \
        --pred ./outputs/spider/pred_dev.sql \
        --db ./data/spider/database/ \
        --table ./data/spider/tables.json \
        --dev_json ./data/spider/dev.json \
        --output_dir ./outputs/spider/ \
        --num_cpus 4 \
        --meta_time_out 30.0
    
    echo ""
    echo "============================================================"
    echo "STEP 3: Running Error Analysis..."
    echo "============================================================"
    
    python ./evaluation/error_analysis.py \
        --eval_result_path ./outputs/spider/eval_result_dev.json \
        --db_root_path ./data/spider/database/ \
        --output_path ./outputs/spider/spider_error_analysis.json \
        --dataset_name spider \
        --sample_size 100 \
        --generate_chart
    
    echo ""
    echo "✅ SPIDER EVALUATION COMPLETE!"
    echo ""
    echo "Output files in ./outputs/spider/:"
    echo "  - eval_result_dev.json    (detailed results)"
    echo "  - spider_error_analysis.json (error categories)"
    echo "  - spider_error_analysis_chart.png (pie chart)"
fi

# =============================================================================
# GENERATE COMPARISON CHARTS (if both were run)
# =============================================================================
if [ "$MODE" = "both" ]; then
    echo ""
    echo "============================================================"
    echo "Generating Comparison Charts..."
    echo "============================================================"
    
    mkdir -p outputs/charts
    
    python ./evaluation/generate_error_charts.py \
        --bird_analysis ./outputs/bird/bird_error_analysis.json \
        --spider_analysis ./outputs/spider/spider_error_analysis.json \
        --output_dir ./outputs/charts/ \
        --create_comparison
    
    echo ""
    echo "✅ COMPARISON CHARTS GENERATED!"
    echo ""
    echo "Charts saved in ./outputs/charts/:"
    echo "  - bird_error_distribution.png"
    echo "  - spider_error_distribution.png"
    echo "  - error_distribution_comparison.png (side-by-side)"
    echo "  - error_distribution_summary.txt"
fi

echo ""
echo "============================================================"
echo "ALL DONE! 🎉"
echo "============================================================"
echo ""
echo "Check the 'outputs' folder for all results."
echo ""