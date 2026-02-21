import streamlit as st
import google.generativeai as genai

st.title("🆘 API 연결 상태 점검")

# 1. 금고(Secrets)에 키가 있는지 확인
if "GEMINI_API_KEY" not in st.secrets:
    st.error("❌ 서버 금고(Secrets)에 'GEMINI_API_KEY'가 저장되어 있지 않습니다!")
    st.info("해결법: Streamlit Cloud 설정 -> Settings -> Secrets에 키를 입력했는지 확인하세요.")
else:
    st.success("✅ 금고에서 API 키를 찾았습니다.")
    
    try:
        # 2. 실제로 구글 서버에 인사해보기
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        with st.spinner("구글 AI에게 인사 건네는 중..."):
            response = model.generate_content("안녕? 연결 잘 됐니? 딱 한 마디만 해줘.")
            st.write("🤖 AI의 대답:", response.text)
            st.balloons() # 성공하면 풍선이 터집니다!
            
    except Exception as e:
        st.error(f"❌ 구글 서버 연결 실패: {e}")
        st.info("참고: API 키가 잘못되었거나, 무료 한도(RPM/RPD)를 초과했을 때 발생합니다.")
