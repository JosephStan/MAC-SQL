import json
import os
import argparse

# Define the default databases for subset_8 (legacy support)
# These are common databases found in BIRD dev set
TARGET_DBS_DEFAULT = [
    "california_schools",  # ~50+ queries
    "card_games",          # Gaming data
    "codebase_community"   # Community platform data
]

# Paths
INPUT_DEV_JSON = "./data/bird/dev.json"
OUTPUT_DEV_SUBSET = "./data/bird/dev_subset_8.json"
OUTPUT_GOLD_SQL = "./data/bird/dev_gold_subset_8.sql"


def prepare_subset(target_dbs=None, input_path=None, output_json_path=None, output_sql_path=None):
    """
    Prepare a subset of BIRD data for evaluation.
    
    Args:
        target_dbs: List of database IDs to include. If None, uses defaults.
        input_path: Path to input dev.json
        output_json_path: Path for output JSON
        output_sql_path: Path for output SQL file
    """
    target_dbs = target_dbs or TARGET_DBS_DEFAULT
    input_path = input_path or INPUT_DEV_JSON
    output_json_path = output_json_path or OUTPUT_DEV_SUBSET
    output_sql_path = output_sql_path or OUTPUT_GOLD_SQL
    
    print(f"Filtering for databases: {target_dbs}")

    if not os.path.exists(input_path):
        print(f"❌ Error: {input_path} not found. Did you download the BIRD data?")
        return False

    with open(input_path, 'r', encoding='utf-8') as f:
        dev_data = json.load(f)

    subset_json = []
    gold_sql_lines = []
    db_counts = {}

    for item in dev_data:
        if item['db_id'] in target_dbs:
            subset_json.append(item)
            clean_sql = item['SQL'].replace('\n', ' ').strip()
            gold_line = f"{clean_sql}\t{item['db_id']}\n"
            gold_sql_lines.append(gold_line)
            
            # Track counts per database
            db_id = item['db_id']
            db_counts[db_id] = db_counts.get(db_id, 0) + 1

    # Create output directory if needed
    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)

    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(subset_json, f, indent=2, ensure_ascii=False)

    with open(output_sql_path, 'w', encoding='utf-8') as f:
        f.writelines(gold_sql_lines)

    print(f"✅ Done! Generated input for {len(subset_json)} questions.")
    print(f"   Databases included:")
    for db_id, count in sorted(db_counts.items()):
        print(f"     - {db_id}: {count} queries")
    print(f"   Output JSON: {output_json_path}")
    print(f"   Output SQL: {output_sql_path}")
    
    return True


def list_available_databases(input_path=None):
    """List all available databases in the dev.json file."""
    input_path = input_path or INPUT_DEV_JSON
    
    if not os.path.exists(input_path):
        print(f"❌ Error: {input_path} not found.")
        return {}
    
    with open(input_path, 'r', encoding='utf-8') as f:
        dev_data = json.load(f)
    
    db_counts = {}
    for item in dev_data:
        db_id = item['db_id']
        db_counts[db_id] = db_counts.get(db_id, 0) + 1
    
    print(f"Available databases in {input_path}:")
    print("-" * 40)
    for db_id, count in sorted(db_counts.items(), key=lambda x: -x[1]):
        print(f"  {db_id}: {count} queries")
    print("-" * 40)
    print(f"Total: {len(db_counts)} databases, {len(dev_data)} queries")
    
    return db_counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Prepare BIRD subset for evaluation')
    parser.add_argument('--input', type=str, default=INPUT_DEV_JSON,
                        help='Path to input dev.json')
    parser.add_argument('--output_json', type=str, default=OUTPUT_DEV_SUBSET,
                        help='Path for output JSON')
    parser.add_argument('--output_sql', type=str, default=OUTPUT_GOLD_SQL,
                        help='Path for output SQL file')
    parser.add_argument('--databases', type=str, nargs='+', default=None,
                        help='List of database IDs to include')
    parser.add_argument('--list', action='store_true',
                        help='List available databases and exit')
    
    args = parser.parse_args()
    
    if args.list:
        list_available_databases(args.input)
    else:
        prepare_subset(
            target_dbs=args.databases,
            input_path=args.input,
            output_json_path=args.output_json,
            output_sql_path=args.output_sql
        )