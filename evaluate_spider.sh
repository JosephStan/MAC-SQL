#!/bin/bash
# =============================================================================
# Spider Evaluation Script
# =============================================================================
# Evaluates MAC-SQL on Spider dataset with EX (Execution Accuracy) metric.
# Spider uses difficulty levels: easy, medium, hard, extra
#
# Usage:
#   ./evaluate_spider.sh                    # Run standard evaluation
#   ./evaluate_spider.sh --error-analysis   # Include error analysis
#
# =============================================================================

set -e

RUN_ERROR_ANALYSIS=false

# Parse arguments
for arg in "$@"; do
    case $arg in
        --error-analysis)
            RUN_ERROR_ANALYSIS=true
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: ./evaluate_spider.sh [--error-analysis]"
            exit 1
            ;;
    esac
done

# =============================================================================
# Configuration
# =============================================================================

# Paths
db_root_path="./data/spider/database/"
gold_sql_path="./data/spider/dev_gold.sql"
pred_sql_path="./outputs/spider/pred_dev.sql"
dev_json_path="./data/spider/dev.json"
tables_json_path="./data/spider/tables.json"
output_dir="./outputs/spider/"

# Settings
num_cpus=4
meta_time_out=30.0

# =============================================================================
# Validation
# =============================================================================

echo "=================================================="
echo "Spider Evaluation"
echo "=================================================="
echo ""
echo "Configuration:"
echo "  DB Root Path: $db_root_path"
echo "  Gold SQL Path: $gold_sql_path"
echo "  Predicted SQL Path: $pred_sql_path"
echo "  Dev JSON Path: $dev_json_path"
echo "  Output Directory: $output_dir"
echo "  Run Error Analysis: $RUN_ERROR_ANALYSIS"
echo ""

# Check if required files exist
if [ ! -d "$db_root_path" ]; then
    echo "ERROR: Database directory not found: $db_root_path"
    exit 1
fi

if [ ! -f "$pred_sql_path" ]; then
    echo "ERROR: Predicted SQL file not found: $pred_sql_path"
    echo "Please run MAC-SQL to generate predictions first."
    echo ""
    echo "Example:"
    echo "  python run.py --dataset_name spider \\"
    echo "                --input_file ./data/spider/dev.json \\"
    echo "                --db_path $db_root_path \\"
    echo "                --tables_json_path $tables_json_path \\"
    echo "                --output_file ${output_dir}output_dev.jsonl"
    exit 1
fi

if [ ! -f "$gold_sql_path" ]; then
    echo "ERROR: Gold SQL file not found: $gold_sql_path"
    exit 1
fi

# Create output directory
mkdir -p "$output_dir"

# =============================================================================
# Standard Spider Evaluation (Original Script)
# =============================================================================

echo "=================================================="
echo "Running Spider Evaluation (EX + EM)..."
echo "=================================================="

python ./evaluation/evaluation_spider.py \
    --gold "$gold_sql_path" \
    --pred "$pred_sql_path" \
    --db "$db_root_path" \
    --table "$tables_json_path" \
    --etype all

# =============================================================================
# Custom EX Evaluation with Result Saving
# =============================================================================

echo ""
echo "=================================================="
echo "Running EX Evaluation with detailed results..."
echo "=================================================="

python ./evaluation/evaluation_spider_ex.py \
    --gold "$gold_sql_path" \
    --pred "$pred_sql_path" \
    --db "$db_root_path" \
    --table "$tables_json_path" \
    --dev_json "$dev_json_path" \
    --output_dir "$output_dir" \
    --num_cpus "$num_cpus" \
    --meta_time_out "$meta_time_out"

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
            --dataset_name spider \
            --sample_size 100 \
            --generate_chart
        
        echo ""
        echo "Error analysis complete. Results saved to: $error_analysis_path"
    else
        echo "ERROR: Evaluation result not found: $eval_result_path"
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
echo "  - ${output_dir}evaluation_report.json (summary report)"
if [ "$RUN_ERROR_ANALYSIS" = true ]; then
    echo "  - ${output_dir}error_analysis.json (error categorization)"
    echo "  - ${output_dir}error_analysis_chart.png (pie chart)"
fi
echo ""