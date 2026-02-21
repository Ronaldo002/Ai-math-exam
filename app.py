import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="AI 모의고사 생성기", page_icon="📝", layout="wide")
st.title("📝 AI 수능 모의고사 생성기 (API 재설정 버전)")

# 1. API 연결 엔진 (에러 자동 복구 기능 탑재)
def get_working_model(api_key):
    genai.configure(api_key=api_key)
    # 구글 서버가 인식할 수 있는 모든 모델 후보군
    model_candidates = [
        'gemini-1.5-flash', 
        'gemini-1.5-flash-latest', 
        'gemini-1.5-pro',
        'models/gemini-1.5-flash'
    ]
    
    for name in model_candidates:
        try:
            model = genai.GenerativeModel(name)
            # 실제로 응답이 오는지 테스트
            model.generate_content("hi", generation_config={"max_output_tokens": 1})
            return model
        except:
            continue
    return None

# 2. 메인 화면 로직
if "GEMINI_API_KEY" not in st.secrets:
    st.error("⚠️ Secrets에 API 키가 설정되지 않았습니다.")
else:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    
    with st.sidebar:
        st.header("설정")
        subject = st.selectbox("과목", ["미적분", "확률과 통계", "수학 I, II"])
        num_q = st.radio("문항 수", [5, 10, 30])
        if st.button("🚀 시험지 생성 시작"):
            model = get_working_model(API_KEY)
            if model:
                st.success(f"✅ 연결 성공! 사용 모델: {model.model_name}")
                # 여기에 문제 생성 로직 실행 (테스트를 위해 간단히 출력)
                try:
                    response = model.generate_content(f"수능 수학 {subject} 문제 1개만 HTML로 만들어줘.")
                    st.write(response.text)
                except Exception as e:
                    st.error(f"생성 중 오류: {e}")
            else:
                st.error("❌ 모든 모델 연결에 실패했습니다. API 키가 활성화되었는지 확인해주세요.")

