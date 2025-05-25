import os
import requests
import re
import time
import hashlib
import json
from collections import defaultdict

class QueryGenerator:
    def __init__(self, db_connector, json_loader):
        self.api_key = os.getenv("PERPLEXITY_API_KEY")
        self.db_connector = db_connector
        self.json_loader = json_loader
        self.api_url = "https://api.perplexity.ai/chat/completions"
        self.response_cache = {}  # 응답 캐싱
        self.cache_ttl = 3600
        
    def _extract_keywords(self, query):
        """한국어 키워드 추출"""
        
        # 불용어 목록
        stopwords = {
            '알려주세요', '보여주세요', '찾아주세요', 
            '알려줘', '보여줘', '찾아줘', 
            '알고싶어', '뭐야', '무엇', '어떤',
            '그리고', '또한', '또', '그럼',
            '이', '그', '저', '이것', '그것', '저것',
            '이번', '저번', '다음', '지난', '이전',
        }
        
        # 명사 추출
        tokens = re.findall(r'[\w가-힣]+', query.lower())
        
        # 중요 키워드 우선 추출(숫자, 영어 포함)
        important_words = [t for t in tokens if re.search(r'[0-9a-zA-Z]', t)]
        
        # 일반 키워드 추출(불용어 제외)
        keywords = set(tokens) - stopwords
        
        # 중요 키워드와 일반 키워드 합치기
        all_keywords = set(important_words) | keywords
        
        # 키워드 확장(유사어, 관련어 추가) -> 추후 개선 예정
        keyword_expansions = {
            '캐릭터': ['character', '실험체', 'character_id'],
            '팀': ['team', '팀원', 'team_id', '아군'],
            '경기': ['match', '게임', 'match_id', '매치'],
            '유저': ['user', '플레이어', 'user_id'],
            '아이템': ['equipment', '장비', '무기'],
            '킬': ['kill', '처치', 'death'],
            '데미지': ['damage', '피해량'],
            '스킬': ['skill', '능력', 'amp', '스킬증폭'],
        }
        
        expanded_keywords = set(all_keywords)
        for kw in all_keywords:
            if kw in keyword_expansions:
                expanded_keywords.update(keyword_expansions[kw])
        
        return expanded_keywords
        
    def _find_related_tables(self, keywords):
        """JSON 설명 기반 테이블 탐색"""
        table_scores = defaultdict(float)
        
        for kw in keywords:
            # 직접 테이블 이름 매칭
            for table in self.json_loader.metadata:
                if kw.lower() in table.lower():
                    table_scores[table] += 2.0
            
            # JSON 로더의 관계 그래프 활용
            related_tables = self.json_loader.get_related_tables(kw)
            for table in related_tables:
                table_scores[table] += 1.5

        sorted_tables = sorted(table_scores.items(), key=lambda x: x[1], reverse=True)
        return [table for table, score in sorted_tables if score > 0]
    
    def _build_contextual_prompt(self, query, tables):
        """맥락 기반 프롬프트 구성"""
        # 기본 컨텍스트 구성
        context = []
        
        # 테이블 관계 그래프 구축
        relation_graph = self.db_connector.build_relation_graph()
        
        # 테이블별 중요도 순으로 정렬
        for table in tables:
            # 테이블 정보
            desc = self.json_loader.metadata[table]['description']
            context.append(f"## {table} 테이블: {desc}")
            
            # 주요 컬럼 정보(PK, FK, 키워드 관련 컬럼)
            primary_keys = []
            foreign_keys = []
            important_columns = []
            other_columns = []
            
            for col, info in self.json_loader.metadata[table]['columns'].items():
                col_desc = f"{col}: {info['description']}"
                if info.get('note'):
                    col_desc += f" ({info['note']})"
                    
                if info.get('is_primary'):
                    primary_keys.append(col_desc)
                elif info.get('is_foreign'):
                    foreign_keys.append(col_desc)
                elif any(kw in info['description'].lower() for kw in query.lower().split()):
                    important_columns.append(col_desc)
                else:
                    other_columns.append(col_desc)
            
            # 중요도 순서대로 컬럼 정보 추출
            if primary_keys:
                context.append("### 기본 키(PK):")
                context.extend([f" - {col}" for col in primary_keys])
                
            if foreign_keys:
                context.append("### 외래 키(FK):")
                context.extend([f" - {col}" for col in foreign_keys])
                
            if important_columns:
                context.append("### 중요 컬럼:")
                context.extend([f" - {col}" for col in important_columns])
            
            # 나머지 컬럼은 너무 많으면 생략
            if len(other_columns) <= 5:
                context.append("### 기타 컬럼:")
                context.extend([f" - {col}" for col in other_columns])
            else:
                context.append(f"### 기타 컬럼: {len(other_columns)}개 (생략)")
            
            # 테이블 관계 정보 추출
            if table in relation_graph:
                related = relation_graph[table]
                if related:
                    context.append(f"### {table} 테이블 관계:")
                    context.append(f" - 관련 테이블: {', '.join(related)}")
            
            context.append("")
        
        return "\n".join(context)
    
    def _get_cached_response(self, query_hash):
        """캐시된 응답 가져오기"""
        if query_hash in self.response_cache:
            cache_time, response = self.response_cache[query_hash]
            if time.time() - cache_time < self.cache_ttl:
                return response
        return None
    
    def _cache_response(self, query_hash, response):
        """응답 캐싱"""
        self.response_cache[query_hash] = (time.time(), response)
    
    def _compress_prompt(self, prompt):
        """프롬프트 압축"""
        # 중복된 줄 제거
        lines = prompt.split('\n')
        unique_lines = []
        line_set = set()
        
        for line in lines:
            stripped = line.strip()
            if stripped and stripped not in line_set:
                line_set.add(stripped)
                unique_lines.append(line)
        
        # 너무 긴 설명 축약
        compressed_lines = []
        for line in unique_lines:
            if len(line) > 100 and not line.startswith('##'):  # 헤더는 그대로 유지
                # 중요함 정보만 추출
                if ':' in line:
                    parts = line.split(':', 1)
                    # 첫 부분과 마지막 부분만 유지
                    compressed = f"{parts[0]}: {parts[1][:40]}..." if len(parts[1]) > 40 else line
                    compressed_lines.append(compressed)
                else:
                    compressed_lines.append(line[:80] + '...' if len(line) > 80 else line)
            else:
                compressed_lines.append(line)
        
        return '\n'.join(compressed_lines)
    
    def generate_sql_query(self, natural_language_query):
        '''자연어 질의를 SQL 쿼리로 변환'''
        # 쿼리 해시 계산(캐싱용)
        query_hash = hashlib.md5(natural_language_query.encode()).hexdigest()
        
        # 캐싱 응답 확인
        cached_result = self._get_cached_response(query_hash)
        if cached_result:
            return cached_result
        
        # 키워드 추출
        keywords = self._extract_keywords(natural_language_query)
        
        # 연관 테이블 찾기
        related_tables = self._find_related_tables(keywords)
        
        # 컨텍스트 구성
        schema_context = self._build_contextual_prompt(natural_language_query, related_tables)
        
        # 프롬프트
        prompt = f"""
        [데이터베이스 컨텍스트]
        {schema_context}
        [사고 과정]
        1. 질문을 분석하여 필요한 정보가 무엇인지 파악
        2. 위에 제시된 데이터베이스 컨텍스트에서 관련된 테이블과 컬럼을 식별
        3. 필요한 조인(JOIN) 관계를 결정
        4. 필터링 조건을 설정
        5. 정렬 또는 그룹화가 필요한지 결정
        6. 최종 SQL 쿼리를 작성
                        
        [변환 규칙]
        1. 테이블과 컬럼 이름은 반드시 영어 원본 사용
        2. 테이블과 컬럼 이름은 한국어 설명을 정확한게 확인하여 스키마 요소와 매핑
        3. 사용자 입력은 한국어 자연어이며, 데이터베이스의 테이블 및 컬럼명은 영어
        4. 적절한 조인(JOIN)과 서브쿼리 활용
        5. 쿼리만 반환하고 설명은 제외
        6. 날짜/시간 비교에는 적절한 MySQL 함수 사용
        7. 효율적인 쿼리 실행을 위해 WHERE 조건 최적화
        8. 쿼리가 생성되면 정확성과 메모리 그리고 쿼리 속도를 최적화하는 방향으로 쿼리를 검토
        
        자연어 질의: {natural_language_query}

        생성할 SQL 쿼리 (Markdown 없이):
        """
        
        # 프롬프트 압축
        compressed_prompt = self._compress_prompt(prompt)

        # API 페이로드
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "sonar-pro",
            "messages": [
                {
                    "role": "system", 
                    "content": "사용자가 입력한 한국어 자연어 질문을 기반으로, 주어진 데이터베이스 스키마의 영어로 된 테이블명과 컬럼명을 정확히 식별하고 적절한 MySQL 쿼리를 생성하는 것이 목적입니다. 복잡한 질의에는 서브쿼리, 조인, 집계 함수 등을 적절히 활용하세요."
                },
                {
                    "role": "user", 
                    "content": compressed_prompt
                }
            ],
            "temperature": 0.2,  # 더 보수적인 답변을 위해 낮은 temperature로 설정
            "max_tokens": 1024,
            "stream": True  # 스트리밍 활성화(True: 응답이 생성되는 즉시 부분적으로 실시간으로 전송)
        }
        
        try:
            # 스트리밍 API 호출
            response = requests.post(self.api_url, headers=headers, json=payload, stream=True)
            response.raise_for_status()
            
            # 스트리밍 응답 처리
            full_response = ""
            
            for line in response.iter_lines():
                if line:
                    line_text = line.decode('utf-8')
                    if line_text.startswith('data: '):
                        try:
                            data = json.loads(line_text[6:])
                            if data.get('choices'):
                                chunk = data['choices'][0].get('delta', {}).get('content', '')
                                if chunk:
                                    full_response += chunk
                                    # 추후 실시간으로 처리할 수 있는 로직 추가하기
                        except:
                            pass
            
            # 캐싱 및 후처리
            sql_query = self._extract_sql(full_response)
            self._cache_response(query_hash, sql_query)
            
            return sql_query
        except Exception as e:
            return f"쿼리 생성 중 오류 발생: {str(e)}"
    
    def _extract_sql(self, response_text):
        """응답에서 SQL 쿼리 추출"""
        # SQL 블록 추출
        sql_match = re.search(r'```(?:sql)?\s*(.*?)```', response_text, re.DOTALL)
        if sql_match:
            return sql_match.group(1).strip()
        
        # 일반 코드 블록 추출
        code_match = re.search(r'```(?:python)?\s*(.*?)```', response_text, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        
        # SQL 쿼리 추출
        sql_keywords = ['SELECT', 'WITH', 'INSERT', 'WHERE', 'FROM', 'JOIN']
        lines = response_text.split('\n')
        for i, line in enumerate(lines):
            if any(line.strip().upper().startswith(kw) for kw in sql_keywords):
                # SQL 구문이 시작되는 줄부터 끝까지 반환
                return '\n'.join(lines[i:]).strip()
        
        # 없을 경우 원본 생성 결과 반환
        return response_text.strip()