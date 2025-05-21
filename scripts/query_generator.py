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
        """한영 혼용 키워드 추출"""
        KR_EN_MAP = {
            '매치': 'match',
            '유저': 'user',
            '평균': 'avg',
            '기본': 'basic'
        }
        tokens = re.findall(r'[\w가-힣]+', query.lower())
        translated = [KR_EN_MAP.get(t, t) for t in tokens]
        return set(translated) - {'show', 'find', 'get', 'display'}
    
    def generate_sql_query(self, natural_language_query):
        '''자연어 질의를 SQL 쿼리로 변환'''
        keywords = self._extract_keywords(natural_language_query)
        compressed_schema = self.db_connector.get_compressed_schema(keywords)
        
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