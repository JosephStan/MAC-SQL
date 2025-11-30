#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Prepare BIRD Subsets for Evaluation

This script prepares 10 database subsets from the BIRD dev set for evaluation.
Each subset contains a specific set of databases to allow for controlled evaluation.

The 10 subsets are designed to cover different complexities and sizes of databases.

Usage:
    python prepare_bird_subsets.py --input_dev_json ./data/bird/dev.json \
                                   --output_dir ./data/bird/subsets/
"""

import os
import json
import argparse
from typing import Dict, List
from collections import defaultdict


# Define 10 subsets with different database combinations
# These are selected to provide diversity in evaluation
BIRD_SUBSETS = {
    "subset_1": {
        "name": "Financial & Schools",
        "databases": ["california_schools", "financial"],
        "description": "School data and financial records"
    },
    "subset_2": {
        "name": "Card Games & Community",
        "databases": ["card_games", "codebase_community"],
        "description": "Gaming and community platform data"
    },
    "subset_3": {
        "name": "Healthcare & Sports",
        "databases": ["thrombosis_prediction", "european_football_2"],
        "description": "Medical and sports data"
    },
    "subset_4": {
        "name": "Formula 1 & Superhero",
        "databases": ["formula_1", "superhero"],
        "description": "Racing and entertainment data"
    },
    "subset_5": {
        "name": "Debit Card & Student",
        "databases": ["debit_card_specializing", "student_club"],
        "description": "Financial transactions and student activities"
    },
    "subset_6": {
        "name": "Toxicology & Retail",
        "databases": ["toxicology", "retail_world"],
        "description": "Scientific and retail data"
    },
    "subset_7": {
        "name": "California Schools Only",
        "databases": ["california_schools"],
        "description": "Single database: California schools"
    },
    "subset_8": {
        "name": "Mixed Small",
        "databases": ["california_schools", "card_games", "codebase_community"],
        "description": "Mixed small databases"
    },
    "subset_9": {
        "name": "Large Mixed",
        "databases": ["financial", "european_football_2", "formula_1", "thrombosis_prediction"],
        "description": "Large mixed databases"
    },
    "subset_10": {
        "name": "Full Dev Sample",
        "databases": None,  # Will use all available databases up to 150 samples
        "description": "Sample from all databases"
    }
}


def get_available_databases(dev_data: List[Dict]) -> Dict[str, int]:
    """Get all available databases and their query counts."""
    db_counts = defaultdict(int)
    for item in dev_data:
        db_counts[item['db_id']] += 1
    return dict(db_counts)


def prepare_subset(dev_data: List[Dict], target_dbs: List[str], 
                   max_samples: int = None) -> List[Dict]:
    """Prepare a subset of data for specific databases."""
    if target_dbs is None:
        # Use all databases, but limit samples
        subset = dev_data[:max_samples] if max_samples else dev_data
    else:
        subset = [item for item in dev_data if item['db_id'] in target_dbs]
        if max_samples and len(subset) > max_samples:
            subset = subset[:max_samples]
    return subset


def generate_gold_sql_file(subset: List[Dict]) -> List[str]:
    """Generate gold SQL file lines from subset."""
    lines = []
    for item in subset:
        clean_sql = item['SQL'].replace('\n', ' ').strip()
        line = f"{clean_sql}\t{item['db_id']}\n"
        lines.append(line)
    return lines


def prepare_all_subsets(input_dev_json: str, output_dir: str, tables_json_path: str = None):
    """
    Prepare all 10 subsets for evaluation.
    
    Args:
        input_dev_json: Path to the BIRD dev.json file
        output_dir: Directory to save subset files
        tables_json_path: Optional path to tables.json for validation
    """
    print("="*60)
    print("BIRD SUBSET PREPARATION")
    print("="*60)
    
    # Load dev data
    if not os.path.exists(input_dev_json):
        print(f"Error: {input_dev_json} not found!")
        return
    
    with open(input_dev_json, 'r', encoding='utf-8') as f:
        dev_data = json.load(f)
    
    print(f"Loaded {len(dev_data)} samples from dev.json")
    
    # Get available databases
    db_counts = get_available_databases(dev_data)
    print(f"\nAvailable databases ({len(db_counts)} total):")
    for db, count in sorted(db_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  - {db}: {count} queries")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Process each subset
    summary = []
    for subset_id, config in BIRD_SUBSETS.items():
        print(f"\nPreparing {subset_id}: {config['name']}...")
        
        target_dbs = config['databases']
        
        # Check if databases exist
        if target_dbs:
            available = [db for db in target_dbs if db in db_counts]
            missing = [db for db in target_dbs if db not in db_counts]
            
            if missing:
                print(f"  Warning: Databases not found: {missing}")
            
            if not available:
                print(f"  Skipping {subset_id}: No available databases")
                continue
            
            target_dbs = available
        
        # Prepare subset
        max_samples = 150 if config['databases'] is None else None
        subset = prepare_subset(dev_data, target_dbs, max_samples)
        
        if len(subset) == 0:
            print(f"  Skipping {subset_id}: No samples found")
            continue
        
        # Save subset JSON
        subset_json_path = os.path.join(output_dir, f"dev_{subset_id}.json")
        with open(subset_json_path, 'w', encoding='utf-8') as f:
            json.dump(subset, f, indent=2, ensure_ascii=False)
        
        # Save gold SQL file
        gold_lines = generate_gold_sql_file(subset)
        gold_sql_path = os.path.join(output_dir, f"dev_gold_{subset_id}.sql")
        with open(gold_sql_path, 'w', encoding='utf-8') as f:
            f.writelines(gold_lines)
        
        # Get difficulty distribution
        difficulties = defaultdict(int)
        for item in subset:
            difficulties[item.get('difficulty', 'simple')] += 1
        
        info = {
            'subset_id': subset_id,
            'name': config['name'],
            'description': config['description'],
            'databases': list(set(item['db_id'] for item in subset)),
            'total_queries': len(subset),
            'difficulty_distribution': dict(difficulties),
            'json_path': subset_json_path,
            'gold_sql_path': gold_sql_path
        }
        summary.append(info)
        
        print(f"  Created: {len(subset)} queries from {len(info['databases'])} databases")
        print(f"  Difficulties: {dict(difficulties)}")
    
    # Save summary
    summary_path = os.path.join(output_dir, 'subsets_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print("\n" + "="*60)
    print("SUBSET PREPARATION COMPLETE")
    print("="*60)
    print(f"Created {len(summary)} subsets in {output_dir}")
    print(f"Summary saved to: {summary_path}")
    
    # Print usage instructions
    print("\nTo run evaluation on a subset:")
    print(f"  python run.py --dataset_name bird \\")
    print(f"                --input_file {output_dir}/dev_subset_1.json \\")
    print(f"                --db_path ./data/bird/dev_databases/ \\")
    print(f"                --tables_json_path ./data/bird/dev_tables.json \\")
    print(f"                --output_file ./outputs/bird_subset_1/output_dev.jsonl")


def main():
    parser = argparse.ArgumentParser(description='Prepare BIRD subsets for evaluation')
    parser.add_argument('--input_dev_json', type=str, default='./data/bird/dev.json',
                        help='Path to BIRD dev.json file')
    parser.add_argument('--output_dir', type=str, default='./data/bird/subsets/',
                        help='Directory to save subset files')
    parser.add_argument('--tables_json_path', type=str, default=None,
                        help='Optional path to tables.json for validation')
    
    args = parser.parse_args()
    
    prepare_all_subsets(
        input_dev_json=args.input_dev_json,
        output_dir=args.output_dir,
        tables_json_path=args.tables_json_path
    )


if __name__ == '__main__':
    main()
