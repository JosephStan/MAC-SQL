#!/bin/bash
# =============================================================================
# MAC-SQL Comprehensive Evaluation Script
# =============================================================================
# This script runs evaluation on BIRD subsets with EX and VES metrics,
# performs error analysis, and generates visualizations.
#
# Usage:
#   ./run_comprehensive_evaluation.sh [subset_id]
#   
# Examples:
#   ./run_comprehensive_evaluation.sh          # Run all subsets
#   ./run_comprehensive_evaluation.sh subset_8 # Run only subset_8
#
# =============================================================================

set -e  # Exit on error

# Configuration
DB_ROOT_PATH="./data/bird/dev_databases/"
SUBSETS_DIR="./data/bird/subsets/"
OUTPUTS_BASE_DIR="./outputs/"
NUM_CPUS=4
META_TIME_OUT=30.0
VES_TIME_OUT=60
VES_ITERATE_NUM=100

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print header
print_header() {
    echo -e "${BLUE}"
    echo "=============================================================="
    echo "$1"
    echo "=============================================================="
    echo -e "${NC}"
}

# Print status
print_status() {
    echo -e "${GREEN}[STATUS]${NC} $1"
}

# Print warning
print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Print error
print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check Python
    if ! command -v python &> /dev/null; then
        print_error "Python is not installed"
        exit 1
    fi
    print_status "Python found: $(python --version)"
    
    # Check required packages
    python -c "import func_timeout" 2>/dev/null || {
        print_warning "func_timeout not found. Installing..."
        pip install func_timeout
    }
    
    python -c "import matplotlib" 2>/dev/null || {
        print_warning "matplotlib not found. Installing..."
        pip install matplotlib
    }
    
    python -c "import numpy" 2>/dev/null || {
        print_warning "numpy not found. Installing..."
        pip install numpy
    }
    
    # Check data directories
    if [ ! -d "$DB_ROOT_PATH" ]; then
        print_error "Database directory not found: $DB_ROOT_PATH"
        exit 1
    fi
    print_status "Database directory found: $DB_ROOT_PATH"
    
    # Check if subsets exist
    if [ ! -d "$SUBSETS_DIR" ]; then
        print_warning "Subsets directory not found. Creating subsets..."
        python prepare_bird_subsets.py --input_dev_json ./data/bird/dev.json --output_dir $SUBSETS_DIR
    fi
    print_status "Subsets directory found: $SUBSETS_DIR"
}

# Run evaluation for a single subset
run_subset_evaluation() {
    local subset_id=$1
    local subset_json="${SUBSETS_DIR}dev_${subset_id}.json"
    local gold_sql="${SUBSETS_DIR}dev_gold_${subset_id}.sql"
    local output_dir="${OUTPUTS_BASE_DIR}bird_${subset_id}/"
    local predict_json="${output_dir}predict_dev.json"
    
    print_header "Evaluating: $subset_id"
    
    # Check if subset files exist
    if [ ! -f "$subset_json" ]; then
        print_warning "Subset JSON not found: $subset_json. Skipping..."
        return
    fi
    
    if [ ! -f "$gold_sql" ]; then
        print_warning "Gold SQL not found: $gold_sql. Skipping..."
        return
    fi
    
    # Create output directory
    mkdir -p "$output_dir"
    
    # Check if predictions exist
    if [ ! -f "$predict_json" ]; then
        print_warning "Predictions not found: $predict_json"
        print_status "You need to run MAC-SQL first to generate predictions."
        print_status "Run: python run.py --dataset_name bird --input_file $subset_json \\"
        print_status "                   --db_path $DB_ROOT_PATH \\"
        print_status "                   --tables_json_path ./data/bird/dev_tables.json \\"
        print_status "                   --output_file ${output_dir}output_dev.jsonl"
        return
    fi
    
    print_status "Running EX evaluation..."
    python ./evaluation/evaluation_bird_ex.py \
        --db_root_path $DB_ROOT_PATH \
        --predicted_sql_json_path $predict_json \
        --data_mode dev \
        --ground_truth_sql_path $gold_sql \
        --num_cpus $NUM_CPUS \
        --mode_predict gpt \
        --diff_json_path $subset_json \
        --meta_time_out $META_TIME_OUT
    
    print_status "Running VES evaluation..."
    python ./evaluation/evaluation_bird_ves.py \
        --db_root_path $DB_ROOT_PATH \
        --predicted_sql_json_path $predict_json \
        --data_mode dev \
        --ground_truth_sql_path $gold_sql \
        --num_cpus $NUM_CPUS \
        --meta_time_out $VES_TIME_OUT \
        --mode_gt gt \
        --mode_predict gpt \
        --diff_json_path $subset_json
    
    # Run error analysis
    local eval_result="${output_dir}eval_result_dev.json"
    if [ -f "$eval_result" ]; then
        print_status "Running error analysis..."
        python ./evaluation/error_analysis.py \
            --eval_result_path $eval_result \
            --db_root_path $DB_ROOT_PATH \
            --output_path "${output_dir}error_analysis.json" \
            --dataset_name bird \
            --sample_size 100 \
            --generate_chart
    fi
    
    print_status "Completed evaluation for $subset_id"
}

