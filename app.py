import streamlit as st
import google.generativeai as genai

st.title("🆘 최종 긴급 진단")

# 1. 키 읽기
if "GEMINI_API_KEY" not in st.secrets:
    st.error("Secrets에 키가 없습니다!")
else:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    # 2. 가장 낮은 사양의 모델로 딱 한 마디만 시도
    if st.button("🔌 서버 강제 연결 시도"):
        try:
            # 모든 복잡한 설정을 빼고 가장 기본형으로 호출
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content("hello")
            st.success("🎉 대박! 드디어 연결됐습니다!")
            st.write("AI 대답:", response.text)
        except Exception as e:
            st.error(f"❌ 구글 서버가 응답을 거부함: {e}")
            st.info("이 에러가 뜨면 키를 새로 뽑거나 1시간 뒤에 다시 해야 합니다.")


