import json
import os

# 1. Define the 8 databases
TARGET_DBS = [     # ~100+ queries    # ~100+ queries
             # ~100 queries
    "california_schools",            # ~50 queries
    "card_games",
    "codebase_community"
]

# Paths
INPUT_DEV_JSON = "./data/bird/dev.json"
OUTPUT_DEV_SUBSET = "./data/bird/dev_subset_8.json"
OUTPUT_GOLD_SQL = "./data/bird/dev_gold_subset_8.sql"

def prepare_subset():
    print(f"Filtering for 8 databases: {TARGET_DBS}")

    if not os.path.exists(INPUT_DEV_JSON):
        print(f"❌ Error: {INPUT_DEV_JSON} not found. Did you download the BIRD data?")
        return

    with open(INPUT_DEV_JSON, 'r', encoding='utf-8') as f:
        dev_data = json.load(f)

    subset_json = []
    gold_sql_lines = []

    for item in dev_data:
        if item['db_id'] in TARGET_DBS:
            subset_json.append(item)
            clean_sql = item['SQL'].replace('\n', ' ').strip()
            gold_line = f"{clean_sql}\t{item['db_id']}\n"
            gold_sql_lines.append(gold_line)

    with open(OUTPUT_DEV_SUBSET, 'w', encoding='utf-8') as f:
        json.dump(subset_json, f, indent=2, ensure_ascii=False)

    with open(OUTPUT_GOLD_SQL, 'w', encoding='utf-8') as f:
        f.writelines(gold_sql_lines)

    print(f"✅ Done! Generated input for {len(subset_json)} questions.")

if __name__ == "__main__":
    prepare_subset()