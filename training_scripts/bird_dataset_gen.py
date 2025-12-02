import json
from pathlib import Path
import re

# =====================================================
# Paths
# =====================================================
DEV_TABLES_PATH = Path("../data/bird/dev_tables.json")   # adjust if needed
OUT_PATH = Path("data/raw/bird_error_sql-llama-instruct.jsonl")

# =====================================================
# Templates extracted from sql-llama-instruct-v0.5.jsonl
# and spider_error_sql-llama-instruct.jsonl
# =====================================================

SCHEMA_SELECTION_TEMPLATE = """As an experienced and professional database administrator, your task is to analyze a user question and a database schema to provide relevant information for text-to-SQL generation. You should carefully evaluate and select the most relevant tables and columns based on the user question and evidence provided.

[Instruction]:
1. Discard any table schema that is not related to the user question and evidence.
2. Sort the columns in each relevant table in descending order of relevance and keep the top 6 columns.
3. Ensure that at least 3 tables are included in the final output JSON.
4. The output should be in JSON format.

Requirements:
1. If a table has less than or equal to 10 columns, mark it as "keep_all".
2. If a table is completely irrelevant to the user question and evidence, mark it as "drop_all".
3. Prioritize the columns in each relevant table based on their relevance.

==========

【DB_ID】 {db_id}
【Schema】
{schema_block}

【Foreign keys】
{fk_block}

【Question】
{question}

【Evidence】
{evidence}

【Answer】"""

SQL_GENERATION_TEMPLATE = """Given a 【Database schema】 description, a knowledge 【Evidence】 and the 【Question】, you need to use valid SQLite and understand databases and different table structures to decompose the question into subquestions for text-to-SQL generation.
When generating SQL, we should always consider constraints:
【Constraints】
- In `SELECT <column>`, just select needed columns in the 【Question】 without any unnecessary column or value
- In `FROM <table>` or `JOIN <table>`, do not include unnecessary table
- If use max or min func, `JOIN <table>` FIRST, THEN use `SELECT MAX(<column>)` or `SELECT MIN(<column>)`
- If [Value examples] of <column> has 'None' or None, use `JOIN <table>` or `WHERE <column> is NOT NULL` is better
- If use `ORDER BY <column> ASC|DESC`, add `GROUP BY <column>` before to select distinct values

==========

【Database schema】
{schema_block}

【Foreign keys】
{fk_block}

【Question】
{question}

【Evidence】
{evidence}

Decompose the question into sub questions, considering 【Constraints】, and generate the SQL after thinking step by step:"""

# =====================================================
# Helper functions
# =====================================================

def render_schema_block(db):
    """Pretty-print each table + columns"""
    tables = db["table_names_original"]
    cols = db["column_names_original"]
    col_types = db["column_types"]

    by_table = {i: [] for i in range(len(tables))}
    for idx, (tid, cname) in enumerate(cols):
        if tid == -1:
            continue
        by_table[tid].append((cname, col_types[idx]))

    out = []
    for tid, tname in enumerate(tables):
        out.append(f"# Table: {tname}")
        out.append("[")
        for cname, ctype in by_table[tid]:
            out.append(f"  ({cname}, type: {ctype}),")
        out.append("]")
    return "\n".join(out)


def render_fk_block(db):
    """Pretty-print FK constraints"""
    tables = db["table_names_original"]
    cols = db["column_names_original"]

    lines = []
    for fk_from, fk_to in db["foreign_keys"]:
        child_tid, child_col = cols[fk_from]
        parent_tid, parent_col = cols[fk_to]
        if child_tid < 0 or parent_tid < 0:
            continue
        lines.append(
            f"{tables[child_tid]}.`{child_col}` = {tables[parent_tid]}.`{parent_col}`"
        )
    return "\n".join(lines)


def pluralize(name):
    """Simple pluralization for readability."""
    n = name.replace("_", " ")
    if n.endswith("y") and not n.endswith(("ay", "ey", "iy", "oy", "uy")):
        return n[:-1] + "ies"
    if n.endswith("s"):
        return n
    return n + "s"


