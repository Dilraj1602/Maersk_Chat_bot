import pandas as pd
import sqlite3
from typing import List, Dict, Any
import os
from dotenv import load_dotenv

class DataHandler:
    """Handles data loading, preprocessing, and database operations for Olist dataset."""
    
    def __init__(self):
        """Initialize DataHandler and set up database connection."""
        load_dotenv()
        self.db_path = os.getenv("DATABASE_URL").replace("sqlite:///", "")
        self._initialize_database()
    
    def _initialize_database(self):
        """Load CSV files into SQLite database if not already present."""
        if not os.path.exists(self.db_path):
            # Create data directory if it doesn't exist
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            # Initialize SQLite database
            conn = sqlite3.connect(self.db_path)
            
            # Dictionary of dataset files and their table names
            datasets = {
                'orders': 'olist_orders_dataset.csv',
                'order_items': 'olist_order_items_dataset.csv',
                'products': 'olist_products_dataset.csv',
                'customers': 'olist_customers_dataset.csv',
                'sellers': 'olist_sellers_dataset.csv',
                'product_category': 'product_category_name_translation.csv',
                'order_payments': 'olist_order_payments_dataset.csv',
                'order_reviews': 'olist_order_reviews_dataset.csv'
            }
            
            # Load each dataset into the database
            for table_name, file_name in datasets.items():
                try:
                    df = pd.read_csv(f'data/{file_name}')
                    df.to_sql(table_name, conn, if_exists='replace', index=False)
                except Exception as e:
                    print(f"Error loading {file_name}: {str(e)}")
            
            conn.close()
    
    def execute_query(self, query: str) -> pd.DataFrame:
        """Execute SQL query and return results as DataFrame."""
        try:
            conn = sqlite3.connect(self.db_path)
            result = pd.read_sql_query(query, conn)
            conn.close()
            return result
        except Exception as e:
            raise Exception(f"Error executing query: {str(e)}")
    
    def get_table_schema(self) -> Dict[str, List[str]]:
        """Return schema information for all tables in the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        schemas = {}
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            schemas[table_name] = [col[1] for col in columns]
        
        conn.close()
        return schemas
    
    def get_sample_data(self, table_name: str, limit: int = 5) -> pd.DataFrame:
        """Return sample rows from a specified table."""
        return self.execute_query(f"SELECT * FROM {table_name} LIMIT {limit}")