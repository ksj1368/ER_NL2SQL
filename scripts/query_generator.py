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
        
        prompt = self._create_prompt(natural_language_query, compressed_schema)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        print(prompt) # 프롬프트 확인용 나중에 제거하기
        payload = {
            "model": "sonar-pro",
            "messages": [
                {"role": "system", "content": "당신은 자연어를 SQL 쿼리로 변환하는 데이터 분석 전문가입니다. 주어진 데이터베이스 스키마를 기반으로 정확한 MySQL 쿼리를 생성해주세요."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 1024
        }

        try:
            response = requests.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            sql_query = data["choices"][0]["message"]["content"]
            return self._extract_sql(sql_query)
        except Exception as e:
            return f"쿼리 생성 중 오류 발생: {str(e)}"

    '''def _create_prompt(self, query):
        return f"""
        다음 데이터베이스 스키마를 기반으로 자연어 질의를 MySQL 쿼리로 변환해주세요:

        {self.schema_info}

        자연어 질의: {query}

        요구사항:
        1. 정확한 MySQL 문법을 사용하세요.
        2. 테이블과 컬럼 이름을 정확하게 사용하세요.
        3. 적절한 조인(JOIN)과 서브쿼리를 활용하세요.
        4. 쿼리만 반환하고 설명은 제외해주세요.

        MySQL 쿼리:
        """
    '''
    def _create_prompt(self, query, schema):
        return f"""
                [압축된 스키마]
                {schema}
                
                [질의 변환 규칙]
                1. 압축 컬럼 사용시 원래 이름으로 확장 (예: char_* → char_id, char_name)
                2. 테이블과 컬럼 이름을 정확하게 사용하세요.
                3. 적절한 조인(JOIN)과 서브쿼리를 활용하세요.
                4. 쿼리만 반환하고 설명은 제외해주세요.

                자연어 질의: {query}

                생성할 SQL 쿼리 (Markdown 없이):
                """
                    
    def _extract_sql(self, response_text):
        return response_text.strip()