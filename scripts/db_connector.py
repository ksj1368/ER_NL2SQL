from sqlalchemy import create_engine, MetaData, inspect, text
from sqlalchemy.pool import QueuePool
from utils import cache_result
from collections import defaultdict

class DatabaseConnector:
    def __init__(self, connection_string, json_loader, pool_size=5):
        # 연결 풀링 설정으로 DB 연결
        self.engine = create_engine(
            connection_string, 
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=3600  # 1시간마다 연결
        )
        self.json_loader = json_loader # 데이터 명세서를 JSON 파일로 변환
        self.metadata = MetaData()
        self.inspector = inspect(self.engine)
        self.compressor = None  # 스키마 압축
        self._schema_cache = {}  # 스키마 캐싱
        self._relation_graph = None  # 테이블 관계 그래프
        
    @cache_result(expires_after=3600)
    def get_all_tables(self):
        """데이터베이스의 모든 테이블 이름 조회"""
        return self.inspector.get_table_names()
    
    @cache_result(expires_after=3600)
    def get_table_details(self, table_name):
        """특정 테이블의 컬럼 정보 조회"""
        columns = self.inspector.get_columns(table_name)
        foreign_keys = self.inspector.get_foreign_keys(table_name)
        primary_keys = self.inspector.get_pk_constraint(table_name)
        indices = self.inspector.get_indexes(table_name)
        
        return {
            "columns": columns,
            "foreign_keys": foreign_keys,
            "primary_keys": primary_keys,
            "indices": indices 
        }
    
    @cache_result(expires_after=3600)
    def get_full_schema(self):
        """전체 데이터베이스 스키마 정보를 수집하여 반환"""
        if self._schema_cache:
            return self._schema_cache
            
        schema_info = {}
        database_name = self.engine.url.database  # 데이터베이스 이름 추출
        tables = self.get_all_tables()
        
        for table in tables:
            details = self.get_table_details(table)
            details['full_name'] = f"{database_name}.{table}" # 정규화 테이블 이름
            schema_info[table] = details
            
        self._schema_cache = schema_info
        return schema_info
    
    def build_relation_graph(self):
        """테이블 간 관계 그래프"""
        if self._relation_graph:
            return self._relation_graph
            
        graph = {}
        schema_info = self.get_full_schema()
        
        graph = defaultdict(set)
        schema_info = self.get_full_schema()
        
        for table, details in schema_info.items():
            for fk in details.get('foreign_keys', []):
                referred_table = fk['referred_table']
                graph[table].add(referred_table)
                graph[referred_table].add(table)
        
        
        json_relation = self.json_loader.relation_graph # JSON 메타데이터 기반 관계 할당
        for table, relations in json_relation.items():
            graph[table].update(relations)
        
        self._relation_graph = graph
        return graph
    
    def get_compressed_schema(self, query_keywords):
        """한국어 키워드 기반 스키마 필터링"""
        # 1단계: 직접 매칭 테이블 검색
        direct_tables = [
            table for table in self.get_all_tables()
            if any(kw in self.json_loader.metadata[table]['description']
                for kw in query_keywords)
        ]
        
        # 2단계: 컬럼 설명 기반 확장 검색
        column_based_tables = []
        for table, details in self.json_loader.metadata.items():
            if any(any(kw in col_info['description'] or kw in col_info.get('note', '')
                    for col_info in details['columns'].values())
                for kw in query_keywords):
                column_based_tables.append(table)
        
        # 3단계: 테이블 관계 기반 확장
        related_tables = set(direct_tables + column_based_tables)
        if related_tables:
            relation_graph = self.build_relation_graph()
            
            # 직접 관련된 테이블과 연관된 이웃 테이블들도 추가
            neighbors = set()
            for table in related_tables:
                if table in relation_graph:
                    neighbors.update(relation_graph[table])
            related_tables.update(neighbors)
        
        return list(related_tables)
    
    def schema_to_prompt_format(self, filtered_tables=None):
        """Perplexity API에 전달할 형식으로 스키마 정보 변환"""
        schema_info = self.get_full_schema()
        formatted_schema = []
        
        # 필터링된 테이블 목록이 있으면 사용하고 없을 경우 모든 테이블 사용
        tables_to_format = filtered_tables or schema_info.keys()
        
        for table in tables_to_format:
            if table not in schema_info:
                continue
                
            details = schema_info[table]
            # JSON 메타데이터에서 테이블 설명 가져오기
            table_desc = self.json_loader.metadata.get(table, {}).get('description', '')
            table_info = f"Table: {table} - {table_desc}\nColumns:\n"
            
            for column in details['columns']:
                col_type = str(column['type'])
                nullable = "NOT NULL" if not column.get('nullable', True) else "NULL"
                
                # JSON 메타데이터에서 컬럼 설명 가져오기
                col_name = column['name'] # 컬럼 이름
                col_desc = ""             # 컬럼 설명  
                col_note = ""             # 컬럼 추가 설명  
                
                if table in self.json_loader.metadata:
                    col_info = self.json_loader.metadata[table]['columns'].get(col_name, {})
                    col_desc = col_info.get('description', '')
                    col_note = col_info.get('note', '')
                
                if col_note:
                    col_desc = f"{col_desc} ({col_note})"
                
                table_info += f" - {col_name} ({col_type}) {nullable} - {col_desc}\n"
            
            if details['primary_keys']['constrained_columns']:
                pks = ", ".join(details['primary_keys']['constrained_columns'])
                table_info += f"Primary Key: {pks}\n"
            
            if details['foreign_keys']:
                table_info += "Foreign Keys:\n"
                for fk in details['foreign_keys']:
                    src_cols = ", ".join(fk['constrained_columns'])
                    ref_cols = ", ".join(fk['referred_columns'])
                    table_info += f" - {src_cols} -> {fk['referred_table']}.{ref_cols}\n"
            
            formatted_schema.append(table_info)
        
        return "\n\n".join(formatted_schema)
    
    def execute_query(self, sql_query, max_rows=100):
        """SQL 쿼리 실행 및 결과 반환"""
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(sql_query))
                rows = result.fetchmany(max_rows)
                columns = result.keys()
                
                return {
                    'columns': columns,
                    'rows': rows,
                    'row_count': len(rows),
                    'has_more': result.rowcount > len(rows) if result.rowcount >= 0 else False
                }
        except Exception as e:
            raise Exception(f"쿼리 실행 오류: {str(e)}")
            
    def analyze_query(self, sql_query):
        """SQL 쿼리 분석 (EXPLAIN)"""
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(f"EXPLAIN {sql_query}"))
                return result.fetchall()
        # 분석할 수 없는 쿼리인 경우
        except Exception as e:
            return None  