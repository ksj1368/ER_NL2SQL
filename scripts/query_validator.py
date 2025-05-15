from sqlalchemy import inspect
import re

class QueryValidator:
    def __init__(self, inspector):
        self.inspector = inspector
    
    def validate_tables(self, sql_query):
        used_tables = re.findall(r'\bFROM\s+(\w+)', sql_query, re.IGNORECASE)
        existing_tables = self.inspector.get_table_names()
        
        for table in used_tables:
            if table not in existing_tables:
                raise ValueError(f"존재하지 않는 테이블: {table}")