import streamlit as st
import google.generativeai as genai

st.title("🔍 서버 가용 모델 직접 조회")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    
    if st.button("목록 불러오기"):
        try:
            # 서버가 현재 이 키로 허용하는 모델 리스트를 가져옵니다.
            models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            st.write("✅ 당신의 키로 사용 가능한 모델 목록:")
            st.success(models)
            st.info("이 목록에 있는 이름을 복사해서 알려주시면 바로 해결됩니다!")
        except Exception as e:
            st.error(f"❌ 목록 조회조차 실패: {e}")

