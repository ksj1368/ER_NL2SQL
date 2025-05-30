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
    
    def _extract_tables(self, sql_query):
        '''SQL 쿼리에서 사용된 테이블 추출'''
        
        # 정규 표현식
        from_pattern = r'\bFROM\s+(\w+)'
        join_pattern = r'\bJOIN\s+(\w+)'
        update_pattern = r'\bUPDATE\s+(\w+)'
        insert_pattern = r'\bINSERT\s+INTO\s+(\w+)'
        
        # 테이블 목록 추출
        tables = []
        tables.extend(re.findall(from_pattern, sql_query, re.IGNORECASE))
        tables.extend(re.findall(join_pattern, sql_query, re.IGNORECASE))
        tables.extend(re.findall(update_pattern, sql_query, re.IGNORECASE))
        tables.extend(re.findall(insert_pattern, sql_query, re.IGNORECASE))
        
        # 중복 제거 및 소문자 변환
        return list(set([table.lower() for table in tables]))
    
    def _validate_columns(self, sql_query, tables):
        '''테이블의 열이 실제로 존재하는지 확인'''
        
        # 모든 테이블의 열 목록 가져오기
        table_columns = {}
        for table in tables:
            try:
                columns = self.inspector.get_columns(table)
                table_columns[table] = [col['name'].lower() for col in columns]
            except:
                # 테이블을 찾을 수 없는 경우(validate_tables에서 확인)
                continue
        
        # SELECT 구문의 열 검증
        select_pattern = r'SELECT\s+(.*?)\s+FROM'
        select_match = re.search(select_pattern, sql_query, re.IGNORECASE)
        
        if select_match:
            column_part = select_match.group(1)
            
            # *는 검사 제외
            if column_part.strip() != '*':
                columns = [c.strip() for c in column_part.split(',')]
                
                # 개별 열 검증(완전한 검증은 어렵기 때문에 기본적인 검증만 수행)
                for col in columns:
                    # 함수나 별칭이 있는 경우 제외
                    if '(' in col or ' AS ' in col.upper() or '.' in col:
                        continue
                    
                    # 모든 테이블에서 열 확인
                    valid = False
                    for table, cols in table_columns.items():
                        if col.lower() in cols:
                            valid = True
                            break
                    
                    if not valid:
                        print(f"경고: 열 '{col}'를 테이블 스키마에서 찾을 수 없습니다.")
        return True
