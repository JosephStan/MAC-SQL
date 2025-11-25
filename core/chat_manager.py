# -*- coding: utf-8 -*-
from core.agents import Selector, Decomposer, Refiner
from core.const import MAX_ROUND, SYSTEM_NAME, SELECTOR_NAME, DECOMPOSER_NAME, REFINER_NAME

INIT_LOG__PATH_FUNC = None
LLM_API_FUC = None
try:
    from core import api
    LLM_API_FUC = api.safe_call_llm
    INIT_LOG__PATH_FUNC = api.init_log_path
    print(f"Use func from core.api in chat_manager.py")
except:
    from core import llm
    LLM_API_FUC = llm.safe_call_llm
    INIT_LOG__PATH_FUNC = llm.init_log_path
    print(f"Use func from core.llm in chat_manager.py")

import time
import re
from pprint import pprint


class ChatManager(object):
    def __init__(self, data_path: str, tables_json_path: str, log_path: str, model_name: str, dataset_name:str, lazy: bool=False, without_selector: bool=False):
        self.data_path = data_path  # root path to database dir, including all databases
        self.tables_json_path = tables_json_path # path to table description json file
        self.log_path = log_path  # path to record important printed content during running
        self.model_name = model_name  # name of base LLM called by agent
        self.dataset_name = dataset_name
        self.ping_network()
        self.chat_group = [
            Selector(data_path=self.data_path, tables_json_path=self.tables_json_path, model_name=self.model_name, dataset_name=dataset_name, lazy=lazy, without_selector=without_selector),
            Decomposer(dataset_name=dataset_name),
            Refiner(data_path=self.data_path, dataset_name=dataset_name)
        ]
        INIT_LOG__PATH_FUNC(log_path)

    def ping_network(self):
        # check network status
        print("Checking network status...", flush=True)
        try:
            _ = LLM_API_FUC("Hello world!")
            print("Network is available", flush=True)
        except Exception as e:
            raise Exception(f"Network is not available: {e}")

    def _chat_single_round(self, message: dict):
        # we use `dict` type so value can be changed in the function
                # agent.talk(message)
        for agent in self.chat_group:  # check each agent in the group
            if message['send_to'] == agent.name:
                print(f"\n=========== RUNNING {agent.name.upper()} ===========", flush=True)
                result = agent.talk(message)
                # Skip if the agent didn’t return anything
                if result is None:
                    result = message.copy()
                    
                message[f"{agent.name}_output"] = result

                if agent.name.lower() == "selector":
                    print(f"[Selector Output]")
                    print(f"  Database: {result.get('db_id', 'N/A')}")
                    print(f"  Question: {result.get('query', 'N/A')}")
                    print(f"  Evidence: {result.get('evidence', 'N/A')}")
                    print("Table Select:")
                    chosen = result.get("chosen_db_schem_dict", {})
                    if not chosen:
                        print("  (No tables selected or Drop All)")
                    else:
                        for table, cols in chosen.items():
                            # Join columns with comma
                            col_str = ", ".join(cols)
                            print(f"  {table}: {col_str}")
                    print("--------------------------------------------------\n")

                    # chosen = result.get("chosen_db_schem_dict", {})
                    # print(f"[Selector Output Summary]")
                    # print(f"Database: {result.get('db_id', 'unknown')}")
                    # print("Relevant tables and chosen columns:")
                    # for tname, cols in chosen.items():
                    #     print(f"  - {tname}: {cols}")
                    
                    # fk_str = result.get("fk_str", "")
                    # if fk_str:
                    #     print("\nForeign keys (unique):")
                    #     print(fk_str)

                elif agent.name.lower() == "decomposer":
                    print(f"[Decomposer → Refiner Message Flow]")
                    qa_pairs_raw = result.get('qa_pairs', '')
                    def clean_sql(txt):
                        txt = txt.replace("```sql", "").replace("```", "").strip()
                        return txt
                    lines = qa_pairs_raw.split('\n')
                    buffer_text = []
                    current_label = None
                    for line in lines:
                        line_strip = line.strip()
                        if line_strip.lower().startswith("sub question"):
                            if current_label:
                                # Print previous block
                                block_content = "\n".join(buffer_text)
                                print(f"{current_label}:")
                                # Try to find SQL in block
                                if "SELECT" in block_content.upper():
                                    # Extract SQL part vaguely or just print the block
                                    # Use regex to find code block if possible
                                    sql_match = re.search(r'```sql(.*?)```', block_content, re.DOTALL)
                                    if sql_match:
                                        print(f"SQL:\n{sql_match.group(1).strip()}")
                                    else:
                                        # Fallback: print lines that look like SQL
                                        print(f"SQL:\n{block_content.strip()}")
                                else:
                                    print(f"(Reasoning): {block_content.strip()}")
                            
                            current_label = line_strip.replace("Sub question", "Sub question").rstrip(":")
                            buffer_text = []
                        elif line_strip.lower().startswith("final sql"):
                            if current_label:
                                block_content = "\n".join(buffer_text)
                                print(f"{current_label}:")
                                sql_match = re.search(r'```sql(.*?)```', block_content, re.DOTALL)
                                if sql_match:
                                    print(f"SQL:\n{sql_match.group(1).strip()}")
                                else:
                                    print(f"SQL:\n{block_content.strip()}")
                            current_label = "Final SQL"
                            buffer_text = []
                        else:
                            buffer_text.append(line)
                    
                    # Print the last block (usually Final SQL)
                    if current_label == "Final SQL":
                         # Extract pure SQL from the final block or result['final_sql']
                         final_sql_clean = result.get('final_sql', '').strip()
                         print(f"Final SQL:\n{final_sql_clean}")

                    elif current_label:
                        block_content = "\n".join(buffer_text)
                        print(f"{current_label}:")
                        sql_match = re.search(r'```sql(.*?)```', block_content, re.DOTALL)
                        if sql_match:
                             print(f"SQL:\n{sql_match.group(1).strip()}")
                        else:
                             print(f"SQL:\n{block_content.strip()}")
                        
                        # Also print final SQL if not printed
                        if 'final_sql' in result and result['final_sql']:
                            print(f"Final SQL:\n{result['final_sql']}")
                    else:
                        # Fallback if parsing failed (e.g. one-shot without subquestions)
                        print(f"Final SQL:\n{result.get('final_sql', 'N/A')}")

                    print("--------------------------------------------------\n")
                    # print(f"[Decomposer Output Summary]")
                    # summary = result.get("summary", {})
                    # if summary:
                    #     sql = summary.get("decomposer_sql", result.get("final_sql", "N/A"))
                    #     subqs = summary.get("sub_questions", result.get("sub_questions", []))
                    # else:
                    #     sql = result.get("final_sql", "N/A")
                    #     # fall back to qa_pairs or sub_questions
                    #     subqs = result.get("sub_questions", [])
                    #     if not subqs:
                    #         qa_pairs = result.get("qa_pairs", "")
                    #         # break qa_pairs by line or numbering
                    #         if isinstance(qa_pairs, str):
                    #             lines = [line.strip() for line in qa_pairs.split("\n") if line.strip()]
                    #             subqs = []
                    #             inside_sql_block = False
                    #             for line in lines:
                    #                 if line.startswith("```sql"):
                    #                     inside_sql_block = True
                    #                     continue
                    #                 elif line.startswith("```") and inside_sql_block:
                    #                     inside_sql_block = False
                    #                     continue
                    #                 if not inside_sql_block and not line.startswith("```"):
                    #                     subqs.append(line)
                    # subqs = [
                    #     sq for sq in subqs if sq.strip() and not sq.strip().lower().startswith("sql")
                    # ]

                    # print(f"Generated SQL: {sql}")
                    # print(f"Number of sub-questions: {len(subqs)}")
                    # if subqs:
                    #     print("\nSub-questions:")
                    #     for i, sq in enumerate(subqs, 1):
                    #         print(f"  {i}. {sq}")

                    # print("")

                elif agent.name.lower() == "refiner":
                    # print(f"[Refiner Output Summary]")
                    print(f"[Refiner Output]")
                    
                    fixed = result.get('fixed', False)
                    print(f"Need Fixed: {fixed}")
                    if fixed:
                        print(f"Error: {result.get('error_detail', 'Check trace for specific SQLite error')}") 
                        print(f"Fixed Time: {result.get('try_times', 1)}")
                    else:
                        print(f"Fixed Time: {result.get('try_times', 1)}")

                    print(f"Final SQL:\n{result.get('pred', result.get('final_sql', ''))}")
                    print("--------------------------------------------------\n")

                    # Extract fields safely
                #     original_sql = result.get("final_sql", "N/A")
                #     final_sql = result.get("pred",result.get("final_sql", "N/A"))
                #     fixed = result.get("fixed", False)
                #     try_times = result.get("try_times", 1)
                #     error_detail = result.get("error_detail", "")
                #     reason = result.get("reason", "")

                #     print(f"Original SQL: {original_sql}")
                #     print(f"Final SQL: {final_sql}")
                #     print(f"Fixed: {fixed}")
                #     print(f"Try times: {try_times}")

                #     if error_detail:
                #         print(f"Error detail: {error_detail}")
                #     if reason:
                #         print(f"Reason: {reason}")

                #     print("")  # spacing

                    
                # print(f"=========== FINISHED {agent.name.upper()} ===========\n", flush=True)
            
        return message

    def start(self, user_message: dict):
        # we use `dict` type so value can be changed in the function
        start_time = time.time()
        if user_message['send_to'] == SYSTEM_NAME:  # in the first round, pass message to prune
            user_message['send_to'] = SELECTOR_NAME
        for i in range(MAX_ROUND):  # start chat in group
            self._chat_single_round(user_message)
            if user_message['send_to'] == SYSTEM_NAME:  # should terminate chat
                print(f"\nTask finished in {i+1} rounds.")
                break
        end_time = time.time()
        exec_time = end_time - start_time
        print(f"\033[0;34mExecute {exec_time} seconds\033[0m", flush=True)


if __name__ == "__main__":
    test_manager = ChatManager(data_path="../data/spider/database",
                               log_path="",
                               model_name='gpt-4-32k',
                               dataset_name='spider',
                               lazy=True)
    msg = {
        'db_id': 'concert_singer',
        'query': 'How many singers do we have?',
        'evidence': '',
        'extracted_schema': {},
        'ground_truth': 'SELECT count(*) FROM singer',
        'difficulty': 'easy',
        'send_to': SYSTEM_NAME
    }
    test_manager.start(msg)
    pprint(msg)
    print(msg['pred'])