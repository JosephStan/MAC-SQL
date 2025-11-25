import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import re
import sqlite3
import pandas as pd
import gradio as gr

from core.chat_manager import ChatManager
from core.const import SYSTEM_NAME

# --------------------------------------------------------
# Configuration for Datasets
# --------------------------------------------------------
DATASET_CONFIG = {
    "Spider": {
        "db_root": "./data/spider/database",
        "tables_json": "./data/spider/tables.json",
        "dataset_name": "spider"
    },
    "Bird (Dev)": {
        "db_root": "./data/bird/dev_databases",
        "tables_json": "./data/bird/dev_tables.json",
        "dataset_name": "bird"
    }
}

# Global instance holder
CURRENT_MANAGER = None

def get_manager(dataset_key="Spider"):
    """Lazy loader / re-initializer for ChatManager based on dataset"""
    global CURRENT_MANAGER
    config = DATASET_CONFIG.get(dataset_key, DATASET_CONFIG["Spider"])
    
    # Check if we need to re-init (if paths changed or first run)
    if CURRENT_MANAGER is None or CURRENT_MANAGER.dataset_name != config["dataset_name"]:
        print(f"Initializing ChatManager for {dataset_key}...")
        CURRENT_MANAGER = ChatManager(
            data_path=config["db_root"],
            tables_json_path=config["tables_json"],
            log_path=f"logs/macsql_{config['dataset_name']}.log",
            model_name="gpt-4o-mini",
            dataset_name=config["dataset_name"],
        )
    return CURRENT_MANAGER

def get_db_root(dataset_key):
    return DATASET_CONFIG.get(dataset_key, DATASET_CONFIG["Spider"])["db_root"]

# --------------------------------------------------------
# Helpers
# --------------------------------------------------------
def load_database_ids(dataset_key):
    db_root = get_db_root(dataset_key)
    if not os.path.exists(db_root):
        return []
    try:
        return sorted([
            name for name in os.listdir(db_root)
            if os.path.isdir(os.path.join(db_root, name))
        ])
    except Exception:
        return []

def execute_sql_on_db(dataset_key: str, db_id: str, sql: str):
    if not sql or "error" in sql.lower():
        return pd.DataFrame(), "No valid SQL generated."

    db_root = get_db_root(dataset_key)
    db_path = f"{db_root}/{db_id}/{db_id}.sqlite"
    
    if not os.path.exists(db_path):
        return pd.DataFrame(), f"Database not found: {db_path}"

    try:
        conn = sqlite3.connect(db_path)
        conn.text_factory = lambda b: b.decode(errors="ignore")
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return df.head(50), ""
    except Exception as e:
        return pd.DataFrame(), f"SQL execution error: {e}"

