#!/bin/bash
# =============================================================================
# EVALUATION ONLY SCRIPT (NO API CALLS - FREE!)
# =============================================================================
# Use this if you already have prediction files (output.jsonl) 
# or if you want to test the evaluation pipeline without paying for API.
#
# This script only runs:
# - EX (Accuracy) Evaluation
# - VES (Efficiency) Evaluation (BIRD only)
# - Error Analysis
# - Chart Generation
#
# USAGE:
#   ./evaluate_only.sh bird     # Evaluate BIRD predictions
#   ./evaluate_only.sh spider   # Evaluate Spider predictions
#   ./evaluate_only.sh charts   # Generate comparison charts only
#
# =============================================================================

set -e

MODE="${1:-bird}"

echo ""
echo "============================================================"
echo "MAC-SQL EVALUATION ONLY (No API calls)"
echo "============================================================"
echo "Mode: $MODE"
echo ""

# =============================================================================
# BIRD EVALUATION ONLY
# =============================================================================
if [ "$MODE" = "bird" ]; then
    
    # Check if prediction file exists
    if [ ! -f "./outputs/bird/predict_dev.json" ]; then
        echo "❌ ERROR: Prediction file not found!"
        echo ""
        echo "Expected: ./outputs/bird/predict_dev.json"
        echo ""
        echo "You need to either:"
        echo "1. Run the full pipeline first: ./simple_run.sh bird"
        echo "2. Or copy existing predictions to this location"
        exit 1
    fi
    
    echo "Running BIRD EX Evaluation..."
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
    echo "Running BIRD VES Evaluation..."
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
    echo "Running BIRD Error Analysis..."
    python ./evaluation/error_analysis.py \
        --eval_result_path ./outputs/bird/eval_result_dev.json \
        --db_root_path ./data/bird/dev_databases/ \
        --output_path ./outputs/bird/bird_error_analysis.json \
        --dataset_name bird \
        --sample_size 100 \
        --generate_chart
    
    echo ""
    echo "✅ BIRD Evaluation Complete!"
    echo "Check ./outputs/bird/ for results"
fi

# =============================================================================
# SPIDER EVALUATION ONLY
# =============================================================================
if [ "$MODE" = "spider" ]; then
    
    if [ ! -f "./outputs/spider/pred_dev.sql" ]; then
        echo "❌ ERROR: Prediction file not found!"
        echo ""
        echo "Expected: ./outputs/spider/pred_dev.sql"
        exit 1
    fi
    
    echo "Running Spider Evaluation..."
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
    echo "Running Spider Error Analysis..."
    python ./evaluation/error_analysis.py \
        --eval_result_path ./outputs/spider/eval_result_dev.json \
        --db_root_path ./data/spider/database/ \
        --output_path ./outputs/spider/spider_error_analysis.json \
        --dataset_name spider \
        --sample_size 100 \
        --generate_chart
    
    echo ""
    echo "✅ Spider Evaluation Complete!"
    echo "Check ./outputs/spider/ for results"
fi

# =============================================================================
# CHARTS ONLY
# =============================================================================
if [ "$MODE" = "charts" ]; then
    
    mkdir -p outputs/charts
    
    echo "Generating Comparison Charts..."
    python ./evaluation/generate_error_charts.py \
        --bird_analysis ./outputs/bird/bird_error_analysis.json \
        --spider_analysis ./outputs/spider/spider_error_analysis.json \
        --output_dir ./outputs/charts/ \
        --create_comparison
    
    echo ""
    echo "✅ Charts Generated!"
    echo "Check ./outputs/charts/ for:"
    echo "  - bird_error_distribution.png"
    echo "  - spider_error_distribution.png"  
    echo "  - error_distribution_comparison.png"
fi

echo ""