def find_date_and_text_columns(db):
    """Find tables containing at least one date/datetime + one text column."""
    tables = db["table_names_original"]
    cols = db["column_names_original"]
    types = db["column_types"]

    by_table = {i: [] for i in range(len(tables))}

    for idx, (tid, cname) in enumerate(cols):
        if tid == -1:
            continue
        by_table[tid].append((cname, types[idx], idx))

    candidates = []
    for tid, columns in by_table.items():
        date_cols = [c for c in columns if c[1] in ("date", "datetime")]
        text_cols = [c for c in columns if c[1] == "text"]
        if date_cols and text_cols:
            candidates.append((tid, tables[tid], date_cols[0], text_cols[0]))
    return candidates


def build_question(parent_table, date_col):
    """Your required template:
       How many percent of {parent_phrase} were issued prior to {child_phrase}?"""

    parent_phrase = pluralize(parent_table)
    child_phrase = date_col.replace("_", " ")
    return f"How many percent of {parent_phrase} were issued prior to {child_phrase}?"


def build_sql(parent_table, id_col, cat_col, date_col):
    """SQL template like the BIRD example."""

    return f"""
SELECT CAST(SUM({cat_col} = 'gold') AS REAL) * 100 / COUNT({id_col})
FROM {parent_table}
WHERE STRFTIME('%Y', {date_col}) < '1998';
""".strip()


def build_selection_answer(db, target_table):
    """Mark relevant/dropped tables following your rule."""
    tables = db["table_names_original"]
    cols = db["column_names_original"]

    by_table_cols = {t: [] for t in tables}
    for tid, cname in cols:
        if tid == -1:
            continue
        by_table_cols[tables[tid]].append(cname)

    out = {}
    for t in tables:
        if t == target_table:
            out[t] = "keep_all" if len(by_table_cols[t]) <= 10 else by_table_cols[t][:6]
        else:
            out[t] = "drop_all"
    return out


# =====================================================
# Main generation
# =====================================================

def main():
    data = json.loads(DEV_TABLES_PATH.read_text())
    db_map = {d["db_id"]: d for d in data}

    records = []
    idx = 0

    for db in data:
        db_id = db["db_id"]
        schema_block = render_schema_block(db)
        fk_block = render_fk_block(db)

        # find tables w/ (date + text)
        cands = find_date_and_text_columns(db)

        for (tid, table_name, (date_col, _, date_idx), (cat_col, _, cat_idx)) in cands:

            # ID column: choose primary key if possible
            pk = db.get("primary_keys", [])
            id_col = None
            for p in pk:
                if isinstance(p, list):
                    continue
                col_tid, col_name = db["column_names_original"][p]
                if col_tid == tid:
                    id_col = col_name
                    break
            if id_col is None:
                # fallback: first INT column
                for tab_id, col_name in db["column_names_original"]:
                    pass
                id_col = date_col  # fallback fallback

            question = build_question(table_name, date_col)
            evidence = "Percent = [ count(category='gold' and date < 1998) / count(*) ] * 100%"  # dummy evidence
            sql = build_sql(table_name, id_col, cat_col, date_col)

            # =========================
            # Schema-selection record
            # =========================
            user_sel = SCHEMA_SELECTION_TEMPLATE.format(
                db_id=db_id,
                schema_block=schema_block,
                fk_block=fk_block,
                question=question,
                evidence=evidence
            )
            sel_json = build_selection_answer(db, table_name)
            assistant_sel = "\n```json\n" + json.dumps(sel_json, indent=2) + "\n```\n"

            records.append({
                "idx": idx,
                "db_id": db_id,
                "task": "schema_selection",
                "messages": [
                    {"role": "system", "content": ""},
                    {"role": "user", "content": user_sel},
                    {"role": "assistant", "content": assistant_sel}
                ]
            })
            idx += 1

            # =========================
            # SQL-generation record
            # =========================
            user_sql = SQL_GENERATION_TEMPLATE.format(
                schema_block=schema_block,
                fk_block=fk_block,
                question=question,
                evidence=evidence
            )

            assistant_sql = (
                f"\nSub question 1: {question}\n"
                "SQL\n```sql\n"
                f"{sql}\n```\nQuestion Solved.\n"
            )

            records.append({
                "idx": idx,
                "db_id": db_id,
                "task": "sql_generation",
                "messages": [
                    {"role": "system", "content": ""},
                    {"role": "user", "content": user_sql},
                    {"role": "assistant", "content": assistant_sql}
                ]
            })
            idx += 1

    # write file
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Generated {len(records)} records → {OUT_PATH}")


if __name__ == "__main__":
    main()
