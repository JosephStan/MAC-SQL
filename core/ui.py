import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import re
import sqlite3
import pandas as pd
import gradio as gr

from core.chat_manager import ChatManager
from core.const import SYSTEM_NAME

# Configuration for Datasets
DATASET_CONFIG = {
    "Spider": {
        "db_root": "./data/spider/database",
        "tables_json": "./data/spider/tables.json",
        "dataset_name": "spider"
    },
    "Bird": {
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
            model_name="gpt-4.1-nano",
            dataset_name=config["dataset_name"],
        )
    return CURRENT_MANAGER

def get_db_root(dataset_key):
    return DATASET_CONFIG.get(dataset_key, DATASET_CONFIG["Spider"])["db_root"]

# Helpers

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

# New Formatter for Selector

def format_selector_html(schema_dict):
    if not schema_dict:
        return "<i>No specific schema selected (or Drop All).</i>"
    
    html = "<div style='display:flex; flex-wrap:wrap; gap:10px;'>"
    for table, cols in schema_dict.items():
        # Handle cases where cols might be a string (e.g., "drop_all")
        if isinstance(cols, list):
            col_badges = "".join([f"<span style='background:#e0f2fe; color:#0369a1; padding:2px 6px; border-radius:4px; font-size:12px; margin:2px; display:inline-block;'>{c}</span>" for c in cols])
        else:
            col_badges = f"<span>{str(cols)}</span>"

        html += f"""
        <div style='border:1px solid #e5e7eb; border-radius:8px; padding:10px; width:300px; background:white; box-shadow:0 1px 2px rgba(0,0,0,0.05);'>
            <div style='font-weight:bold; color:#374151; border-bottom:1px solid #eee; padding-bottom:5px; margin-bottom:5px;'> {table}</div>
            <div>{col_badges}</div>
        </div>
        """
    html += "</div>"
    return html

# Parser Logic

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

# Main Logic

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
        reply = f"SQL Error:\n```\n{err}\n```"
    else:
        count = len(df) if df is not None else 0
        reply = f"Success! Found {count} rows.\nSample data shown in table."
        if diff["was_fixed"]: reply += f"\n\n**Note:** {diff['fix_description']}"

    history = history + [(question, reply)]
    
    # Comparison HTML
    if diff["was_fixed"]:
        comp_md = (
            "#### Original SQL (from Decomposer)\n"
            f"```sql\n{res['decomposer_sql']}\n```\n"
            f" **Error detected:**\n> {diff['error_message']}\n\n"
            " *Refined SQL*\n"
            f"```sql\n{res['final_sql']}\n```"
        )
    elif diff["had_errors"]:
        # Case: Decomposer failed, and Refiner likely failed too or didn't change it enough
        comp_md = (
            "#### Original SQL\n"
            f"```sql\n{res['decomposer_sql']}\n```\n"
            f" **Error:** {diff['error_message']}\n\n"
            " *Final SQL*\n"
            f"```sql\n{res['final_sql']}\n```"
        )
    elif res["decomposer_sql"].strip() != res["final_sql"].strip():
        comp_md = (
            "#### Original SQL\n"
            f"```sql\n{res['decomposer_sql']}\n```\n"
            " *Final SQL*\n"
            f"```sql\n{res['final_sql']}\n```"
    )
    else:
        comp_md = (
            "```sql\n"
            f"{res['final_sql']}\n"
            "```"
        )
    # Text outputs
    decomp_text = "\n\n".join(res["sub_questions"]) if res["sub_questions"] else "No decomposition steps found."

    # 1. Pretty Selector Format
    selector_html = format_selector_html(res["schema"])
    
    return (
        history, 
        comp_md, 
        (df if df is not None else pd.DataFrame()),
        decomp_text, 
        selector_html, 
        res["trace"]
    )


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
    .result-table { height: 500px !important; overflow-y: auto !important; }
    .trace-box { height: 500px !important; overflow-y: scroll !important; }
    pre { white-space: pre-wrap; }
    
    /* Stronger selector to force font size change */
    .small-chat .prose, 
    .small-chat .prose p, 
    .small-chat .message,
    .small-chat span { 
        font-size: 13px !important; 
    }
    """
    with gr.Blocks(css=css, theme="soft", title="MAC-SQL") as demo:
        gr.Markdown("## MAC-SQL: Multi-Agent Text-to-SQL (Spider & Bird)")
        
        with gr.Row():
            ds_dd = gr.Dropdown(choices=list(DATASET_CONFIG.keys()), value="Spider", label="Dataset")
            db_dd = gr.Dropdown(choices=[], label="Database")
        
        with gr.Row():
            with gr.Column(scale=1):
                chatbot = gr.Chatbot(height=400,elem_classes=["small-chat"])
                q_input = gr.Textbox(label="Question", placeholder="e.g. How many singers are there?")
                btn = gr.Button("Generate SQL", variant="primary")
            
            with gr.Column(scale=2):
                with gr.Tab("Result Table"):
                    res_df = gr.DataFrame(
                        elem_classes=["result-table"],
                        wrap=True,
                        max_height=400
                    )

                with gr.Tab("Browse Database"):
                    tb_dd = gr.Dropdown(label="Table", choices=[])
                    tb_df = gr.DataFrame(
                        elem_classes=["result-table"],
                        wrap=True,
                        max_height=400
                    )
                with gr.Tab("Agent Details"):
                    with gr.Accordion("Selector", open=False):
                        # 1. Changed to HTML for pretty format
                        schema_box = gr.HTML()
                    with gr.Accordion("Decomposer", open=True):
                        # 2. Changed to Markdown for formating
                        decomp_md = gr.Markdown()
                    with gr.Accordion("Refiner", open=True):
                         # Refiner now uses Markdown (text)
                        refine_html = gr.Markdown()
                    with gr.Accordion("Raw Trace", open=False):
                        # 3. Changed to Code for scrolling and JSON highlighting
                        trace_box = gr.Code(language="json", elem_classes=["trace-box"])

        # Init
        demo.load(on_dataset_change, [ds_dd], [db_dd, tb_dd, tb_df])
        
        # Interaction
        ds_dd.change(on_dataset_change, [ds_dd], [db_dd, tb_dd, tb_df])
        db_dd.change(on_db_change, [ds_dd, db_dd], [tb_dd, tb_df])
        tb_dd.change(on_table_select, [ds_dd, db_dd, tb_dd], [tb_df])
        
        # FIX: Removed the duplicate 'refine_html' from the output list.
        # Original (Error): [chatbot, refine_html, res_df, decomp_md, refine_html, schema_box, trace_box]
        # Fixed:            [chatbot, refine_html, res_df, decomp_md, schema_box, trace_box]
        
        outputs = [chatbot, refine_html, res_df, decomp_md, schema_box, trace_box]

        btn.click(on_submit, [ds_dd, db_dd, q_input, chatbot], outputs)
        q_input.submit(on_submit, [ds_dd, db_dd, q_input, chatbot], outputs)

    demo.launch()

if __name__ == "__main__":
    main()