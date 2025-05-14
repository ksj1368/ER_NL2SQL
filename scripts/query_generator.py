import os
import requests
import re

class QueryGenerator:
    def __init__(self, schema_info, db_connector):
        self.api_key = os.getenv("PERPLEXITY_API_KEY")
        self.schema_info = schema_info
        self.db_connector = db_connector
        self.api_url = "https://api.perplexity.ai/chat/completions"

    def _extract_keywords(self, query):
        """자연어 질의에서 키워드 추출"""
        tokens = re.findall(r'\w+', query.lower())
        return set(tokens) - {'show', 'find', 'get', 'display'}
    
    def generate_sql_query(self, natural_language_query):
        keywords = self._extract_keywords(natural_language_query)
        compressed_schema = self.db_connector.get_compressed_schema(keywords)
        
        prompt = self._create_prompt(natural_language_query, compressed_schema)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        print(prompt)
        payload = {
            "model": "sonar-pro",
            "messages": [
                {"role": "system", "content": "당신은 자연어를 SQL 쿼리로 변환하는 전문가입니다. 주어진 데이터베이스 스키마를 기반으로 정확한 MySQL 쿼리를 생성해주세요."},
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
                [압축된 스키마 버전 1.2]
                {schema}

                [질의 변환 규칙]
                1. 압축 컬럼 사용시 원래 이름으로 확장 (예: char_* → char_id, char_name)
                2. 테이블과 컬럼 이름을 정확하게 사용하세요.
                3. 적절한 조인(JOIN)과 서브쿼리를 활용하세요.
                4. 쿼리만 반환하고 설명은 제외해주세요.

                자연어 질의: {query}

                생성할 SQL 쿼리:
                """
                    
    def _extract_sql(self, response_text):
        return response_text.strip()