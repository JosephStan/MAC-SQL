import json
import os
import argparse

# Paths
INPUT_DEV_JSON = "./data/spider/dev.json"
INPUT_GOLD_SQL = "./data/spider/dev_gold.sql"

OUTPUT_DEV_SUBSET = "./data/spider/dev_subset.json"
OUTPUT_GOLD_SUBSET = "./data/spider/dev_gold_subset.sql"


def list_databases():
    """List all available databases with question counts."""
    if not os.path.exists(INPUT_DEV_JSON):
        print(f"❌ Error: {INPUT_DEV_JSON} not found.")
        return
    
    with open(INPUT_DEV_JSON, 'r', encoding='utf-8') as f:
        dev_data = json.load(f)
    
    db_counts = {}
    for item in dev_data:
        db_id = item['db_id']
        db_counts[db_id] = db_counts.get(db_id, 0) + 1
    
    print("\n📊 Available Spider Databases:")
    print("=" * 50)
    total = 0
    for db_id, count in sorted(db_counts.items(), key=lambda x: -x[1]):
        print(f"  {db_id}: {count} questions")
        total += count
    print("=" * 50)
    print(f"  TOTAL: {total} questions across {len(db_counts)} databases")


def prepare_subset(max_questions=400):
    """Prepare a subset of Spider data with approximately max_questions."""
    
    print(f"Preparing Spider subset with max {max_questions} questions...")

    if not os.path.exists(INPUT_DEV_JSON):
        print(f"❌ Error: {INPUT_DEV_JSON} not found.")
        print("Please download data.zip from:")
        print("https://drive.google.com/file/d/1kkkNJSmJkZKeZyDFUDG7c4mnkxsrr-om/view")
        return False

    # Load original data
    with open(INPUT_DEV_JSON, 'r', encoding='utf-8') as f:
        dev_data = json.load(f)

    with open(INPUT_GOLD_SQL, 'r', encoding='utf-8') as f:
        gold_lines = f.readlines()

    subset_json = []
    subset_gold_lines = []

    # Take first max_questions (they're already diverse across databases)
    for i, item in enumerate(dev_data):
        if len(subset_json) >= max_questions:
            break
        subset_json.append(item)
        subset_gold_lines.append(gold_lines[i])

    # Save subset JSON
    with open(OUTPUT_DEV_SUBSET, 'w', encoding='utf-8') as f:
        json.dump(subset_json, f, indent=2, ensure_ascii=False)
    
    # Save subset Gold SQL
    with open(OUTPUT_GOLD_SUBSET, 'w', encoding='utf-8') as f:
        f.writelines(subset_gold_lines)

    # Count databases in subset
    db_counts = {}
    for item in subset_json:
        db_id = item['db_id']
        db_counts[db_id] = db_counts.get(db_id, 0) + 1

    print(f"\n✅ Created Spider subset with {len(subset_json)} questions")
    print(f"   Databases included: {len(db_counts)}")
    print(f"\n📁 Files created:")
    print(f"   - {OUTPUT_DEV_SUBSET}")
    print(f"   - {OUTPUT_GOLD_SUBSET}")
    
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Prepare Spider subset for evaluation')
    parser.add_argument('--list', action='store_true', help='List available databases')
    parser.add_argument('--max_questions', type=int, default=400, 
                        help='Maximum number of questions (default: 400)')
    
    args = parser.parse_args()
    
    if args.list:
        list_databases()
    else:
        prepare_subset(max_questions=args.max_questions)