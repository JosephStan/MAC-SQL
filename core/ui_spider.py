# core/ui.py
# --------------------------------------------------------
# MAC-SQL Graphical Interface (Watson-style)
# --------------------------------------------------------

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import sqlite3
import pandas as pd
import gradio as gr

from core.chat_manager import ChatManager
from core.const import SYSTEM_NAME


# --------------------------------------------------------
# Helpers: load DB list
# --------------------------------------------------------
def load_database_ids(db_root="./data/spider/database"):
    try:
        return sorted([
            name for name in os.listdir(db_root)
            if os.path.isdir(os.path.join(db_root, name))
        ])
    except Exception:
        return []


DB_LIST = load_database_ids()


# --------------------------------------------------------
# Init ChatManager once
# --------------------------------------------------------
chat_manager = ChatManager(
    data_path="./data/spider/database",
    tables_json_path="./data/spider/tables.json",
    log_path="logs/macsql.log",
    model_name="gpt-4o-mini",
    dataset_name="spider",
)

# --------------------------------------------------------
# SQL execution helper (center table)
# --------------------------------------------------------
def execute_sql_on_db(db_id: str, sql: str):
    """
    Execute SQL against the Spider SQLite DB and return (DataFrame, error_msg).
    """
    if not sql or "error" in sql.lower():
        return pd.DataFrame(), "No valid SQL generated."

    db_path = f"./data/spider/database/{db_id}/{db_id}.sqlite"
    if not os.path.exists(db_path):
        return pd.DataFrame(), f"Database not found: {db_path}"

    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return df.head(50), ""  # limit rows for display
    except Exception as e:
        return pd.DataFrame(), f"SQL execution error: {e}"


# --------------------------------------------------------
# Get all tables from database
# --------------------------------------------------------
def get_database_tables(db_id: str):
    """Get list of all tables in the database"""
    db_path = f"./data/spider/database/{db_id}/{db_id}.sqlite"
    if not os.path.exists(db_path):
        return []
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables
    except Exception:
        return []


