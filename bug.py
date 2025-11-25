# Create file: clean_gold.py
import os

FILE = "./data/bird/dev_gold_subset_8.sql"

with open(FILE, 'r') as f:
    lines = [line for line in f.readlines() if line.strip()]

with open(FILE, 'w') as f:
    f.writelines(lines)

print(f"Cleaned {len(lines)} lines in {FILE}")