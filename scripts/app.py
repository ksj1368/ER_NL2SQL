# app.py
import os
import pymysql
from db_connector import DatabaseConnector
from query_generator import QueryGenerator
from dotenv import load_dotenv

class TextToSQLApp:
    def __init__(self, db_config):
        # 데이터베이스 연결 설정
        connection_string = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
        self.db_connector = DatabaseConnector(connection_string)
        
        # 스키마 정보 로드
        self.schema_info = self.db_connector.schema_to_prompt_format()
        
        # 쿼리 생성기 초기화
        self.query_generator = QueryGenerator(self.schema_info, self.db_connector)
        
        # PyMySQL 연결 (실제 쿼리 실행용)
        self.connection = pymysql.connect(
            host=db_config['host'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database'],
            port=int(db_config['port']),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        # 연결
        
    def process_query(self, natural_language_query):
        """자연어 질의를 처리하고 결과 반환"""
        # SQL 쿼리 생성
        sql_query = self.query_generator.generate_sql_query(natural_language_query)
        
        # 결과 및 쿼리 실행 정보 준비
        result = {
            "natural_language_query": natural_language_query,
            "generated_sql": sql_query,
            "execution_result": None,
            "error": None
        }
        
        try:
            # 쿼리 실행
            with self.connection.cursor() as cursor:
                cursor.execute(sql_query)
                result["execution_result"] = cursor.fetchall()
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def close(self):
        """리소스 정리"""
        if hasattr(self, 'connection') and self.connection:
            self.connection.close()

# 간단한 CLI 인터페이스
if __name__ == "__main__":
    load_dotenv()
    # 환경 변수 설정
    os.environ["PERPLEXITY_API_KEY"] = os.getenv("PERPLEXITY_API_KEY")
    
    # 데이터베이스 설정
    db_config = {
        "host": os.getenv("DB_HOST"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
        "port": os.getenv("DB_PORT")
    }
    
    app = TextToSQLApp(db_config)
    
    try:
        while True:
            query = input("\n자연어 질의를 입력하세요 (종료하려면 'exit' 입력): ")
            
            if query.lower() == 'exit':
                break
                
            result = app.process_query(query)
            
            print("\n생성된 SQL 쿼리:")
            print(result["generated_sql"])
            
            if result["error"]:
                print("\n실행 중 오류 발생:")
                print(result["error"])
            else:
                print("\n실행 결과:")
                for row in result["execution_result"]:
                    print(row)
    finally:
        app.close()
