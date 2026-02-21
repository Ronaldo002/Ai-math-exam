import streamlit as st
import google.generativeai as genai
import os

st.title("🚀 수능 모의고사 최종 연결 테스트")

# 환경변수를 통해 베타 버전 이슈를 원천 차단
os.environ["GOOGLE_API_USE_MTLS"] = "never"

if "GEMINI_API_KEY" not in st.secrets:
    st.error("Secrets 설정이 비어있습니다!")
else:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    if st.button("🔌 구글 서버에 접속 시도"):
        try:
            # v1beta 에러를 피하기 위해 모델 경로를 수동으로 지정
            model = genai.GenerativeModel(model_name='models/gemini-1.5-flash')
            response = model.generate_content("성공했다면 '축하합니다'라고 말해줘.")
            st.success(f"🎊 연결 성공! AI 대답: {response.text}")
            st.balloons()
        except Exception as e:
            st.error(f"❌ 여전히 서버 거부 중: {e}")
            st.info("이 에러가 계속된다면, 구글 계정을 바꿔서 새 키를 발급받는 것이 유일한 해결책입니다.")
