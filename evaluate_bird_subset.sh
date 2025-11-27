#!/bin/bash

# 1. Database Path
db_root_path="./data/bird/dev_databases/"

# 2. Paths to your 8-DB SUBSET files
diff_json_path="./data/bird/dev_subset_8.json" 
# CORRECT
predicted_sql_json_path="./outputs/bird_subset_8/predict_dev_fixed.json"
ground_truth_sql_path="./data/bird/dev_gold_subset_8.sql"

# 3. Settings
data_mode="dev"
num_cpus=4
meta_time_out=30.0
time_out=60
mode_gt="gt"
mode_predict="gpt"

# --- RUN EVALUATION ---

echo "------------------------------------------------"
echo "Starting EX (Accuracy) Evaluation..."
python ./evaluation/evaluation_bird_ex.py \
    --db_root_path $db_root_path \
    --predicted_sql_json_path $predicted_sql_json_path \
    --data_mode $data_mode \
    --ground_truth_sql_path $ground_truth_sql_path \
    --num_cpus $num_cpus \
    --mode_predict $mode_predict \
    --diff_json_path $diff_json_path \
    --meta_time_out $meta_time_out

echo "------------------------------------------------"
echo "Starting VES (Efficiency) Evaluation..."
python ./evaluation/evaluation_bird_ves.py \
    --db_root_path $db_root_path \
    --predicted_sql_json_path $predicted_sql_json_path \
    --data_mode $data_mode \
    --ground_truth_sql_path $ground_truth_sql_path \
    --num_cpus $num_cpus \
    --meta_time_out $time_out \
    --mode_gt $mode_gt \
    --mode_predict $mode_predict \
    --diff_json_path $diff_json_path