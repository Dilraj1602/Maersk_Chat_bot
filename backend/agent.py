from typing import Dict, Any, Optional
import os
import re
import logging
import requests
import json
import pandas as pd
from dotenv import load_dotenv
from .data_handler import DataHandler
from .utils import create_visualization

logger = logging.getLogger(__name__)


class QueryAgent:
    """
    QueryAgent using Google Gemini API (v1beta) with fully updated REST format.
    """

    def __init__(self, data_handler: DataHandler):
        load_dotenv()

        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY missing in .env")

        VALID_MODELS = {
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-2.0-flash",
            "gemini-2.0-pro",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
        }

        env_model = os.getenv("GENAI_MODEL", "gemini-2.5-flash").strip()
        env_model = env_model.replace("models/", "").strip()

        if env_model not in VALID_MODELS:
            logger.warning(f"[GENAI_MODEL INVALID] '{env_model}' → using gemini-2.5-flash")
            env_model = "gemini-2.5-flash"

        self.model_name = f"models/{env_model}"
        self.data_handler = data_handler

    # -------------------------------------------------------------------------
    # MODEL CALL
    # -------------------------------------------------------------------------
    def _call_model(self, prompt: str, temperature: float = 0.0, max_output_tokens: int = 512) -> str:

        url = f"https://generativelanguage.googleapis.com/v1beta/{self.model_name}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens
            }
        }

        resp = requests.post(url, params=params, headers=headers, json=payload, timeout=30)

        if resp.status_code >= 400:
            logger.error("Model API request failed: %s", resp.text)
        resp.raise_for_status()

        data = resp.json()

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            logger.warning("Unexpected response. Returning raw JSON.")
            return json.dumps(data)

    # -------------------------------------------------------------------------
    # SAFE SQL EXTRACTION (Bullet-proof)
    # -------------------------------------------------------------------------
    def _extract_sql(self, text: str) -> Optional[str]:
        """Extract SQL safely. Prevents 'ite SELECT' or matching inside 'SQLite'."""
        if not text or not isinstance(text, str):
            return None

        text = text.strip()
        logger.debug(f"Raw model response: {text[:200]}")

        # --- 1. ```sql ... ``` block ---
        m = re.search(r"```sql\s*(.*?)```", text, flags=re.S | re.I)
        if m:
            sql = m.group(1).strip()
            logger.debug("Matched ```sql block.")
            return self._clean_sql(sql)

        # --- 2. Any fenced block containing SQL keywords ---
        m = re.search(r"```(.*?)```", text, flags=re.S)
        if m:
            block = m.group(1)
            if re.search(r"\b(select|with)\b", block, flags=re.I):
                return self._clean_sql(block.strip())

        # --- 3. SAFE fallback: must match a WORD-BOUNDARY SELECT or WITH ---
        m = re.search(r"\b(select|with)\b", text, flags=re.I)
        if m:
            sql = text[m.start():].strip()
            return self._clean_sql(sql)

        logger.warning("SQL extraction failed. No SELECT/WITH found.")
        return None

    # -------------------------------------------------------------------------
    # CLEAN SQL
    # -------------------------------------------------------------------------
    def _clean_sql(self, sql: str) -> str:
        """Normalize SQL (remove junk, ensure terminator)."""
        sql = sql.strip()

        # Remove accidental prefix garbage lines like "Here is the query:"
        sql = re.sub(r"^(Here.*?:|SQL\s*:)", "", sql, flags=re.I).strip()

        # Stop at first semicolon
        if ";" in sql:
            sql = sql.split(";")[0] + ";"
        else:
            sql = sql.rstrip() + ";"

        # Guarantee SQL starts properly
        if not sql.lower().startswith(("select", "with")):
            # Find correct starting point
            m = re.search(r"\b(select|with)\b", sql, flags=re.I)
            if m:
                sql = sql[m.start():].strip()
            else:
                return None

        return sql

    # -------------------------------------------------------------------------
    # MAIN QUERY PROCESS
    # -------------------------------------------------------------------------
    def process_query(self, query: str) -> Dict[str, Any]:
        try:
            schema = self.data_handler.get_table_schema()
            schema_text = "\n".join(f"-- Table {t}: {', '.join(cols)}" for t, cols in schema.items())

            prompt = (
                "You are an expert SQL generator. "
                "Given the SQLite schema and question, output ONLY a valid SQLite SQL query. "
                "NO explanation. NO wording. NO markdown. Only SQL.\n\n"
                f"{schema_text}\n\n"
                f"Question: {query}\n\n"
                "Output only SQL."
            )

            gen_text = self._call_model(prompt)
            sql = self._extract_sql(gen_text)

            if not sql:
                return {"text": "I could not generate a valid SQL query.", "visualization": None}

            # Validate that the SQL only references tables available in the DB
            available_tables = list(schema.keys())
            # find tables referenced in SQL via FROM and JOIN
            referenced = set()
            for m in re.finditer(r"\bFROM\s+([a-zA-Z_][\w]*)", sql, flags=re.I):
                referenced.add(m.group(1))
            for m in re.finditer(r"\bJOIN\s+([a-zA-Z_][\w]*)", sql, flags=re.I):
                referenced.add(m.group(1))

            missing = [t for t in referenced if t not in available_tables]
            if missing:
                # Inform user and provide example customers-only queries
                example_queries = [
                    "Top 5 states by number of customers: SELECT customer_state, COUNT(*) AS num_customers FROM customers GROUP BY customer_state ORDER BY num_customers DESC LIMIT 5;",
                    "Number of unique customers: SELECT COUNT(DISTINCT customer_unique_id) FROM customers;",
                    "Customers in a city (replace CITY_NAME): SELECT * FROM customers WHERE customer_city = 'CITY_NAME' LIMIT 20;",
                ]
                msg = (
                    f"The generated SQL references tables not available in the database: {missing}. "
                    f"Available tables: {available_tables}.\n"
                    "This app currently only has the customers table loaded. Try one of these customers-only queries:\n- "
                    + "\n- ".join(example_queries)
                )
                return {"text": msg, "visualization": None}

            # Execute SQL
            try:
                df = self.data_handler.execute_query(sql)
            except Exception as e:
                logger.exception("SQL execution failed")
                return {"text": f"SQL execution failed: {e}", "visualization": None}

            # Summarize
            sample = df.head(20).to_csv(index=False)
            explain_prompt = (
                "Summarize this SQL result in 2–4 sentences and recommend a chart type.\n\n"
                f"SQL:\n{sql}\n\nCSV:\n{sample}\n\nAnswer:"
            )

            explanation = self._call_model(explain_prompt).strip()

            # Visualization
            viz = None
            try:
                if isinstance(df, pd.DataFrame) and not df.empty:
                    viz = create_visualization(df)
            except Exception:
                viz = None

            return {"text": explanation, "visualization": viz}

        except Exception as e:
            logger.exception("Error in process_query")
            return {"text": f"Error: {e}", "visualization": None}