# Generate combined report
generate_combined_report() {
    print_header "Generating Combined Report"
    
    python - << 'EOF'
import os
import json
from datetime import datetime

output_base = "./outputs/"
report = {
    "generated_at": datetime.now().isoformat(),
    "subsets": []
}

# Find all evaluation reports
for subset_dir in sorted(os.listdir(output_base)):
    if subset_dir.startswith("bird_subset"):
        eval_report = os.path.join(output_base, subset_dir, "evaluation_report.json")
        error_analysis = os.path.join(output_base, subset_dir, "error_analysis.json")
        
        subset_info = {"subset_id": subset_dir}
        
        if os.path.exists(eval_report):
            with open(eval_report, 'r') as f:
                subset_info["evaluation"] = json.load(f)
        
        if os.path.exists(error_analysis):
            with open(error_analysis, 'r') as f:
                ea = json.load(f)
                subset_info["error_analysis"] = {
                    "total_errors": ea.get("total_errors", 0),
                    "error_distribution": ea.get("error_distribution", {})
                }
        
        if len(subset_info) > 1:
            report["subsets"].append(subset_info)

# Calculate averages if we have results
if report["subsets"]:
    total_ex = 0
    total_ves = 0
    count_ex = 0
    count_ves = 0
    
    for subset in report["subsets"]:
        if "evaluation" in subset:
            metrics = subset["evaluation"].get("metrics", {})
            if "EX" in metrics:
                total_ex += metrics["EX"].get("overall", 0)
                count_ex += 1
            if "VES" in metrics:
                total_ves += metrics["VES"].get("overall", 0)
                count_ves += 1
    
    report["summary"] = {
        "average_EX": round(total_ex / count_ex, 2) if count_ex > 0 else 0,
        "average_VES": round(total_ves / count_ves, 2) if count_ves > 0 else 0,
        "subsets_evaluated": len(report["subsets"])
    }

# Save combined report
report_path = os.path.join(output_base, "combined_evaluation_report.json")
with open(report_path, 'w') as f:
    json.dump(report, f, indent=2)

print(f"Combined report saved to: {report_path}")

# Print summary
if "summary" in report:
    print("\n" + "="*50)
    print("EVALUATION SUMMARY")
    print("="*50)
    print(f"Subsets Evaluated: {report['summary']['subsets_evaluated']}")
    print(f"Average EX: {report['summary']['average_EX']}%")
    print(f"Average VES: {report['summary']['average_VES']}")
    print("="*50)
EOF
}

# Main execution
main() {
    print_header "MAC-SQL Comprehensive Evaluation"
    
    check_prerequisites
    
    # Get subset to evaluate
    local target_subset=$1
    
    if [ -z "$target_subset" ]; then
        # Run all subsets
        print_status "Running evaluation on all subsets..."
        for i in {1..10}; do
            run_subset_evaluation "subset_$i"
        done
    else
        # Run specific subset
        run_subset_evaluation "$target_subset"
    fi
    
    # Generate combined report
    generate_combined_report
    
    print_header "Evaluation Complete"
    print_status "Results saved to: $OUTPUTS_BASE_DIR"
}

# Run main with arguments
main "$@"
