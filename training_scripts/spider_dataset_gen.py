import json
from pathlib import Path

# ---------- Paths ----------
TABLES_PATH = Path("../data/spider/tables.json")  # adjust if needed
OUT_PATH = Path("data/raw/spider_error_sql-llama-instruct.jsonl")


# ---------- User message templates ----------

SCHEMA_SELECTION_USER_TEMPLATE = """As an experienced and professional database administrator, your task is to analyze a user question and a database schema to provide relevant information for text-to-SQL generation. You should carefully evaluate and select the most relevant tables and columns based on the user question and evidence provided.

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

SQL_GENERATION_USER_TEMPLATE = """Given a 【Database schema】 description, a knowledge 【Evidence】 and the 【Question】, you need to use valid SQLite and understand databases and different table structures to decompose the question into subquestions for text-to-SQL generation.
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


# ---------- Helpers ----------

def build_schema_block(db):
    """Render a simple schema description block for a DB."""
    table_names_orig = db["table_names_original"]
    col_names_orig = db["column_names_original"]
    col_types = db["column_types"]

    by_table = {i: [] for i in range(len(table_names_orig))}
    for idx, (tid, cname) in enumerate(col_names_orig):
        if tid == -1:  # skip global *
            continue
        by_table[tid].append((cname, col_types[idx]))

    parts = []
    for tid, tname in enumerate(table_names_orig):
        parts.append(f"# Table: {tname}")
        parts.append("[")
        for cname, ctype in by_table[tid]:
            parts.append(f"  ({cname}, type: {ctype}),")
        parts.append("]")
    return "\n".join(parts)


def build_fk_block(db):
    """Render all foreign keys for a DB."""
    col_names_orig = db["column_names_original"]
    table_names_orig = db["table_names_original"]
    lines = []
    for fk_from, fk_to in db["foreign_keys"]:
        child_tbl_id, child_col = col_names_orig[fk_from]
        parent_tbl_id, parent_col = col_names_orig[fk_to]
        if child_tbl_id < 0 or parent_tbl_id < 0:
            continue
        child_tbl_name = table_names_orig[child_tbl_id]
        parent_tbl_name = table_names_orig[parent_tbl_id]
        lines.append(f"{child_tbl_name}.`{child_col}` = {parent_tbl_name}.`{parent_col}`")
    return "\n".join(lines)


def build_question(parent_table, child_table):
    """Question pattern similar to the Spider bad case."""
    parent_phrase = parent_table.replace("_", " ")
    child_phrase = child_table.replace("_", " ")
    # Match the rough structure of the provided bad-case example
    return f"How many {parent_phrase} has more than 2 {child_phrase} ?"


def build_sql(db, parent_col_idx, child_col_idx):
    """Build the SQL pattern: count parents with > 2 children, using one FK."""
    col_names_orig = db["column_names_original"]
    table_names_orig = db["table_names_original"]

    parent_tbl_id, parent_col = col_names_orig[parent_col_idx]
    child_tbl_id, child_col = col_names_orig[child_col_idx]
    parent_tbl = table_names_orig[parent_tbl_id]
    child_tbl = table_names_orig[child_tbl_id]

    sql = (
        f"SELECT COUNT(*)\n"
        f"FROM {parent_tbl} AS t1\n"
        f"JOIN {child_tbl} AS t2 ON t1.`{parent_col}` = t2.`{child_col}`\n"
        f"GROUP BY t1.`{parent_col}`\n"
        f"HAVING COUNT(*) > 2;"
    )
    return sql


def build_schema_selection_answer(db, parent_table, child_table):
    """Create a selection JSON: keep/limit for parent & child, drop others."""
    table_names_orig = db["table_names_original"]
    col_names_orig = db["column_names_original"]

    by_table_cols = {t: [] for t in table_names_orig}
    for tid, cname in col_names_orig:
        if tid == -1:
            continue
        tname = table_names_orig[tid]
        by_table_cols[tname].append(cname)

    result = {}
    for tname in table_names_orig:
        cols = by_table_cols.get(tname, [])
        if tname == parent_table or tname == child_table:
            if len(cols) <= 10:
                result[tname] = "keep_all"
            else:
                result[tname] = cols[:6]  # top-6 by order
        else:
            result[tname] = "drop_all"
    return result


# ---------- Main generation ----------

def main():
    tables_data = json.loads(TABLES_PATH.read_text(encoding="utf-8"))

    db_by_id = {db["db_id"]: db for db in tables_data}

    # All distinct parent–child table pairs via FKs: (db_id, parent_table, child_table) -> (parent_col_idx, child_col_idx)
    pair_map = {}
    for db in tables_data:
        db_id = db["db_id"]
        col_names_orig = db["column_names_original"]
        table_names_orig = db["table_names_original"]
        for fk_from, fk_to in db["foreign_keys"]:
            child_tbl_id = col_names_orig[fk_from][0]
            parent_tbl_id = col_names_orig[fk_to][0]
            if child_tbl_id < 0 or parent_tbl_id < 0:
                continue
            key = (db_id, table_names_orig[parent_tbl_id], table_names_orig[child_tbl_id])
            if key not in pair_map:
                pair_map[key] = (fk_to, fk_from)

    print(f"Found {len(pair_map)} distinct parent–child table pairs")

    # Precompute schema & FK blocks for each DB
    schema_blocks = {}
    fk_blocks = {}
    for db_id, db in db_by_id.items():
        schema_blocks[db_id] = build_schema_block(db)
        fk_blocks[db_id] = build_fk_block(db)

    records = []
    idx_counter = 0

    # Build records: 2 per pair (schema-selection + SQL-generation)
    for (db_id, parent_table, child_table), (parent_col_idx, child_col_idx) in sorted(pair_map.items()):
        db = db_by_id[db_id]
        schema_block = schema_blocks[db_id]
        fk_block = fk_blocks[db_id]
        question = build_question(parent_table, child_table)
        sql = build_sql(db, parent_col_idx, child_col_idx)
        evidence = ""  # keep empty, like your example

        # 1) Schema-selection record
        user_content_sel = SCHEMA_SELECTION_USER_TEMPLATE.format(
            db_id=db_id,
            schema_block=schema_block,
            fk_block=fk_block,
            question=question,
            evidence=evidence,
        )
        selection_json = build_schema_selection_answer(db, parent_table, child_table)
        assistant_content_sel = "\n```json\n" + json.dumps(selection_json, indent=2) + "\n```\n"

        rec_sel = {
            "idx": idx_counter,
            "messages": [
                {"role": "system", "content": ""},
                {"role": "user", "content": user_content_sel},
                {"role": "assistant", "content": assistant_content_sel},
            ],
        }
        records.append(rec_sel)
        idx_counter += 1

        # 2) SQL-generation record
        user_content_sql = SQL_GENERATION_USER_TEMPLATE.format(
            schema_block=schema_block,
            fk_block=fk_block,
            question=question,
            evidence=evidence,
        )
        assistant_content_sql = (
            f"\nSub question 1: {question}\n"
            "SQL\n"
            "```sql\n"
            f"{sql}\n"
            "```\n"
            "Question Solved.\n"
        )

        rec_sql = {
            "idx": idx_counter,
            "messages": [
                {"role": "system", "content": ""},
                {"role": "user", "content": user_content_sql},
                {"role": "assistant", "content": assistant_content_sql},
            ],
        }
        records.append(rec_sql)
        idx_counter += 1

    # Write JSONL
    with OUT_PATH.open("w", encoding="utf-8") as f_out:
        for rec in records:
            f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Wrote {len(records)} records to {OUT_PATH}")


if __name__ == "__main__":
    main()
