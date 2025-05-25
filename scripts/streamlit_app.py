import os
import streamlit as st
from dotenv import load_dotenv
from app import TextToSQLApp
load_dotenv()

# 페이지 제목 설정
st.title("Text to SQL for Eternal Return")

# 데이터베이스 설정
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": os.getenv("DB_PORT")
}

# TextToSQLApp 초기화
@st.cache_resource
def get_app():    
    return TextToSQLApp(db_config)

app = get_app()

# 자연어 질의 입력 영역

natural_language_query = st.text_area(
    "SQL로 변환할 자연어 질의를 입력하세요.",
    placeholder="예시: 모든 매치에서 가장 높은 승률을 기록하고 있는 실험체의 1등 비율",
    height=150
)

# 쿼리 실행 여부 체크박스
execute_query = st.checkbox("생성된 쿼리 실행하기")

# 쿼리 변환 및 실행 버튼
if st.button("쿼리 생성"):
    if natural_language_query:
        # 진행 상태 표시
        with st.spinner("쿼리 처리 중..."):
            result = app.process_query(natural_language_query)
            
            # 생성된 SQL 쿼리 출력
            st.subheader("생성된 SQL 쿼리")
            st.code(result["generated_sql"], language="sql")
            
            # 쿼리 실행 결과 출력 (체크박스가 선택된 경우에만)
            if execute_query:
                st.subheader("실행 결과")
                if result["error"]:
                    st.error(f"쿼리 실행 중 오류 발생: {result['error']}")
                else:
                    if not result["execution_result"]:
                        st.info("결과가 없습니다.")
                    else:
                        st.json(result["execution_result"])
    else:
        st.warning("자연어 질의를 입력해주세요.")

# 사용 방법 출력
with st.expander("사용 방법"):
    st.markdown("""
    1. 자연어로 질의를 입력합니다.
    2. '생성된 쿼리 실행하기' 체크박스를 선택할 경우, 생성된 SQL 쿼리가 실행됩니다.
    3. '쿼리 생성' 버튼을 클릭하여 결과를 확인합니다.
    """)

# 앱 종료 시 리소스 정리
def cleanup():
    app.close()

# 앱이 종료될 때 호출되는 함수 등록
import atexit
atexit.register(cleanup)
