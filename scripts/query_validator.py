from sqlalchemy import inspect
import re
import sqlparse

class QueryValidator:
    def __init__(self, inspector):
        self.inspector = inspector
        self.forbidden_patterns = [
            r'DROP\s+TABLE',                    # 테이블 삭제
            r'DROP\s+DATABASE',                 # 데이터베이스 삭제
            r'TRUNCATE\s+TABLE',                # 테이블 삭제
            r'DELETE\s+FROM\s+(?!WHERE)',       # WHERE 절 없는 DELETE
            r'UPDATE\s+.*?\s+SET\s+(?!WHERE)',  # WHERE 절 없는 UPDATE
            r'ALTER\s+TABLE',                   # 테이블 수정
            r'GRANT\s+',                        # 권한 부여 명령어
            r'REVOKE\s+',                       # 권한 회수 명령어
        ]
    
    def validate_tables(self, sql_query):
        '''테이블이 데이터베이스에 존재하는지 확인'''
        # 안전하지 않은 쿼리 패턴 검사
        self._check_safety(sql_query)
        
        # SQL 파싱
        parsed = sqlparse.parse(sql_query)
        if not parsed:
            raise ValueError("SQL 구문을 파싱할 수 없습니다.")
        
        # 테이블 추출
        used_tables = self._extract_tables(sql_query)
        existing_tables = self.inspector.get_table_names()
        
        # 존재하지 않는 테이블 확인
        invalid_tables = [table for table in used_tables if table not in existing_tables]
        if invalid_tables:
            raise ValueError(f"존재하지 않는 테이블: {', '.join(invalid_tables)}")
        
        # 열 검증
        self._validate_columns(sql_query, used_tables)
        
        return True
    
    def _check_safety(self, sql_query):
        '''안전하지 않은 SQL 패턴 검사'''
        upper_query = sql_query.upper()
        
        # 금지된 패턴 확인
        for pattern in self.forbidden_patterns:
            if re.search(pattern, upper_query, re.IGNORECASE):
                raise ValueError("안전하지 않은 SQL 구문이 포함되어 있습니다.")
        
        # DDL 구문 금지
        if any(keyword in upper_query for keyword in ['CREATE TABLE', 'DROP TABLE', 'ALTER TABLE']):
            raise ValueError("데이터 정의어(DDL)는 지원되지 않습니다.")
        
        # 대규모 데이터 수정 구문 제한
        if 'DELETE FROM' in upper_query and 'WHERE' not in upper_query:
            raise ValueError("WHERE 절이 없는 DELETE 구문은 사용할 수 없습니다.")
            
        if 'UPDATE' in upper_query and 'SET' in upper_query and 'WHERE' not in upper_query:
            raise ValueError("WHERE 절이 없는 UPDATE 구문은 사용할 수 없습니다.")
    
