#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Comprehensive Evaluation Runner for MAC-SQL Framework

This script evaluates the MAC-SQL framework on BIRD dataset with:
- Execution Accuracy (EX) - proportion of correct SQL execution results
- Valid Efficiency Score (VES) - measures efficiency of valid SQLs

Based on the evaluation metrics described in the MAC-SQL paper:
- EX: Proportion of questions where predicted and ground-truth SQL return identical results
- VES: Measures the efficiency of valid SQLs by comparing execution times

Usage:
    python evaluation_runner.py --dataset bird \
                                --db_root_path ./data/bird/dev_databases/ \
                                --predicted_sql_path ./outputs/bird_subset_8/predict_dev.json \
                                --ground_truth_path ./data/bird/dev_gold_subset_8.sql \
                                --diff_json_path ./data/bird/dev_subset_8.json \
                                --output_dir ./outputs/bird_subset_8/ \
                                --run_ves
"""

import os
import re
import sys
import json
import time
import math
import sqlite3
import argparse
import numpy as np
import multiprocessing as mp
from typing import Dict, List, Tuple, Optional
from func_timeout import func_timeout, FunctionTimedOut
from datetime import datetime


# Global variable for multiprocessing results
exec_result = []
ves_result = []


def result_callback_ex(result):
    """Callback for EX evaluation results."""
    exec_result.append(result)


def result_callback_ves(result):
    """Callback for VES evaluation results."""
    ves_result.append(result)


def replace_multiple_spaces(text: str) -> str:
    """Replace multiple spaces with single space."""
    return re.sub(r'\s+', ' ', text)


def load_json(path: str) -> any:
    """Load JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path: str, data: any):
    """Save data to JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved to {path}")


def clean_abnormal(input_data: list) -> list:
    """Remove outliers from timing data (for VES calculation)."""
    input_arr = np.asarray(input_data)
    processed_list = []
    mean = np.mean(input_arr, axis=0)
    std = np.std(input_arr, axis=0)
    for x in input_arr:
        if x < mean + 3 * std and x > mean - 3 * std:
            processed_list.append(x)
    return processed_list


# ==================== EX Evaluation Functions ====================

def execute_sql_ex(predicted_sql: str, ground_truth: str, db_path: str) -> int:
    """Execute SQL for EX evaluation."""
    conn = sqlite3.connect(db_path)
    conn.text_factory = lambda b: b.decode(errors="ignore")
    cursor = conn.cursor()
    
    cursor.execute(predicted_sql)
    predicted_res = cursor.fetchall()
    
    cursor.execute(ground_truth)
    ground_truth_res = cursor.fetchall()
    
    conn.close()
    
    # Compare results as sets
    if set(predicted_res) == set(ground_truth_res):
        return 1
    return 0


def execute_model_ex(predicted_sql: str, ground_truth: str, db_place: str, 
                     idx: int, meta_time_out: float) -> Dict:
    """Execute model for EX evaluation with timeout."""
    try:
        res = func_timeout(meta_time_out, execute_sql_ex,
                          args=(predicted_sql, ground_truth, db_place))
    except KeyboardInterrupt:
        sys.exit(0)
    except FunctionTimedOut:
        res = 0
    except Exception as e:
        res = 0
    
    return {'sql_idx': idx, 'res': res}


# ==================== VES Evaluation Functions ====================

def execute_sql_timed(sql: str, db_path: str) -> float:
    """Execute SQL and return execution time."""
    conn = sqlite3.connect(db_path)
    conn.text_factory = lambda b: b.decode(errors="ignore")
    cursor = conn.cursor()
    
    start_time = time.time()
    cursor.execute(sql)
    exec_time = time.time() - start_time
    
    conn.close()
    return exec_time


def iterated_execute_sql_ves(predicted_sql: str, ground_truth: str, 
                             db_path: str, iterate_num: int) -> float:
    """Execute SQL multiple times for VES calculation."""
    if predicted_sql.strip() == ground_truth.strip():
        return 1.0
    
    conn = sqlite3.connect(db_path)
    conn.text_factory = lambda b: b.decode(errors="ignore")
    cursor = conn.cursor()
    
    cursor.execute(predicted_sql)
    predicted_res = cursor.fetchall()
    
    cursor.execute(ground_truth)
    ground_truth_res = cursor.fetchall()
    
    conn.close()
    
    time_ratio = 0
    if set(predicted_res) == set(ground_truth_res):
        diff_list = []
        for _ in range(iterate_num):
            predicted_time = execute_sql_timed(predicted_sql, db_path)
            ground_truth_time = execute_sql_timed(ground_truth, db_path)
            if predicted_time > 0:
                diff_list.append(ground_truth_time / predicted_time)
        
        if diff_list:
            processed_diff_list = clean_abnormal(diff_list)
            if processed_diff_list:
                time_ratio = sum(processed_diff_list) / len(processed_diff_list)
    
    return time_ratio


def execute_model_ves(predicted_sql: str, ground_truth: str, db_place: str,
                      idx: int, iterate_num: int, meta_time_out: float) -> Dict:
    """Execute model for VES evaluation with timeout."""
    try:
        time_ratio = func_timeout(meta_time_out * iterate_num, iterated_execute_sql_ves,
                                 args=(predicted_sql, ground_truth, db_place, iterate_num))
    except KeyboardInterrupt:
        sys.exit(0)
    except FunctionTimedOut:
        time_ratio = 0
    except Exception as e:
        time_ratio = 0
    
    return {'sql_idx': idx, 'time_ratio': time_ratio}


# ==================== SQL Packaging Functions ====================

def package_sqls_bird(sql_path: str, db_root_path: str, mode: str = 'gpt') -> Tuple[List, List]:
    """Package SQLs for BIRD dataset."""
    clean_sqls = []
    db_path_list = []
    
    if mode == 'gpt':
        sql_data = load_json(sql_path)
        for idx, sql_str in sql_data:
            if isinstance(sql_str, str):
                parts = sql_str.split('\t----- bird -----\t')
                if len(parts) == 2:
                    sql, db_name = parts
                else:
                    sql, db_name = sql_str, "financial"
            else:
                sql, db_name = " ", "financial"
            clean_sqls.append(sql)
            db_path_list.append(os.path.join(db_root_path, db_name, f"{db_name}.sqlite"))
    
    elif mode == 'gt':
        with open(sql_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    sql, db_name = parts[0], parts[1]
                    clean_sqls.append(sql)
                    db_path_list.append(os.path.join(db_root_path, db_name, f"{db_name}.sqlite"))
    
    return clean_sqls, db_path_list


# ==================== Parallel Execution ====================

def run_sqls_parallel_ex(sqls: List[Tuple], db_places: List[str], 
                         num_cpus: int = 1, meta_time_out: float = 30.0):
    """Run EX evaluation in parallel."""
    global exec_result
    exec_result = []
    
    pool = mp.Pool(processes=num_cpus)
    for i, sql_pair in enumerate(sqls):
        predicted_sql, ground_truth = sql_pair
        pool.apply_async(execute_model_ex, 
                        args=(predicted_sql, ground_truth, db_places[i], i, meta_time_out),
                        callback=result_callback_ex)
    pool.close()
    pool.join()


def run_sqls_parallel_ves(sqls: List[Tuple], db_places: List[str],
                          num_cpus: int = 1, iterate_num: int = 100,
                          meta_time_out: float = 30.0):
    """Run VES evaluation in parallel."""
    global ves_result
    ves_result = []
    
    pool = mp.Pool(processes=num_cpus)
    for i, sql_pair in enumerate(sqls):
        predicted_sql, ground_truth = sql_pair
        pool.apply_async(execute_model_ves,
                        args=(predicted_sql, ground_truth, db_places[i], i, iterate_num, meta_time_out),
                        callback=result_callback_ves)
    pool.close()
    pool.join()


# ==================== Score Computation ====================

def sort_results(list_of_dicts: List[Dict]) -> List[Dict]:
    """Sort results by SQL index."""
    return sorted(list_of_dicts, key=lambda x: x['sql_idx'])


def compute_ex_by_difficulty(exec_results: List[Dict], diff_json_path: str) -> Tuple:
    """Compute EX accuracy by difficulty level."""
    num_queries = len(exec_results)
    results = [res['res'] for res in exec_results]
    contents = load_json(diff_json_path)
    
    simple_results = []
    moderate_results = []
    challenging_results = []
    
    for i, content in enumerate(contents):
        difficulty = content.get('difficulty', 'simple')
        if i < len(exec_results):
            if difficulty == 'simple':
                simple_results.append(exec_results[i])
            elif difficulty == 'moderate':
                moderate_results.append(exec_results[i])
            elif difficulty == 'challenging':
                challenging_results.append(exec_results[i])
    
    simple_acc = sum([r['res'] for r in simple_results]) / len(simple_results) if simple_results else 0
    moderate_acc = sum([r['res'] for r in moderate_results]) / len(moderate_results) if moderate_results else 0
    challenging_acc = sum([r['res'] for r in challenging_results]) / len(challenging_results) if challenging_results else 0
    all_acc = sum(results) / num_queries if num_queries > 0 else 0
    
    count_lists = [len(simple_results), len(moderate_results), len(challenging_results), num_queries]
    
    return (simple_acc * 100, moderate_acc * 100, challenging_acc * 100, all_acc * 100, count_lists)


def compute_ves(exec_results: List[Dict]) -> float:
    """Compute VES score."""
    num_queries = len(exec_results)
    if num_queries == 0:
        return 0
    
    total_ratio = 0
    for result in exec_results:
        total_ratio += math.sqrt(result['time_ratio']) * 100
    
    return total_ratio / num_queries


def compute_ves_by_difficulty(exec_results: List[Dict], diff_json_path: str) -> Tuple:
    """Compute VES by difficulty level."""
    num_queries = len(exec_results)
    contents = load_json(diff_json_path)
    
    simple_results = []
    moderate_results = []
    challenging_results = []
    
    for i, content in enumerate(contents):
        difficulty = content.get('difficulty', 'simple')
        if i < len(exec_results):
            if difficulty == 'simple':
                simple_results.append(exec_results[i])
            elif difficulty == 'moderate':
                moderate_results.append(exec_results[i])
            elif difficulty == 'challenging':
                challenging_results.append(exec_results[i])
    
    simple_ves = compute_ves(simple_results)
    moderate_ves = compute_ves(moderate_results)
    challenging_ves = compute_ves(challenging_results)
    all_ves = compute_ves(exec_results)
    
    count_lists = [len(simple_results), len(moderate_results), len(challenging_results), num_queries]
    
    return (simple_ves, moderate_ves, challenging_ves, all_ves, count_lists)


# ==================== Report Generation ====================

def print_ex_results(score_lists: List[float], count_lists: List[int]):
    """Print EX results in formatted table."""
    levels = ['simple', 'moderate', 'challenging', 'total']
    print("\n" + "="*80)
    print("EXECUTION ACCURACY (EX) RESULTS")
    print("="*80)
    print("{:20} {:20} {:20} {:20} {:20}".format("", *levels))
    print("{:20} {:<20} {:<20} {:<20} {:<20}".format('count', *count_lists))
    print("-"*80)
    print("{:20} {:<20.2f} {:<20.2f} {:<20.2f} {:<20.2f}".format('accuracy (%)', *score_lists))
    print("="*80)


def print_ves_results(score_lists: List[float], count_lists: List[int]):
    """Print VES results in formatted table."""
    levels = ['simple', 'moderate', 'challenging', 'total']
    print("\n" + "="*80)
    print("VALID EFFICIENCY SCORE (VES) RESULTS")
    print("="*80)
    print("{:20} {:20} {:20} {:20} {:20}".format("", *levels))
    print("{:20} {:<20} {:<20} {:<20} {:<20}".format('count', *count_lists))
    print("-"*80)
    print("{:20} {:<20.2f} {:<20.2f} {:<20.2f} {:<20.2f}".format('VES', *score_lists))
    print("="*80)


def generate_evaluation_report(ex_results: Dict, ves_results: Optional[Dict], 
                               output_path: str, dataset_name: str):
    """Generate comprehensive evaluation report."""
    report = {
        'evaluation_timestamp': datetime.now().isoformat(),
        'dataset': dataset_name,
        'metrics': {
            'EX': {
                'description': 'Execution Accuracy - proportion of correct SQL execution results',
                'overall': ex_results['all'],
                'by_difficulty': {
                    'simple': ex_results['simple'],
                    'moderate': ex_results['moderate'],
                    'challenging': ex_results['challenging']
                },
                'counts': {
                    'simple': ex_results['counts'][0],
                    'moderate': ex_results['counts'][1],
                    'challenging': ex_results['counts'][2],
                    'total': ex_results['counts'][3]
                }
            }
        }
    }
    
    if ves_results:
        report['metrics']['VES'] = {
            'description': 'Valid Efficiency Score - measures efficiency of valid SQLs',
            'overall': ves_results['all'],
            'by_difficulty': {
                'simple': ves_results['simple'],
                'moderate': ves_results['moderate'],
                'challenging': ves_results['challenging']
            },
            'counts': {
                'simple': ves_results['counts'][0],
                'moderate': ves_results['counts'][1],
                'challenging': ves_results['counts'][2],
                'total': ves_results['counts'][3]
            }
        }
    
    save_json(output_path, report)
    print(f"\nEvaluation report saved to: {output_path}")


# ==================== Main Evaluation Function ====================

def run_evaluation(predicted_sql_path: str, ground_truth_path: str,
                   db_root_path: str, diff_json_path: str,
                   output_dir: str, num_cpus: int = 4,
                   meta_time_out: float = 30.0, run_ves: bool = False,
                   ves_iterate_num: int = 100, ves_time_out: float = 60.0):
    """
    Run comprehensive evaluation with EX and optionally VES metrics.
    """
    global exec_result, ves_result
    
    print("\n" + "="*80)
    print("MAC-SQL EVALUATION RUNNER")
    print("="*80)
    print(f"Predicted SQL: {predicted_sql_path}")
    print(f"Ground Truth: {ground_truth_path}")
    print(f"Database Root: {db_root_path}")
    print(f"Difficulty JSON: {diff_json_path}")
    print(f"Output Directory: {output_dir}")
    print(f"Run VES: {run_ves}")
    print("="*80 + "\n")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Package SQLs
    print("Loading predicted SQLs...")
    pred_queries, db_paths = package_sqls_bird(predicted_sql_path, db_root_path, mode='gpt')
    
    print("Loading ground truth SQLs...")
    gt_queries, _ = package_sqls_bird(ground_truth_path, db_root_path, mode='gt')
    
    assert len(pred_queries) == len(gt_queries), \
        f"Mismatch: {len(pred_queries)} predictions vs {len(gt_queries)} ground truth"
    
    print(f"Total queries to evaluate: {len(pred_queries)}")
    
    query_pairs = list(zip(pred_queries, gt_queries))
    
    # ==================== EX Evaluation ====================
    print("\n" + "-"*40)
    print("Running EX (Execution Accuracy) Evaluation...")
    print("-"*40)
    
    exec_result = []
    run_sqls_parallel_ex(query_pairs, db_paths, num_cpus=num_cpus, meta_time_out=meta_time_out)
    exec_result = sort_results(exec_result)
    
    # Compute EX scores
    simple_ex, moderate_ex, challenging_ex, all_ex, ex_counts = \
        compute_ex_by_difficulty(exec_result, diff_json_path)
    
    ex_results = {
        'simple': round(simple_ex, 2),
        'moderate': round(moderate_ex, 2),
        'challenging': round(challenging_ex, 2),
        'all': round(all_ex, 2),
        'counts': ex_counts
    }
    
    print_ex_results([simple_ex, moderate_ex, challenging_ex, all_ex], ex_counts)
    
    # Save EX results with detailed info
    raw_json_data = load_json(diff_json_path)
    pred_sqls = [replace_multiple_spaces(s) for s in pred_queries]
    
    result_json_lst = []
    for i, item in enumerate(raw_json_data):
        if i < len(pred_sqls):
            item['pred'] = pred_sqls[i]
            item['gold'] = replace_multiple_spaces(item.get('SQL', ''))
            if 'SQL' in item:
                del item['SQL']
            item['res'] = exec_result[i]['res'] if i < len(exec_result) else 0
            result_json_lst.append(item)
    
    eval_result_path = os.path.join(output_dir, 'eval_result_dev.json')
    save_json(eval_result_path, result_json_lst)
    
    # ==================== VES Evaluation ====================
    ves_results = None
    if run_ves:
        print("\n" + "-"*40)
        print("Running VES (Valid Efficiency Score) Evaluation...")
        print("This may take a while...")
        print("-"*40)
        
        ves_result = []
        run_sqls_parallel_ves(query_pairs, db_paths, num_cpus=num_cpus,
                              iterate_num=ves_iterate_num, meta_time_out=ves_time_out)
        ves_result = sort_results(ves_result)
        
        # Compute VES scores
        simple_ves, moderate_ves, challenging_ves, all_ves, ves_counts = \
            compute_ves_by_difficulty(ves_result, diff_json_path)
        
        ves_results = {
            'simple': round(simple_ves, 2),
            'moderate': round(moderate_ves, 2),
            'challenging': round(challenging_ves, 2),
            'all': round(all_ves, 2),
            'counts': ves_counts
        }
        
        print_ves_results([simple_ves, moderate_ves, challenging_ves, all_ves], ves_counts)
    
    # ==================== Generate Report ====================
    report_path = os.path.join(output_dir, 'evaluation_report.json')
    generate_evaluation_report(ex_results, ves_results, report_path, 'bird')
    
    print("\n" + "="*80)
    print("EVALUATION COMPLETED")
    print("="*80)
    print(f"Results saved to: {output_dir}")
    print(f"  - eval_result_dev.json: Detailed evaluation results")
    print(f"  - evaluation_report.json: Summary report with EX" + (" and VES" if run_ves else ""))
    print("="*80 + "\n")
    
    return ex_results, ves_results


def main():
    parser = argparse.ArgumentParser(description='MAC-SQL Evaluation Runner')
    parser.add_argument('--dataset', type=str, default='bird', choices=['bird', 'spider'],
                        help='Dataset to evaluate')
    parser.add_argument('--predicted_sql_path', type=str, required=True,
                        help='Path to predicted SQL JSON file')
    parser.add_argument('--ground_truth_path', type=str, required=True,
                        help='Path to ground truth SQL file')
    parser.add_argument('--db_root_path', type=str, required=True,
                        help='Path to database root directory')
    parser.add_argument('--diff_json_path', type=str, required=True,
                        help='Path to difficulty JSON file')
    parser.add_argument('--output_dir', type=str, required=True,
                        help='Directory to save evaluation results')
    parser.add_argument('--num_cpus', type=int, default=4,
                        help='Number of CPUs for parallel execution')
    parser.add_argument('--meta_time_out', type=float, default=30.0,
                        help='Timeout for SQL execution (seconds)')
    parser.add_argument('--run_ves', action='store_true',
                        help='Run VES evaluation (time-consuming)')
    parser.add_argument('--ves_iterate_num', type=int, default=100,
                        help='Number of iterations for VES timing')
    parser.add_argument('--ves_time_out', type=float, default=60.0,
                        help='Timeout for VES execution (seconds)')
    
    args = parser.parse_args()
    
    run_evaluation(
        predicted_sql_path=args.predicted_sql_path,
        ground_truth_path=args.ground_truth_path,
        db_root_path=args.db_root_path,
        diff_json_path=args.diff_json_path,
        output_dir=args.output_dir,
        num_cpus=args.num_cpus,
        meta_time_out=args.meta_time_out,
        run_ves=args.run_ves,
        ves_iterate_num=args.ves_iterate_num,
        ves_time_out=args.ves_time_out
    )


if __name__ == '__main__':
    main()
