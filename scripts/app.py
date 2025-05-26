import os
import pymysql
from db_connector import DatabaseConnector
from query_generator import QueryGenerator
from query_validator import QueryValidator
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
        
    def process_query(self, natural_language_query):
        """자연어 질의를 처리하고 결과 반환"""
        # SQL 쿼리 생성
        sql_query = self.query_generator.generate_sql_query(natural_language_query)
        
        # 결과 및 쿼리 실행 정보 준비
        result = {
            "natural_language_query": natural_language_query,  # 자연어 질문
            "generated_sql": sql_query,                        # SQL 쿼리 생성
            "execution_result": None,                          # SQL 쿼리 실행 결과
            "error": None,                                     # 에러 로그
            "query_plan": None                                 # 쿼리 실행 계획
        }
        
        # 쿼리 검증
        try:
            # 쿼리 구문 및 테이블 검증
            self.validator.validate_tables(sql_query)
            
            # 실행 계획 분석
            try:
                # SQLAlchemy로 실행 계획 분석
                plan = self.db_connector.analyze_query(sql_query)
                if plan:
                    result["query_plan"] = [dict(row) for row in plan]
            except:
                # 실행 계획 분석 실패는 무시
                pass
            
            # 쿼리 실행
            connection = self._get_connection()
            if connection:
                with connection.cursor() as cursor:
                    cursor.execute(sql_query)
                    result["execution_result"] = cursor.fetchall()
                    result["rows_affected"] = cursor.rowcount
            else:
                result["error"] = "데이터베이스 연결을 확인할 수 없습니다."
                
        except ValueError as e:
            result["error"] = str(e)
        except Exception as e:
            result["error"] = f"쿼리 실행 중 오류: {str(e)}"
        return result
    
    def close(self):
        """리소스 정리 및 데이터베이스 연결 종료"""
        if hasattr(self, 'connection_pool') and self.connection_pool and self.connection_pool.open:
            self.connection_pool.close()
            print("데이터베이스 연결이 종료되었습니다.")

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
            query = input("\n자연어 질의를 입력하세요. (종료하려면 'exit' 입력): ")
            
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
                if not result["execution_result"]:
                    print("결과가 없습니다.")
                else:
                    for row in result["execution_result"]:
                        print(row)
                    print(f"\n총 {result.get('rows_affected', 0)}개 행이 반환되었습니다.")
    finally:
        app.close()
