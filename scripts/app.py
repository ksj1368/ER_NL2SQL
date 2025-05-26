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
        # JSON 스키마 로더 초기화
        self.json_loader = JsonSchemaLoader("./docs/data_discription.json")
        self.db_config = db_config
        # 데이터베이스 커넥터 초기화 (연결 풀 사용)
        self.db_connector = DatabaseConnector(
            connection_string=connection_string,
            json_loader=self.json_loader,
            pool_size=5  # 연결 풀 크기 설정
        )
        
        # 쿼리 생성기 초기화
        self.query_generator = QueryGenerator(
            db_connector=self.db_connector,
            json_loader=self.json_loader
        )
        
        # 쿼리 검증기 초기화
        self.validator = QueryValidator(self.db_connector.inspector)
        
        # 연결 풀 생성 (PyMySQL)
        self.connection_pool = self._create_connection_pool(db_config)
    
    def _create_connection_pool(self, db_config):
        """PyMySQL 연결 풀 생성"""
        try:
            # PyMySQL 직접 연결 (SQLAlchemy와 별도로 유지)
            return pymysql.connect(
                host=db_config['host'],
                user=db_config['user'],
                password=db_config['password'],
                database=db_config['database'],
                port=int(db_config['port']),
                charset='utf8mb4',
                cursorclass=DictCursor,
                autocommit=True,  # 자동 커밋 활성화
                connect_timeout=5
            )
        except Exception as e:
            print(f"연결 풀 생성 중 오류: {str(e)}")
            return None
    
    def _get_connection(self):
        """연결 풀에서 연결 가져오기"""
        db_config = self.db_config
        if not self.connection_pool or not self.connection_pool.open:
            db_config = {
                'host': db_config['host'],
                'user': db_config['user'],
                'password': db_config['password'],
                'database': db_config['database'],
                'port': int(db_config['port']),
            }
            self.connection_pool = self._create_connection_pool(db_config)
        
        return self.connection_pool
    
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
