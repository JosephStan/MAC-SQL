import json
import os

# 1. Define the 10 databases you want to test
# You can change these IDs to whatever you like found in data/spider/database/
TARGET_DBS = [
    "concert_singer",
    "pets_1",
    "car_1",
    "flight_1",
    "employee_hire_evaluation",
    "cre_Doc_Template_Mgt",
    "course_teach",
    "museum_visit",
    "wta_1",
    "battle_death"
]

# Paths (Adjust if your paths are different)
INPUT_DEV_JSON = "./data/spider/dev.json"
INPUT_GOLD_SQL = "./data/spider/dev_gold.sql"

OUTPUT_DEV_SUBSET = "./data/spider/dev_subset_10.json"
OUTPUT_GOLD_SUBSET = "./data/spider/dev_gold_subset_10.sql"

def prepare_subset():
    print(f"Filtering for databases: {TARGET_DBS}")

    # 1. Load original dev.json
    with open(INPUT_DEV_JSON, 'r', encoding='utf-8') as f:
        dev_data = json.load(f)

    # 2. Load original gold sqls
    # dev_gold.sql corresponds line-by-line to dev.json
    with open(INPUT_GOLD_SQL, 'r', encoding='utf-8') as f:
        gold_lines = f.readlines()

    subset_json = []
    subset_gold_lines = []

    # 3. Filter
    # We iterate by index to keep JSON and Gold SQL aligned
    for i, item in enumerate(dev_data):
        if item['db_id'] in TARGET_DBS:
            subset_json.append(item)
            subset_gold_lines.append(gold_lines[i])

    # 4. Save new JSON (Input for run.py)
    with open(OUTPUT_DEV_SUBSET, 'w', encoding='utf-8') as f:
        json.dump(subset_json, f, indent=2, ensure_ascii=False)
    
    # 5. Save new Gold SQL (Input for evaluation_spider.py)
    with open(OUTPUT_GOLD_SUBSET, 'w', encoding='utf-8') as f:
        f.writelines(subset_gold_lines)

    print(f"Done! Extracted {len(subset_json)} questions.")
    print(f"Input file saved to: {OUTPUT_DEV_SUBSET}")
    print(f"Gold file saved to:  {OUTPUT_GOLD_SUBSET}")

if __name__ == "__main__":
    prepare_subset()