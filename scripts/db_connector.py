# db_connector.py
from sqlalchemy import create_engine, MetaData, inspect
from schema_compressor import SchemaCompressor
import json

class DatabaseConnector:
    def __init__(self, connection_string):
        self.engine = create_engine(connection_string)
        self.metadata = MetaData()
        self.inspector = inspect(self.engine)
        self.compressor = None # 스키마 압축
        
    def get_all_tables(self):
        """데이터베이스의 모든 테이블 이름 조회"""
        return self.inspector.get_table_names()
    
    def get_table_details(self, table_name):
        """특정 테이블의 컬럼 정보 조회"""
        columns = self.inspector.get_columns(table_name)
        foreign_keys = self.inspector.get_foreign_keys(table_name)
        primary_keys = self.inspector.get_pk_constraint(table_name)
        
        return {
            "columns": columns,
            "foreign_keys": foreign_keys,
            "primary_keys": primary_keys
        }
    
    def get_full_schema(self):
        """전체 데이터베이스 스키마 정보를 수집하여 반환"""
        schema_info = {}
        tables = self.get_all_tables()
        
        for table in tables:
            schema_info[table] = self.get_table_details(table)
            
        return schema_info
    
    def get_compressed_schema(self, query_keywords):
        """질의 키워드 기반 스키마 압축"""
        if not self.compressor:
            full_schema = self.get_full_schema()
            self.compressor = SchemaCompressor(full_schema)
        
        # 키워드 기반 테이블 필터링
        filtered_tables = [
            table for table in self.get_all_tables()
            if any(kw.lower() in table.lower() for kw in query_keywords)
        ]
        
        return self.compressor.generate_compressed_prompt(filtered_tables)
    
    def schema_to_prompt_format(self):
        """Perplexity API에 전달할 형식으로 스키마 정보 변환"""
        schema_info = self.get_full_schema()
        formatted_schema = []
        
        for table, details in schema_info.items():
            table_info = f"Table: {table}\nColumns:\n"
            for column in details['columns']:
                col_type = str(column['type'])
                nullable = "NOT NULL" if not column.get('nullable', True) else "NULL"
                table_info += f"  - {column['name']} ({col_type}) {nullable}\n"
            
            if details['primary_keys']['constrained_columns']:
                pks = ", ".join(details['primary_keys']['constrained_columns'])
                table_info += f"Primary Key: {pks}\n"
            
            if details['foreign_keys']:
                table_info += "Foreign Keys:\n"
                for fk in details['foreign_keys']:
                    src_cols = ", ".join(fk['constrained_columns'])
                    ref_cols = ", ".join(fk['referred_columns'])
                    table_info += f"  - {src_cols} -> {fk['referred_table']}.{ref_cols}\n"
            
            formatted_schema.append(table_info)
            
        return "\n".join(formatted_schema)
