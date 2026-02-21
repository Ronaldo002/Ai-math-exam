import streamlit as st
import google.generativeai as genai

st.set_page_config(page_title="최종 연결 테스트", page_icon="🎈")
st.title("🎈 신규 API 연결 최종 테스트")

# 1. Secrets에서 키 읽기
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
    
    st.info("⏳ 새 키로 구글 서버에 접속을 시도합니다...")

    if st.button("🚀 연결 확인하기"):
        # 가장 안정적인 기본 모델로 테스트
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        try:
            response = model.generate_content("성공했다면 '준비 완료'라고 한 마디만 해줘.")
            st.success(f"🎊 드디어 성공했습니다! AI 대답: {response.text}")
            st.balloons() # 화면에 풍선이 날아갑니다!
            
            st.markdown("---")
            st.write("✅ 이제 이 키로 모의고사 생성기를 돌릴 수 있습니다. 전체 코드를 합쳐드릴까요?")
            
        except Exception as e:
            st.error(f"❌ 접속 실패: {e}")
            st.info("팁: 새 프로젝트 키는 활성화까지 1~2분 정도 걸릴 수 있습니다. 잠시 후 다시 눌러보세요.")

except Exception as e:
    st.error(f"⚠️ Secrets 설정 오류: {e}")