def load_table_data(dataset_key: str, db_id: str, table_name: str):
    if not table_name: return pd.DataFrame()
    db_root = get_db_root(dataset_key)
    db_path = f"{db_root}/{db_id}/{db_id}.sqlite"
    if not os.path.exists(db_path): return pd.DataFrame()
    
    try:
        conn = sqlite3.connect(db_path)
        conn.text_factory = lambda b: b.decode(errors="ignore")
        df = pd.read_sql_query(f"SELECT * FROM `{table_name}` LIMIT 50", conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame({"Error": [str(e)]})

def get_database_tables(dataset_key: str, db_id: str):
    db_root = get_db_root(dataset_key)
    db_path = f"{db_root}/{db_id}/{db_id}.sqlite"
    if not os.path.exists(db_path): return []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables
    except Exception:
        return []

# --------------------------------------------------------
# Parser Logic
# --------------------------------------------------------
def parse_decomposer_output(decomposer_obj):
    if isinstance(decomposer_obj, str):
        try: decomposer_obj = json.loads(decomposer_obj)
        except: return [], "", str(decomposer_obj)
    if not isinstance(decomposer_obj, dict): return [], "", str(decomposer_obj)

    qa = decomposer_obj.get("qa_pairs", "")
    if not isinstance(qa, str): return [], "", str(qa)

    lines = qa.split("\n")
    sub_questions = []
    # Regex to match "Sub question 1:", "Subquestion 1:", etc.
    subq_regex = re.compile(r'^Sub\s*question\s*\d+[:.]', re.IGNORECASE)
    current_q = None
    
    for line in lines:
        l = line.strip()
        if not l: continue
        if subq_regex.match(l):
            if current_q: sub_questions.append(current_q)
            current_q = l
        elif l.startswith("```sql") or (l.startswith("```") and "```sql" not in l):
             if current_q: current_q += f"\n{l}"
        else:
            if current_q: current_q += f"\n{l}"
    if current_q: sub_questions.append(current_q)

    sql_text = decomposer_obj.get('final_sql', '')
    return sub_questions, sql_text, qa

def check_sql_differences(decomposer_sql: str, refiner_sql: str, dataset_key: str, db_id: str) -> dict:
    result = {"had_errors": False, "error_message": "", "was_fixed": False, "fix_description": "", "decomposer_result": None, "refiner_result": None}
    
    # Test Decomposer
    d_df, d_err = execute_sql_on_db(dataset_key, db_id, decomposer_sql)
    result["decomposer_result"] = d_df
    if d_err:
        result["had_errors"] = True
        result["error_message"] = d_err
    
    # Test Refiner
    r_df, r_err = execute_sql_on_db(dataset_key, db_id, refiner_sql)
    result["refiner_result"] = r_df
    
    if result["had_errors"] and not r_err:
        result["was_fixed"] = True
        result["fix_description"] = "Refiner successfully fixed the SQL error"
    
    if not d_err and not r_err and decomposer_sql.strip() != refiner_sql.strip():
        d_count = len(d_df) if d_df is not None else 0
        r_count = len(r_df) if r_df is not None else 0
        if d_count != r_count:
            result["was_fixed"] = True
            result["fix_description"] = f"Refiner corrected logic ({d_count} rows → {r_count} rows)"
    
    return result

# --------------------------------------------------------
# Main Logic
# --------------------------------------------------------
def run_pipeline(dataset_key, db_id, question):
    manager = get_manager(dataset_key)
    message = {
        "db_id": db_id,
        "query": question,
        "evidence": "", # Evidence input not exposed in simple UI yet
        "extracted_schema": {},
        "idx": 0,
        "difficulty": "medium",
        "send_to": SYSTEM_NAME,
    }
    manager.start(message)
    
    # Extract outputs
    decomposer_raw = message.get("Decomposer_output", {})
    sub_questions, sql_from_qa, _ = parse_decomposer_output(decomposer_raw)
    
    return {
        "final_sql": message.get("pred", ""),
        "decomposer_sql": sql_from_qa or message.get("pred", ""),
        "sub_questions": sub_questions,
        "trace": json.dumps({k:v for k,v in message.items() if k.endswith("_output")}, indent=2, ensure_ascii=False),
        "schema": message.get("chosen_db_schem_dict", {})
    }

def on_submit(dataset_key, db_id, question, history):
    if not question.strip(): return history, "", pd.DataFrame(), "", "", "", "", ""
    if history is None: history = []

    res = run_pipeline(dataset_key, db_id, question)
    
    # Diff check
    diff = check_sql_differences(res["decomposer_sql"], res["final_sql"], dataset_key, db_id)
    
    # Execute Final
    df, err = execute_sql_on_db(dataset_key, db_id, res["final_sql"])
    
    # Chat Reply
    if err:
        reply = f"❌ SQL Error:\n```\n{err}\n```"
    else:
        count = len(df) if df is not None else 0
        reply = f"✅ Success! Found {count} rows.\nSample data shown in table."
        if diff["was_fixed"]: reply += f"\n\n**Note:** {diff['fix_description']}"

    history = history + [(question, reply)]
    
    # Comparison HTML
    if diff["was_fixed"]:
        comp_html = f"""<div style="padding:10px; background:#fff3cd; border-radius:5px;">
        <b>Original (Failed):</b><br><pre>{res['decomposer_sql']}</pre>
        <div style="text-align:center">⬇️ <i>Refined</i></div>
        <b>Fixed:</b><br><pre>{res['final_sql']}</pre>
        </div>"""
    elif res["decomposer_sql"].strip() != res["final_sql"].strip():
        comp_html = f"""<div style="padding:10px; background:#e2e3e5; border-radius:5px;">
        <b>Original:</b><br><pre>{res['decomposer_sql']}</pre>
        <div style="text-align:center">⬇️ <i>Optimized</i></div>
        <b>Final:</b><br><pre>{res['final_sql']}</pre>
        </div>"""
    else:
        comp_html = f"<div style='padding:10px; background:#d4edda; border-radius:5px;'><b>SQL Generated (No changes needed):</b><br><pre>{res['final_sql']}</pre></div>"

    # Text outputs
    decomp_text = "\n\n".join(res["sub_questions"]) if res["sub_questions"] else "No decomposition steps found."
    decomp_text += f"\n\n### Decomposer SQL\n```sql\n{res['decomposer_sql']}\n```"
    
    return history, comp_html, (df if df is not None else pd.DataFrame()), decomp_text, comp_html, json.dumps(res["schema"], indent=2), res["trace"]

# --------------------------------------------------------
# Event Handlers
# --------------------------------------------------------
def on_dataset_change(dataset_key):
    dbs = load_database_ids(dataset_key)
    new_db = dbs[0] if dbs else None
    tables = get_database_tables(dataset_key, new_db) if new_db else []
    new_table = tables[0] if tables else None
    
    # Return: DB Dropdown update, Table Dropdown update, Table Data clear
    return (
        gr.Dropdown(choices=dbs, value=new_db), 
        gr.Dropdown(choices=tables, value=new_table),
        pd.DataFrame()
    )

def on_db_change(dataset_key, db_id):
    tables = get_database_tables(dataset_key, db_id)
    new_table = tables[0] if tables else None
    return gr.Dropdown(choices=tables, value=new_table), pd.DataFrame()

def on_table_select(dataset_key, db_id, table_name):
    return load_table_data(dataset_key, db_id, table_name)

# --------------------------------------------------------
# UI
# --------------------------------------------------------
def main():
    css = """
    * { font-family: Arial, sans-serif !important; }
    .gradio-container { max-width: 95% !important; } 
    .result-table { height: 400px; overflow: auto; }
    pre { white-space: pre-wrap; }
    """
    with gr.Blocks(css=css, theme="soft", title="MAC-SQL") as demo:
        gr.Markdown("## MAC-SQL: Multi-Agent Text-to-SQL (Spider & Bird)")
        
        with gr.Row():
            ds_dd = gr.Dropdown(choices=list(DATASET_CONFIG.keys()), value="Spider", label="Dataset")
            db_dd = gr.Dropdown(choices=[], label="Database")
        
        with gr.Row():
            with gr.Column(scale=1):
                chatbot = gr.Chatbot(height=400)
                q_input = gr.Textbox(label="Question", placeholder="e.g. How many singers are there?")
                btn = gr.Button("Generate SQL", variant="primary")
            
            with gr.Column(scale=2):
                with gr.Tab("Result Table"):
                    res_df = gr.DataFrame(elem_classes=["result-table"])
                with gr.Tab("Browse Database"):
                    tb_dd = gr.Dropdown(label="Table", choices=[])
                    tb_df = gr.DataFrame(elem_classes=["result-table"])
                with gr.Tab("Agent Details"):
                    with gr.Accordion("Decomposition", open=True):
                        decomp_md = gr.Markdown()
                    with gr.Accordion("Refinement Comparison", open=True):
                        refine_html = gr.HTML()
                    with gr.Accordion("Schema Selected", open=False):
                        schema_box = gr.Textbox(lines=10)
                    with gr.Accordion("Raw Trace", open=False):
                        trace_box = gr.Textbox(lines=10)

        # Init
        demo.load(on_dataset_change, [ds_dd], [db_dd, tb_dd, tb_df])
        
        # Interaction
        ds_dd.change(on_dataset_change, [ds_dd], [db_dd, tb_dd, tb_df])
        db_dd.change(on_db_change, [ds_dd, db_dd], [tb_dd, tb_df])
        tb_dd.change(on_table_select, [ds_dd, db_dd, tb_dd], [tb_df])
        
        btn.click(on_submit, [ds_dd, db_dd, q_input, chatbot], [chatbot, refine_html, res_df, decomp_md, refine_html, schema_box, trace_box])
        q_input.submit(on_submit, [ds_dd, db_dd, q_input, chatbot], [chatbot, refine_html, res_df, decomp_md, refine_html, schema_box, trace_box])

    demo.launch()

if __name__ == "__main__":
    main()