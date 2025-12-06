import os, sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../MACSQL
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# -*- coding: utf-8 -*-
from core.utils import parse_json, parse_sql_from_string, add_prefix, load_json_file, extract_world_info, is_email, is_valid_date_column
from func_timeout import func_set_timeout, FunctionTimedOut
from core.const import *
from typing import List
from copy import deepcopy
import sqlite3
import time
import abc
import sys
import os
import re
import json  # Added for robust parsing
import pandas as pd
from tqdm import trange

LLM_API_FUC = None
try:
    from core import api
    LLM_API_FUC = api.safe_call_llm
    print(f"Use func from core.api in agents.py")
except:
    from core import llm
    LLM_API_FUC = llm.safe_call_llm
    print(f"Use func from core.llm in agents.py")

class BaseAgent(metaclass=abc.ABCMeta):
    def __init__(self):
        pass

    @abc.abstractmethod
    def talk(self, message: dict):
        pass

class Selector(BaseAgent):
    name = SELECTOR_NAME
    description = "Get database description and if need, extract relative tables & columns"

    def __init__(
        self,
        data_path: str,
        tables_json_path: str,
        model_name: str,
        dataset_name: str,
        lazy: bool = False,
        without_selector: bool = False
    ):
        super().__init__()
        self.data_path = data_path.strip("/").strip("\\")
        self.tables_json_path = tables_json_path
        self.model_name = model_name
        self.dataset_name = dataset_name
        self.db2infos = {}
        self.db2dbjsons = {}
        self.init_db2jsons()
        if not lazy:
            self._load_all_db_info()
        self._message = {}
        self.without_selector = without_selector

    def init_db2jsons(self):
        if not os.path.exists(self.tables_json_path):
            raise FileNotFoundError(f"tables.json not found in {self.tables_json_path}")
        data = load_json_file(self.tables_json_path)
        for item in data:
            db_id = item["db_id"]
            table_names = item["table_names"]
            item["table_count"] = len(table_names)
            column_count_lst = [0] * len(table_names)
            for tb_idx, col in item["column_names"]:
                if tb_idx >= 0:
                    column_count_lst[tb_idx] += 1
            item["max_column_count"] = max(column_count_lst) if column_count_lst else 0
            item["total_column_count"] = sum(column_count_lst)
            item["avg_column_count"] = (sum(column_count_lst) // len(table_names)) if table_names else 0
            self.db2dbjsons[db_id] = item

    def _get_column_attributes(self, cursor, table):
        cursor.execute(f"PRAGMA table_info(`{table}`)")
        columns = cursor.fetchall()
        column_names = []
        column_types = []
        for column in columns:
            column_names.append(column[1])
            column_types.append(column[2])
        return column_names, column_types

    def _get_unique_column_values_str(
        self,
        cursor,
        table,
        column_names,
        column_types,
        json_column_names,
        is_key_column_lst
    ):
        col_to_values_str_lst = []
        col_to_values_str_dict = {}
        key_col_list = [json_column_names[i] for i, flag in enumerate(is_key_column_lst) if flag]

        for idx, column_name in enumerate(column_names):
            # skip pk and fk
            if column_name in key_col_list:
                continue

            lower_column_name: str = column_name.lower()
            if (
                lower_column_name.endswith("id")
                or lower_column_name.endswith("email")
                or lower_column_name.endswith("url")
            ):
                col_to_values_str_dict[column_name] = ""
                continue

            sql = f"SELECT `{column_name}` FROM `{table}` GROUP BY `{column_name}` ORDER BY COUNT(*) DESC"
            cursor.execute(sql)
            values = cursor.fetchall()
            values = [value[0] for value in values]
            try:
                values_str = self._get_value_examples_str(values, column_types[idx])
            except Exception:
                values_str = ""
            col_to_values_str_dict[column_name] = values_str

        for k, column_name in enumerate(json_column_names):
            values_str = ""
            is_key = is_key_column_lst[k]
            if is_key:
                values_str = ""
            elif column_name in col_to_values_str_dict:
                values_str = col_to_values_str_dict[column_name]
            col_to_values_str_lst.append([column_name, values_str])

        return col_to_values_str_lst

    def _get_value_examples_str(self, values: List[object], col_type: str):
        if not values:
            return ""
        if len(values) > 10 and col_type in ["INTEGER", "REAL", "NUMERIC", "FLOAT", "INT"]:
            return ""

        vals = []
        has_null = False
        for v in values:
            if v is None:
                has_null = True
            else:
                tmp_v = str(v).strip()
                if tmp_v != "":
                    vals.append(v)
        if not vals:
            return ""

        if col_type in ["TEXT", "VARCHAR"]:
            new_values = []
            for v in vals:
                if not isinstance(v, str):
                    new_values.append(v)
                else:
                    if self.dataset_name == "spider":
                        v = v.strip()
                    if v == "" or "https://" in v or "http://" in v or is_email(v):
                        continue
                    else:
                        new_values.append(v)
            vals = new_values
            tmp_vals = [len(str(a)) for a in vals]
            if not tmp_vals or max(tmp_vals) > 50:
                return ""

        if not vals:
            return ""

        vals = vals[:6]
        if is_valid_date_column(vals):
            vals = vals[:1]
        if has_null:
            vals.insert(0, None)

        return str(vals)

    def _load_single_db_info(self, db_id: str) -> dict:
        table2coldescription = {}
        table2primary_keys = {}
        table_foreign_keys = {}
        table_unique_column_values = {}

        db_dict = self.db2dbjsons[db_id]
        important_key_id_lst = []
        keys = db_dict["primary_keys"] + db_dict["foreign_keys"]
        for col_id in keys:
            if isinstance(col_id, list):
                important_key_id_lst.extend(col_id)
            else:
                important_key_id_lst.append(col_id)

        db_path = f"{self.data_path}/{db_id}/{db_id}.sqlite"
        conn = sqlite3.connect(db_path)
        conn.text_factory = lambda b: b.decode(errors="ignore")
        cursor = conn.cursor()

        table_names_original_lst = db_dict["table_names_original"]
        all_column_names_original_lst = db_dict["column_names_original"]

        for tb_idx, tb_name in enumerate(table_names_original_lst):
            all_column_names_full_lst = db_dict["column_names"]
            col2dec_lst = []
            pure_column_names_original_lst = []
            is_key_column_lst = []

            for col_idx, (root_tb_idx, orig_col_name) in enumerate(all_column_names_original_lst):
                if root_tb_idx != tb_idx:
                    continue
                pure_column_names_original_lst.append(orig_col_name)
                is_key_column_lst.append(col_idx in important_key_id_lst)
                full_col_name = all_column_names_full_lst[col_idx][1].replace("_", " ")
                col2dec_lst.append([orig_col_name, full_col_name, ""])

            table2coldescription[tb_name] = col2dec_lst
            table_foreign_keys[tb_name] = []
            table2primary_keys[tb_name] = []

            all_sqlite_column_names_lst, all_sqlite_column_types_lst = self._get_column_attributes(
                cursor, tb_name
            )
            col_to_values_str_lst = self._get_unique_column_values_str(
                cursor,
                tb_name,
                all_sqlite_column_names_lst,
                all_sqlite_column_types_lst,
                pure_column_names_original_lst,
                is_key_column_lst,
            )
            table_unique_column_values[tb_name] = col_to_values_str_lst

        foreign_keys_lst = db_dict["foreign_keys"]
        for from_col_idx, to_col_idx in foreign_keys_lst:
            from_tb_idx = all_column_names_original_lst[from_col_idx][0]
            to_tb_idx = all_column_names_original_lst[to_col_idx][0]
            table_foreign_keys[table_names_original_lst[from_tb_idx]].append(
                (
                    all_column_names_original_lst[from_col_idx][1],
                    table_names_original_lst[to_tb_idx],
                    all_column_names_original_lst[to_col_idx][1],
                )
            )

        for pk_idx in db_dict["primary_keys"]:
            pk_idx_lst = pk_idx if isinstance(pk_idx, list) else [pk_idx]
            for cur_pk_idx in pk_idx_lst:
                tb_idx = all_column_names_original_lst[cur_pk_idx][0]
                table2primary_keys[table_names_original_lst[tb_idx]].append(
                    all_column_names_original_lst[cur_pk_idx][1]
                )

        cursor.close()
        return {
            "desc_dict": table2coldescription,
            "value_dict": table_unique_column_values,
            "pk_dict": table2primary_keys,
            "fk_dict": table_foreign_keys,
        }

    def _load_all_db_info(self):
        print("\nLoading all database info...", file=sys.stdout, flush=True)
        db_ids = [item for item in os.listdir(self.data_path)]
        for i in trange(len(db_ids)):
            self.db2infos[db_ids[i]] = self._load_single_db_info(db_ids[i])

    def _build_bird_table_schema_list_str(self, table_name, new_columns_desc, new_columns_val):
        schema_desc_str = f"# Table: {table_name}\n"
        extracted_column_infos = []
        for (col_name, full_col_name, col_extra_desc), (_, col_values_str) in zip(
            new_columns_desc, new_columns_val
        ):
            col_extra_desc = (
                f"And {col_extra_desc}"
                if col_extra_desc and str(col_extra_desc) != "nan"
                else ""
            )
            col_line = f"  ({col_name},"
            if full_col_name.strip():
                col_line += f" {full_col_name.strip()}."
            if col_values_str:
                col_line += f" Value examples: {col_values_str}."
            if col_extra_desc:
                col_line += f" {col_extra_desc[:100]}"
            col_line += "),"
            extracted_column_infos.append(col_line)
        schema_desc_str += "[\n" + "\n".join(extracted_column_infos).strip(",") + "\n]\n"
        return schema_desc_str

    # --- KEY CHANGE: In strict mode, use ONLY LLM-chosen columns (no PK/FK injection, no padding).
    # Also: "drop_all" drops the table entirely.
    def _get_db_desc_str(self, db_id: str, extracted_schema: dict, use_gold_schema: bool = False):
        if self.db2infos.get(db_id, {}) == {}:
            self.db2infos[db_id] = self._load_single_db_info(db_id)
        db_info = self.db2infos[db_id]
        desc_info, value_info, pk_info, fk_info = (
            db_info["desc_dict"],
            db_info["value_dict"],
            db_info["pk_dict"],
            db_info["fk_dict"],
        )

        schema_desc_str = ""
        db_fk_infos = []
        chosen_db_schem_dict = {}

        norm_extracted_schema = {str(k).lower(): v for k, v in (extracted_schema or {}).items()}

        def canon(s: str) -> str:
            # ignore underscores/spaces/case; matches Fname vs FName etc.
            return re.sub(r"[^a-z0-9]+", "", str(s).lower())

        for table_name in desc_info.keys():
            if table_name in (extracted_schema or {}):
                table_decision = extracted_schema[table_name]
            elif table_name.lower() in norm_extracted_schema:
                table_decision = norm_extracted_schema[table_name.lower()]
            else:
                table_decision = ""

            # strict mode: drop tables not mentioned
            if use_gold_schema and table_decision == "":
                continue

            # drop_all: drop this table entirely
            if isinstance(table_decision, str) and table_decision.lower() == "drop_all":
                continue

            columns_desc = desc_info[table_name]
            columns_val = value_info[table_name]

            new_columns_desc, new_columns_val = [], []

            # keep_all: keep whole table
            if isinstance(table_decision, str) and table_decision.lower() == "keep_all":
                new_columns_desc = deepcopy(columns_desc)
                new_columns_val = deepcopy(columns_val)

            # list of columns: keep ONLY those columns (your requirement)
            elif isinstance(table_decision, list):
                want = set(canon(c) for c in table_decision)
                for idx, (col_name, _, _) in enumerate(columns_desc):
                    if canon(col_name) in want:
                        new_columns_desc.append(columns_desc[idx])
                        new_columns_val.append(columns_val[idx])

                # if LLM chose columns that don't exist (typo), don't emit empty table
                if not new_columns_desc:
                    continue

            # non-strict fallback: table_decision == '' keeps all (matches your old behavior)
            else:
                new_columns_desc = deepcopy(columns_desc)
                new_columns_val = deepcopy(columns_val)

            chosen_db_schem_dict[table_name] = [col[0] for col in new_columns_desc]
            schema_desc_str += self._build_bird_table_schema_list_str(
                table_name, new_columns_desc, new_columns_val
            )

            for col_name, to_table, to_col in fk_info[table_name]:
                if "`" not in str(col_name):
                    col_name = f"`{col_name}`"
                if "`" not in str(to_col):
                    to_col = f"`{to_col}`"
                fk_link_str = f"{table_name}.{col_name} = {to_table}.{to_col}"
                if fk_link_str not in db_fk_infos:
                    db_fk_infos.append(fk_link_str)

        return schema_desc_str.strip(), "\n".join(db_fk_infos).strip(), chosen_db_schem_dict

    def _is_need_prune(self, db_id: str, db_schema: str):
        return True

    def _fallback_tables(self, db_id: str, query: str, k: int = 4) -> dict:
        if self.db2infos.get(db_id, {}) == {}:
            self.db2infos[db_id] = self._load_single_db_info(db_id)

        db_info = self.db2infos[db_id]
        all_tables = list(db_info["desc_dict"].keys())

        selected = {}
        query_lower = (query or "").lower()

        for t in all_tables:
            if t.lower() in query_lower:
                selected[t] = "keep_all"

        if len(selected) == 0:
            for t in all_tables[:k]:
                selected[t] = "keep_all"

        return selected

    def _prune(self, db_id: str, query: str, db_schema: str, db_fk: str, evidence: str = None) -> dict:
        prompt = selector_template.format(
            db_id=db_id, query=query, evidence=evidence, desc_str=db_schema, fk_str=db_fk
        )
        word_info = extract_world_info(self._message)
        reply = LLM_API_FUC(prompt, **word_info)

        print(f"\n[Selector] Raw LLM Reply (first 1200 chars):\n{str(reply)[:1200]}\n")

        def clean_json_text(text: str) -> str:
            text = (text or "").strip()
            text = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```\s*$", "", text)
            return text.strip()

        clean_reply = clean_json_text(str(reply))

        try:
            parsed = parse_json(clean_reply)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except Exception:
            pass

        try:
            parsed = json.loads(clean_reply)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except Exception:
            pass

        print("[Selector] JSON parsing FAILED. Returning {}.")
        return {}

    def talk(self, message: dict):
        if message.get("send_to") != self.name:
            return

        self._message = message
        db_id = message.get("db_id")
        ext_sch = message.get("extracted_schema", {}) or {}
        query = message.get("query")
        evidence = message.get("evidence")

        # full schema only used as input to the LLM selector prompt
        db_schema_full, db_fk_full, _ = self._get_db_desc_str(
            db_id=db_id, extracted_schema={}, use_gold_schema=False
        )

        need_prune = self._is_need_prune(db_id, db_schema_full)
        if self.without_selector:
            need_prune = False

        if ext_sch == {} and need_prune:
            try:
                raw_extracted_schema_dict = self._prune(
                    db_id=db_id,
                    query=query,
                    db_schema=db_schema_full,
                    db_fk=db_fk_full,
                    evidence=evidence,
                )
            except Exception as e:
                print(f"[Selector] Error in Pruning: {e}")
                raw_extracted_schema_dict = {}

            print(f"[Selector] Parsed Dict: {raw_extracted_schema_dict}")

            if not raw_extracted_schema_dict:
                print("[Selector] Warning: Selector returned empty. Falling back to TOP-K tables (not all).")
                raw_extracted_schema_dict = self._fallback_tables(db_id=db_id, query=query, k=4)

            # strict mode ON here (only keep tables mentioned by selector)
            db_schema_used, db_fk_used, chosen_db_schem_dict = self._get_db_desc_str(
                db_id=db_id,
                extracted_schema=raw_extracted_schema_dict,
                use_gold_schema=True,
            )

            message["extracted_schema"] = raw_extracted_schema_dict
            message["chosen_db_schem_dict"] = chosen_db_schem_dict
            message["desc_str"] = db_schema_used
            message["fk_str"] = db_fk_used
            message["pruned"] = True
            message["send_to"] = DECOMPOSER_NAME
            return message.copy()

        # if schema already provided upstream, respect it (strict only if non-empty)
        use_strict = True if ext_sch else False
        db_schema_used, db_fk_used, chosen_db_schem_dict = self._get_db_desc_str(
            db_id=db_id,
            extracted_schema=ext_sch,
            use_gold_schema=use_strict,
        )

        message["chosen_db_schem_dict"] = chosen_db_schem_dict
        message["desc_str"] = db_schema_used
        message["fk_str"] = db_fk_used
        message["pruned"] = False
        message["send_to"] = DECOMPOSER_NAME
        return message.copy()
    
class Decomposer(BaseAgent):
    name = DECOMPOSER_NAME
    description = "Decompose the question and solve them using CoT"

    def __init__(self, dataset_name):
        super().__init__()
        self.dataset_name = dataset_name
        self._message = {}

    def talk(self, message: dict):
        if message['send_to'] != self.name: return
        self._message = message
        query, evidence, schema_info, fk_info = message.get('query'), message.get('evidence'), message.get('desc_str'), message.get('fk_str')
        
        if self.dataset_name == 'bird':
            prompt = decompose_template_bird.format(query=query, desc_str=schema_info, fk_str=fk_info, evidence=evidence)
        else:
            prompt = decompose_template_spider.format(query=query, desc_str=schema_info, fk_str=fk_info)
        
        word_info = extract_world_info(self._message)
        reply = LLM_API_FUC(prompt, **word_info).strip()
        
        res = ''
        try:
            if "Final SQL" in reply:
                final_part = reply.split("Final SQL")[-1]
                res = parse_sql_from_string(final_part)
            else:
                res = parse_sql_from_string(reply)
        except Exception as e:
            res = f'error: {str(e)}'
        
        message['final_sql'] = res
        message['qa_pairs'] = reply
        message['fixed'] = False
        message['send_to'] = REFINER_NAME
        return message.copy()

class Refiner(BaseAgent):
    name = REFINER_NAME
    description = "Execute SQL and preform validation"

    def __init__(self, data_path: str, dataset_name: str):
        super().__init__()
        self.data_path = data_path
        self.dataset_name = dataset_name
        self._message = {}

    @func_set_timeout(120)
    def _execute_sql(self, sql: str, db_id: str) -> dict:
        db_path = f"{self.data_path}/{db_id}/{db_id}.sqlite"
        try:
            conn = sqlite3.connect(db_path)
            conn.text_factory = lambda b: b.decode(errors="ignore")
            cursor = conn.cursor()
            cursor.execute(sql)
            result = cursor.fetchall()
            conn.close()
            return {
                "sql": str(sql),
                "data": result[:5],
                "sqlite_error": "",
                "exception_class": ""
            }
        except sqlite3.Error as er:
            return {
                "sql": str(sql),
                "sqlite_error": str(' '.join(er.args)),
                "exception_class": str(er.__class__)
            }
        except Exception as e:
            return {
                "sql": str(sql),
                "sqlite_error": str(e.args),
                "exception_class": str(type(e).__name__)
            }

    def _is_need_refine(self, exec_result: dict):
        if self.dataset_name == 'spider':
            if 'data' not in exec_result: return True
            return False
        
        data = exec_result.get('data', None)
        if data is not None:
            if len(data) == 0:
                exec_result['sqlite_error'] = 'no data selected'
                return True
            return False
        else:
            return True
    
    def _refine(self, query: str, evidence:str, schema_info: str, fk_info: str, error_info: dict) -> dict:
        sql_arg = add_prefix(error_info.get('sql'))
        sqlite_error = error_info.get('sqlite_error')
        exception_class = error_info.get('exception_class')
        prompt = refiner_template.format(query=query, evidence=evidence, desc_str=schema_info, fk_str=fk_info, sql=sql_arg, sqlite_error=sqlite_error, exception_class=exception_class)
        word_info = extract_world_info(self._message)
        reply = LLM_API_FUC(prompt, **word_info)
        return parse_sql_from_string(reply)
    
    def talk(self, message: dict):
        if message['send_to'] != self.name: return
        self._message = message
        db_id, old_sql, query, evidence, schema_info, fk_info = message.get('db_id'), message.get('pred', message.get('final_sql')), message.get('query'), message.get('evidence'), message.get('desc_str'), message.get('fk_str')
        
        if 'error' in old_sql:
            message['try_times'] = message.get('try_times', 0) + 1
            message['pred'] = old_sql
            message['send_to'] = SYSTEM_NAME
            return
        
        is_timeout = False
        try:
            error_info = self._execute_sql(old_sql, db_id)
        except:
            is_timeout = True
        
        is_need = self._is_need_refine(error_info)
        if not is_need or is_timeout:
            message['try_times'] = message.get('try_times', 0) + 1
            message['pred'] = old_sql
            message['send_to'] = SYSTEM_NAME
        else:
            new_sql = self._refine(query, evidence, schema_info, fk_info, error_info)
            message['try_times'] = message.get('try_times', 0) + 1
            message['pred'] = new_sql
            message['fixed'] = True
            message['error_detail'] = error_info.get('sqlite_error', 'Unknown error')
            try:
                verify_result = self._execute_sql(new_sql, db_id)
                if self._is_need_refine(verify_result):
                    message['send_to'] = REFINER_NAME
                else:
                    message['send_to'] = SYSTEM_NAME  
            except:
                message['send_to'] = SYSTEM_NAME
        return message.copy()