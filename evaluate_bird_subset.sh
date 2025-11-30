#!/bin/bash
# =============================================================================
# BIRD Subset Evaluation Script
# =============================================================================
# Evaluates MAC-SQL on BIRD dataset subsets with EX and VES metrics.
# 
# Usage:
#   ./evaluate_bird_subset.sh                    # Use default subset_8
#   ./evaluate_bird_subset.sh subset_1           # Evaluate subset_1
#   ./evaluate_bird_subset.sh subset_8 --no-ves  # Skip VES evaluation
#   ./evaluate_bird_subset.sh subset_8 --error-analysis  # Include error analysis
#
# Metrics:
#   - EX (Execution Accuracy): Proportion of correct SQL execution results
#   - VES (Valid Efficiency Score): Measures efficiency of valid SQLs
#
# =============================================================================

set -e

# Default subset
SUBSET_ID="${1:-subset_8}"
RUN_VES=true
RUN_ERROR_ANALYSIS=false

# Parse additional arguments
for arg in "${@:2}"; do
    case $arg in
        --no-ves)
            RUN_VES=false
            ;;
        --error-analysis)
            RUN_ERROR_ANALYSIS=true
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: ./evaluate_bird_subset.sh [subset_id] [--no-ves] [--error-analysis]"
            exit 1
            ;;
    esac
done

# =============================================================================
# Configuration
# =============================================================================

# 1. Database Path
db_root_path="./data/bird/dev_databases/"

# 2. Paths based on subset ID
if [[ "$SUBSET_ID" == "subset_8" ]]; then
    # Legacy path support for subset_8
    diff_json_path="./data/bird/dev_subset_8.json"
    predicted_sql_json_path="./outputs/bird_subset_8/predict_dev.json"
    ground_truth_sql_path="./data/bird/dev_gold_subset_8.sql"
    output_dir="./outputs/bird_subset_8/"
else
    # New subsets directory structure
    diff_json_path="./data/bird/subsets/dev_${SUBSET_ID}.json"
    predicted_sql_json_path="./outputs/bird_${SUBSET_ID}/predict_dev.json"
    ground_truth_sql_path="./data/bird/subsets/dev_gold_${SUBSET_ID}.sql"
    output_dir="./outputs/bird_${SUBSET_ID}/"
fi

# 3. Settings
data_mode="dev"
num_cpus=4
meta_time_out=30.0
ves_time_out=60
mode_gt="gt"
mode_predict="gpt"

# =============================================================================
# Validation
# =============================================================================

echo "=================================================="
echo "BIRD Subset Evaluation: $SUBSET_ID"
echo "=================================================="
echo ""
echo "Configuration:"
echo "  Subset ID: $SUBSET_ID"
echo "  DB Root Path: $db_root_path"
echo "  Diff JSON Path: $diff_json_path"
echo "  Predicted SQL Path: $predicted_sql_json_path"
echo "  Ground Truth Path: $ground_truth_sql_path"
echo "  Output Directory: $output_dir"
echo "  Run VES: $RUN_VES"
echo "  Run Error Analysis: $RUN_ERROR_ANALYSIS"
echo ""

# Check if required files exist
if [ ! -f "$diff_json_path" ]; then
    echo "ERROR: Diff JSON file not found: $diff_json_path"
    echo "Please run prepare_bird_subsets.py first."
    exit 1
fi

if [ ! -f "$predicted_sql_json_path" ]; then
    echo "ERROR: Predicted SQL file not found: $predicted_sql_json_path"
    echo "Please run MAC-SQL to generate predictions first."
    echo ""
    echo "Example:"
    echo "  python run.py --dataset_name bird \\"
    echo "                --input_file $diff_json_path \\"
    echo "                --db_path $db_root_path \\"
    echo "                --tables_json_path ./data/bird/dev_tables.json \\"
    echo "                --output_file ${output_dir}output_dev.jsonl"
    exit 1
fi

if [ ! -f "$ground_truth_sql_path" ]; then
    echo "ERROR: Ground truth SQL file not found: $ground_truth_sql_path"
    exit 1
fi

# Create output directory if needed
mkdir -p "$output_dir"

# =============================================================================
# EX Evaluation
# =============================================================================

echo "=================================================="
echo "Starting EX (Execution Accuracy) Evaluation..."
echo "=================================================="
python ./evaluation/evaluation_bird_ex.py \
    --db_root_path "$db_root_path" \
    --predicted_sql_json_path "$predicted_sql_json_path" \
    --data_mode "$data_mode" \
    --ground_truth_sql_path "$ground_truth_sql_path" \
    --num_cpus "$num_cpus" \
    --mode_predict "$mode_predict" \
    --diff_json_path "$diff_json_path" \
    --meta_time_out "$meta_time_out"

echo ""
echo "EX evaluation complete. Results saved to: ${output_dir}eval_result_dev.json"

# =============================================================================
# VES Evaluation
# =============================================================================

if [ "$RUN_VES" = true ]; then
    echo ""
    echo "=================================================="
    echo "Starting VES (Valid Efficiency Score) Evaluation..."
    echo "This may take a while..."
    echo "=================================================="
    python ./evaluation/evaluation_bird_ves.py \
        --db_root_path "$db_root_path" \
        --predicted_sql_json_path "$predicted_sql_json_path" \
        --data_mode "$data_mode" \
        --ground_truth_sql_path "$ground_truth_sql_path" \
        --num_cpus "$num_cpus" \
        --meta_time_out "$ves_time_out" \
        --mode_gt "$mode_gt" \
        --mode_predict "$mode_predict" \
        --diff_json_path "$diff_json_path"
    
    echo ""
    echo "VES evaluation complete."
fi

# =============================================================================
# Error Analysis
# =============================================================================

if [ "$RUN_ERROR_ANALYSIS" = true ]; then
    echo ""
    echo "=================================================="
    echo "Running Error Analysis..."
    echo "=================================================="
    
    eval_result_path="${output_dir}eval_result_dev.json"
    error_analysis_path="${output_dir}error_analysis.json"
    
    if [ -f "$eval_result_path" ]; then
        python ./evaluation/error_analysis.py \
            --eval_result_path "$eval_result_path" \
            --db_root_path "$db_root_path" \
            --output_path "$error_analysis_path" \
            --dataset_name bird \
            --sample_size 100 \
            --generate_chart
        
        echo ""
        echo "Error analysis complete. Results saved to: $error_analysis_path"
    else
        echo "ERROR: Evaluation result not found: $eval_result_path"
        echo "Please run EX evaluation first."
    fi
fi

# =============================================================================
# Summary
# =============================================================================

echo ""
echo "=================================================="
echo "Evaluation Complete!"
echo "=================================================="
echo ""
echo "Output files:"
echo "  - ${output_dir}eval_result_dev.json (detailed results)"
if [ "$RUN_ERROR_ANALYSIS" = true ]; then
    echo "  - ${output_dir}error_analysis.json (error categorization)"
    echo "  - ${output_dir}error_analysis_chart.png (pie chart)"
fi
echo ""
echo "To view results:"
echo "  cat ${output_dir}eval_result_dev.json | python -m json.tool | head -50"
echo ""