def load_table_data(db_id: str, table_name: str):
    """Load data from a specific table"""
    if not table_name:
        return pd.DataFrame()
    
    db_path = f"./data/spider/database/{db_id}/{db_id}.sqlite"
    if not os.path.exists(db_path):
        return pd.DataFrame()
    
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(f"SELECT * FROM {table_name} LIMIT 100", conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame({"Error": [str(e)]})


# --------------------------------------------------------
# Decomposer parsing helper
# --------------------------------------------------------
def parse_decomposer_output(decomposer_obj):
    """
    Returns (sub_questions: List[str], sql_text: str, raw_qa: str)
    from the Decomposer_output dict (or string).
    """
    # handle string -> dict if needed
    if isinstance(decomposer_obj, str):
        try:
            decomposer_obj = json.loads(decomposer_obj)
        except Exception:
            return [], "", decomposer_obj

    if not isinstance(decomposer_obj, dict):
        return [], "", str(decomposer_obj)

    qa = decomposer_obj.get("qa_pairs", "")
    if not isinstance(qa, str):
        return [], "", str(qa)

    lines = qa.split("\n")
    sub_questions = []
    sql_lines = []
    inside_sql = False

    for line in lines:
        l = line.strip()

        # capture "Sub question ..." lines
        if l.lower().startswith("sub question"):
            # Normalize label: "Subquestion X: ..."
            if ":" in l:
                label, rest = l.split(":", 1)
                sub_questions.append(f"Subquestion{label[len('Sub question'):]}:{rest}")
            else:
                sub_questions.append(l.replace("Sub question", "Subquestion"))
            continue

        # detect ```sql block
        if l.startswith("```sql"):
            inside_sql = True
            continue
        if inside_sql and l.startswith("```"):
            inside_sql = False
            continue

        if inside_sql:
            sql_lines.append(line)

    sql_text = "\n".join(sql_lines).strip()
    return sub_questions, sql_text, qa


def check_sql_differences(decomposer_sql: str, refiner_sql: str, db_id: str) -> dict:
    """
    Check if Refiner fixed any errors from Decomposer.
    Returns dict with: had_errors, error_message, was_fixed, fix_description
    """
    result = {
        "had_errors": False,
        "error_message": "",
        "was_fixed": False,
        "fix_description": "",
        "decomposer_result": None,
        "refiner_result": None
    }
    
    # Test Decomposer SQL
    decomposer_df, decomposer_error = execute_sql_on_db(db_id, decomposer_sql)
    result["decomposer_result"] = decomposer_df
    
    if decomposer_error:
        result["had_errors"] = True
        result["error_message"] = decomposer_error
    
    # Test Refiner SQL
    refiner_df, refiner_error = execute_sql_on_db(db_id, refiner_sql)
    result["refiner_result"] = refiner_df
    
    # Check if Refiner fixed the error
    if result["had_errors"] and not refiner_error:
        result["was_fixed"] = True
        result["fix_description"] = "Refiner successfully fixed the SQL error"
    
    # Check if results are different (logic fix, not syntax)
    if not decomposer_error and not refiner_error:
        if decomposer_sql.strip() != refiner_sql.strip():
            # SQLs are different but both work - check results
            decomposer_count = len(decomposer_df) if decomposer_df is not None else 0
            refiner_count = len(refiner_df) if refiner_df is not None else 0
            
            if decomposer_count != refiner_count:
                result["was_fixed"] = True
                result["fix_description"] = f"Refiner corrected the logic (Decomposer: {decomposer_count} rows → Refiner: {refiner_count} rows)"
    
    return result


# --------------------------------------------------------
# Core pipeline: call ChatManager once per message
# --------------------------------------------------------
def run_pipeline(db_id: str, question: str, evidence: str):
    """
    Runs Selector → Decomposer → Refiner via ChatManager.
    Returns a dict with all useful pieces for the UI.
    """
    message = {
        "db_id": db_id,
        "query": question,
        "evidence": evidence,
        "extracted_schema": {},
        "idx": 0,
        "difficulty": "medium",
        "send_to": SYSTEM_NAME,
    }

    chat_manager.start(message)

    final_sql = message.get("pred", "")
    chosen_schema = message.get("chosen_db_schem_dict", {})

    # raw agent outputs stored by ChatManager
    selector_raw = message.get("Selector_output", {})
    decomposer_raw = message.get("Decomposer_output", {})
    refiner_raw = message.get("Refiner_output", {})

    # parse decomposer into sub questions + SQL
    sub_questions, sql_from_qa, qa_raw = parse_decomposer_output(decomposer_raw)
    if not sql_from_qa and final_sql:
        sql_from_qa = final_sql

    # Extract decomposer SQL
    decomposer_sql = sql_from_qa or "(No SQL generated by Decomposer)"
    
    # Extract refiner SQL
    refiner_sql = final_sql or "(No SQL generated by Refiner)"

    # build full raw trace
    def pretty(v):
        if isinstance(v, (dict, list)):
            return json.dumps(v, indent=2, ensure_ascii=False)
        return str(v)

    trace_str = ""
    for k, v in message.items():
        if k.endswith("_output"):
            trace_str += f"\n================ {k} ================\n"
            trace_str += pretty(v) + "\n"

    return {
        "final_sql": final_sql,
        "sql_from_qa": sql_from_qa,
        "decomposer_sql": decomposer_sql,
        "refiner_sql": refiner_sql,
        "selector_raw": selector_raw,
        "decomposer_raw": decomposer_raw,
        "refiner_raw": refiner_raw,
        "sub_questions": sub_questions,
        "qa_raw": qa_raw,
        "chosen_schema": chosen_schema,
        "trace": trace_str,
    }


# --------------------------------------------------------
# Chat submit handler (Option C + SQL execution)
# --------------------------------------------------------
def on_chat_submit(db_id, user_message, history):
    if history is None:
        history = []

    user_message = (user_message or "").strip()
    if not user_message:
        # nothing typed
        empty_df = pd.DataFrame()
        return history, "", empty_df, "", "", "", "", "", history

    # ---- 1. Run MAC-SQL pipeline ----
    result = run_pipeline(db_id, user_message, evidence="")

    final_sql = result["refiner_sql"]
    decomposer_sql = result["decomposer_sql"]
    sub_questions = result["sub_questions"]
    trace_str = result["trace"]
    schema_dict = result["chosen_schema"]

    # ---- 2. Check if Refiner fixed errors ----
    diff_result = check_sql_differences(decomposer_sql, final_sql, db_id)

    # ---- 3. Execute SQL & build chat reply ----
    df, sql_error = execute_sql_on_db(db_id, final_sql)

    if sql_error:
        chat_reply = (
            "I tried to generate and run a SQL query, but hit an issue:\n"
            f"```text\n{sql_error}\n```\n"
            "You can inspect the SQL in the **Refiner SQL** tab and the raw trace in **Full Trace**."
        )
    else:
        if df is not None and not df.empty:
            first_row = df.iloc[0]
            snippet = ", ".join(f"{col} = {first_row[col]}" for col in df.columns[:3])  # first 3 cols
            chat_reply = (
                "Here is what I found from the database:\n\n"
                f"**Sample:** {snippet}...\n\n"
                "The full result is shown in the center table. "
                "You can also see how I decomposed the question on the right."
            )
            
            # Add note if Refiner fixed something
            if diff_result["was_fixed"]:
                chat_reply += f"\n\n **Note:** {diff_result['fix_description']}"
        else:
            chat_reply = (
                "The SQL ran successfully, but returned **0 rows**. "
                "You may want to adjust the question or inspect the SQL / schema "
                "on the right."
            )

    history = history + [(user_message, chat_reply)]

    # ---- 4. Explanation (right → Explanation tab) ----
    if sub_questions:
        explanation = "### Question\n"
        explanation += user_message + "\n\n"
        explanation += "### How I reasoned\n"
        for i, sq in enumerate(sub_questions, 1):
            explanation += f"{i}. {sq}\n"
        if sql_error:
            explanation += f"\n *SQL execution warning:* {sql_error}\n"
    else:
        explanation = (
            "No explicit decomposition text was returned by the Decomposer.\n"
            "You can still inspect the SQL and raw trace in the other tabs."
        )

    # ---- 5. Decomposition tab content (with Decomposer SQL) ----
    if sub_questions:
        decomposition_text = "### Decomposed Subquestions\n\n"
        for i, sq in enumerate(sub_questions, 1):
            decomposition_text += f"{i}. {sq}\n"
        decomposition_text += f"\n### Decomposer SQL\n```sql\n{decomposer_sql}\n```"
    else:
        decomposition_text = f"(No subquestions were extracted from qa_pairs.)\n\n### Decomposer SQL\n```sql\n{decomposer_sql}\n```"

    # ---- 6. Refiner SQL tab - COMPARISON VIEW (方案 A) ----
    if diff_result["was_fixed"]:
        # Show Before/After comparison with better formatting
        refiner_comparison = f"""<div style="padding: 10px;">

###  SQL Refinement Process

<div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 10px 0; border-radius: 5px;">

####  Step 1: Decomposer SQL (Initial)

```sql
{decomposer_sql}
```

<p style="color: #856404; margin-top: 10px;">
<b>Issue Detected:</b> {diff_result['error_message'] if diff_result['error_message'] else 'Logic error or incomplete query'}
</p>

</div>

<div style="text-align: center; margin: 20px 0;">
<span style="font-size: 24px;"></span><br/>
<b>Refiner Processing...</b>
</div>

<div style="background-color: #d4edda; border-left: 4px solid #28a745; padding: 15px; margin: 10px 0; border-radius: 5px;">

####  Step 2: Refiner SQL (Corrected)

```sql
{final_sql}
```

<p style="color: #155724; margin-top: 10px;">
<b>What was Fixed:</b> {diff_result['fix_description']}
</p>

</div>

---

###  Execution Results Comparison

<table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
<tr style="background-color: #f8f9fa;">
    <th style="padding: 12px; text-align: left; border: 1px solid #dee2e6;">Stage</th>
    <th style="padding: 12px; text-align: left; border: 1px solid #dee2e6;">Result</th>
    <th style="padding: 12px; text-align: left; border: 1px solid #dee2e6;">Status</th>
</tr>
<tr>
    <td style="padding: 10px; border: 1px solid #dee2e6;">Decomposer</td>
    <td style="padding: 10px; border: 1px solid #dee2e6; font-family: monospace;">{diff_result['error_message'] if diff_result['had_errors'] else f"{len(diff_result['decomposer_result'])} rows" if diff_result['decomposer_result'] is not None else "N/A"}</td>
    <td style="padding: 10px; border: 1px solid #dee2e6;"> Failed</td>
</tr>
<tr style="background-color: #d4edda;">
    <td style="padding: 10px; border: 1px solid #dee2e6;">Refiner</td>
    <td style="padding: 10px; border: 1px solid #dee2e6; font-family: monospace;">{len(diff_result['refiner_result'])} rows</td>
    <td style="padding: 10px; border: 1px solid #dee2e6;"> Success</td>
</tr>
</table>

</div>"""
    else:
        # No fix needed or same SQL
        if decomposer_sql.strip() == final_sql.strip():
            refiner_comparison = f"""<div style="padding: 10px;">

<div style="background-color: #d4edda; border-left: 4px solid #28a745; padding: 20px; margin: 10px 0; border-radius: 5px;">

###  SQL Generation Successful (No Refinement Needed)

```sql
{final_sql}
```

<p style="color: #155724; margin-top: 15px;">
<b>Status:</b> Decomposer generated correct SQL on the first try. No refinement needed! 🎉
</p>

</div>

</div>"""
        else:
            refiner_comparison = f"""<div style="padding: 10px;">

<div style="background-color: #d1ecf1; border-left: 4px solid #17a2b8; padding: 15px; margin: 10px 0; border-radius: 5px;">

####  Decomposer SQL (Original)

```sql
{decomposer_sql}
```

</div>

<div style="text-align: center; margin: 15px 0;">
<span style="font-size: 20px;"></span><br/>
<span style="color: #666;">Minor adjustments...</span>
</div>

<div style="background-color: #d4edda; border-left: 4px solid #28a745; padding: 15px; margin: 10px 0; border-radius: 5px;">

#### Refiner SQL (Optimized)

```sql
{final_sql}
```

<p style="color: #155724; margin-top: 10px;">
<b>Note:</b> Minor optimization or formatting changes from Decomposer.
</p>

</div>

</div>"""

    # ---- 7. Schema (right → Schema tab) ----
    schema_pretty = json.dumps(schema_dict, indent=2, ensure_ascii=False) if schema_dict else ""

    # ---- 8. Full Trace (bottom right) ----
    debug_text = result["trace"]

    # Center table DataFrame
    table_df = df if (df is not None) else pd.DataFrame()

    return history, refiner_comparison, table_df, explanation, decomposition_text, refiner_comparison, schema_pretty, debug_text, history


# --------------------------------------------------------
# Handle database change - update table list
# --------------------------------------------------------
def on_db_change(db_id):
    tables = get_database_tables(db_id)
    return gr.Dropdown(choices=tables, value=tables[0] if tables else None)


# --------------------------------------------------------
# Handle table selection - load table data
# --------------------------------------------------------
def on_table_select(db_id, table_name):
    return load_table_data(db_id, table_name)


# --------------------------------------------------------
# UI Layout (Watson-style)
# --------------------------------------------------------
def main():
    custom_css = """
    * { font-family: Arial, sans-serif !important; }
    body { background-color: #101216; }
    .gradio-container { max-width: 1600px !important; margin: auto; }
    .chatbot { height: 400px; }
    /chatbot .user-message { font-size: 12px !important; }    /* 用户消息 */
    .chatbot .bot-message { font-size: 12px !important; }     /* AI 回复 */
    .chatbot p { font-size: 12px !important; }                /* 所有段落 */
    .result-table { height: 350px; overflow-y: auto; }
    .tab-content { height: 400px; overflow-y: auto; }
    .schema-box { max-height: 350px; overflow-y: scroll !important; overflow-x: auto !important; white-space: pre-wrap; }
    .trace-box { max-height: 300px; overflow-y: scroll !important; overflow-x: auto !important; white-space: pre-wrap; }
    .refiner-content { height: 500px; overflow-y: auto; }
    """

    with gr.Blocks(css=custom_css, theme="soft") as demo:
        gr.Markdown("## MAC-SQL – a multi-agent Text-to-SQL Assistant")

        with gr.Row():
            db_id = gr.Dropdown(
                DB_LIST,
                label="Database",
                value="car_1" if "car_1" in DB_LIST else (DB_LIST[0] if DB_LIST else None),
                interactive=True,
            )

        # Shared state for chat history
        chat_state = gr.State([])

        with gr.Row():
            # -------- Left: Chat --------
            with gr.Column(scale=2):
                chatbot = gr.Chatbot(
                    label="Conversation",
                    height=300,
                    avatar_images=(None, None),
                )
                user_box = gr.Textbox(
                    label="Ask a question about the selected database",
                    placeholder="e.g., Which country has the most car model makers?",
                    lines=2,
                )
                send_btn = gr.Button("Send", variant="primary")

            # -------- Middle: Tables --------
            with gr.Column(scale=3):
                with gr.Tab("Query Result"):
                    result_table = gr.DataFrame(
                        label="SQL Query Result",
                        interactive=False,
                        wrap=False,
                        column_widths=["auto"],
                        elem_classes=["result-table"]
                    )
                with gr.Tab("Database Tables"):
                    table_selector = gr.Dropdown(
                        label="Select Table to View",
                        choices=[],
                        interactive=True
                    )
                    table_data = gr.DataFrame(
                        label="Table Content (drag column borders to resize)",
                        interactive=False,
                        wrap=False,
                        column_widths=["auto"],
                        elem_classes=["result-table"]
                    )

            # -------- Right: Tabs --------
            with gr.Column(scale=3):
                with gr.Tab("Explanation"):
                    explanation_md = gr.Markdown(elem_classes=["tab-content"])
                with gr.Tab("Decomposition"):
                    decomposition_md = gr.Markdown(elem_classes=["tab-content"])
                with gr.Tab("Refiner SQL"):
                    refiner_sql_md = gr.Markdown(
                        label="SQL Refinement Process",
                        elem_classes=["refiner-content"]
                    )
                with gr.Tab("Schema"):
                    schema_box = gr.Textbox(
                        label="Detected Relevant Schema (from Selector)",
                        lines=12,
                        max_lines=12,
                        elem_classes=["schema-box"]
                    )
                
                # Move Full Trace here (right side, below tabs)
                with gr.Accordion("Full Agent Trace (Debug)", open=False):
                    trace_box = gr.Textbox(
                        label="Raw JSON output from all agents",
                        lines=12,
                        max_lines=12,
                        elem_classes=["trace-box"]
                    )
        
        # Initialize table selector when page loads
        demo.load(
            on_db_change,
            inputs=[db_id],
            outputs=[table_selector]
        )
        
        # Wire database change to update table selector
        db_id.change(
            on_db_change,
            inputs=[db_id],
            outputs=[table_selector]
        )
        
        # Wire table selection to load data
        table_selector.change(
            on_table_select,
            inputs=[db_id, table_selector],
            outputs=[table_data]
        )

        # Wire send button + Enter key
        inputs = [db_id, user_box, chat_state]
        outputs = [
            chatbot,         # updated chat history (UI)
            refiner_sql_md,  # refiner SQL markdown (duplicate for tab)
            result_table,    # center table
            explanation_md,  # Explanation tab
            decomposition_md,# Decomposition tab (with decomposer SQL)
            refiner_sql_md,  # Refiner SQL tab (comparison view)
            schema_box,      # Schema tab
            trace_box,       # Full trace (bottom)
            chat_state,      # updated state
        ]

        send_btn.click(on_chat_submit, inputs=inputs, outputs=outputs)
        user_box.submit(on_chat_submit, inputs=inputs, outputs=outputs)

    demo.launch()


if __name__ == "__main__":
    main()