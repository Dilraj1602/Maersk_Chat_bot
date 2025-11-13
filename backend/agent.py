from typing import Dict, Any, Optional
import os
import re
import logging
try:
    import google.generativeai as genai
except Exception as _e:  # pragma: no cover - environment-specific
    # Defer raising until runtime so importing this module doesn't crash apps
    genai = None
    _IMPORT_GOOGLE_GENAI_ERROR = _e
from dotenv import load_dotenv
from .data_handler import DataHandler
from .utils import create_visualization
import pandas as pd

logger = logging.getLogger(__name__)


class QueryAgent:
    """Lightweight QueryAgent that uses a Generative model to produce SQL for SQLite and
    then executes it via the project's DataHandler.

    This avoids depending on LangChain internals and keeps behavior explicit and
    easy to debug.
    """

    def __init__(self, data_handler: DataHandler):
        load_dotenv()
        # If the google.generativeai package failed to import earlier, raise a
        # clear error at runtime (so importing the module doesn't immediately crash),
        # with guidance on how to fix it.
        if genai is None:  # pragma: no cover - runtime dependency
            err_msg = (
                "The 'google.generativeai' package is not available.\n"
                "Install it with: pip install google-generativeai\n"
                "If it is already installed, ensure there are no conflicting 'google' packages that shadow the namespace.\n"
            )
            # Attach the original import error if available for debugging
            if "_IMPORT_GOOGLE_GENAI_ERROR" in globals():
                err_msg += f"Original import error: {_IMPORT_GOOGLE_GENAI_ERROR!r}"
            raise ImportError(err_msg)

        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

        # Gemini / OpenRouter model wrapper
        # Use 'gemini-pro' by default; change as needed in .env
        self.model = genai.GenerativeModel(os.getenv("GENAI_MODEL", "gemini-pro"))

        self.data_handler = data_handler

    def _extract_sql(self, text: str) -> Optional[str]:
        """Try to extract a SQL statement from the model output.

        Looks for ```sql``` code fences first, then a first occurrence of SELECT/WITH.
        Returns None if no SQL found.
        """
        # Try code fence with sql
        m = re.search(r"```sql\s*(.*?)```", text, flags=re.S | re.I)
        if m:
            return m.group(1).strip()

        # Try any code fence
        m = re.search(r"```(?:.*?)\s*(.*?)```", text, flags=re.S)
        if m and ("select" in m.group(1).lower() or "with" in m.group(1).lower()):
            return m.group(1).strip()

        # Fallback: find first SELECT ...; or rest of text starting at SELECT
        m = re.search(r"(select\s.+)", text, flags=re.I | re.S)
        if m:
            sql = m.group(1).strip()
            # if it ends with extraneous text, try to cut at last semicolon
            if ";" in sql:
                sql = sql.split(";")[0] + ";"
            return sql

        return None

    def process_query(self, query: str) -> Dict[str, Any]:
        """Generate SQL for the user's natural language query, run it, and return
        a human-readable explanation plus an optional Plotly visualization.
        """
        try:
            # Provide schema to the model so it can generate valid SQL for the DB
            schema = self.data_handler.get_table_schema()
            schema_text = "\n".join(
                f"-- Table {t}: {', '.join(cols)}" for t, cols in schema.items()
            )

            prompt = (
                "You are an expert data analyst. Given the SQLite database schema below and a user question, "
                "write a single, syntactically-correct SQLite query that answers the question. "
                "Return only the SQL statement (no explanation). Use standard SQLite SQL.\n\n"
                f"Schema:\n{schema_text}\n\n"
                f"Question: {query}\n\n"
                "If the request requires aggregation, grouping, or ordering, include it. If it's impossible, reply with 'NO_SQL'."
            )

            # Ask the model for SQL
            gen_resp = self.model.generate_content(prompt)
            gen_text = getattr(gen_resp, "text", str(gen_resp))

            sql = self._extract_sql(gen_text)
            if not sql or sql.strip().upper().startswith("NO_SQL"):
                return {"text": "I could not generate a SQL query for that request.", "visualization": None}

            # Execute SQL
            try:
                df = self.data_handler.execute_query(sql)
            except Exception as e:
                logger.exception("SQL execution failed")
                return {"text": f"Failed to execute SQL: {e}", "visualization": None}

            # Generate a concise natural-language explanation of the results
            # Limit the amount of data we send back to the model (head + schema)
            sample = df.head(20).to_csv(index=False)
            explain_prompt = (
                "You are a helpful analyst. Given the SQL query and the query results (CSV), produce a short (2-4 sentences) "
                "summary in plain English and suggest a good chart type (bar, line, pie, table, scatter) if appropriate.\n\n"
                f"SQL:\n{sql}\n\nResults (CSV):\n{sample}\n\nAnswer:" 
            )

            explain_resp = self.model.generate_content(explain_prompt)
            explanation = getattr(explain_resp, "text", str(explain_resp)).strip()

            # Create visualization if the data is tabular and small enough
            viz = None
            try:
                if isinstance(df, pd.DataFrame) and not df.empty:
                    viz = create_visualization(df)
            except Exception:
                viz = None

            return {"text": explanation, "visualization": viz}

        except Exception as e:
            logger.exception("Error in process_query")
            return {"text": f"I encountered an error: {e}", "visualization": None}
