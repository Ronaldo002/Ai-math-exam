import streamlit as st
import google.generativeai as genai
import time

st.set_page_config(page_title="AI 모의고사 생성기", page_icon="📝", layout="wide")
st.title("📝 AI 수능 모의고사 생성기 (안전 모드)")

# 1. API 키 설정 (금고에서 가져오기)
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
except:
    st.error("API 키 설정에 문제가 있습니다. Streamlit Cloud의 Secrets 설정을 확인해주세요.")

# 2. 사이드바 설정
st.sidebar.header("설정")
subject = st.sidebar.selectbox("과목", ["미적분", "확률과 통계", "수학 I, II"])
num_questions_str = st.sidebar.radio("문항 수", ["5문항", "10문항", "30문항"])
total_q = int(num_questions_str.split("문항")[0])

# 3. 메인 로직
if st.sidebar.button("🚀 시험지 생성 시작"):
    all_content = ""
    progress_bar = st.progress(0)
    status_text = st.empty()
    display_area = st.container() # 문제가 하나씩 표시될 공간

    for i in range(1, total_q + 1):
        status_text.text(f"⏳ {total_q}문제 중 {i}번 문제를 만드는 중...")
        
        # AI에게 1문제씩만 요청 (가장 안전한 방법)
        prompt = f"수능 수학 {subject} 과목의 {i}번 문제를 HTML <div> 태그 형식으로 만들어줘. 수식은 MathJax를 사용하고, 다른 설명 없이 코드만 줘."
        
        try:
            response = model.generate_content(prompt)
            q_html = response.text.replace('```html', '').replace('```', '')
            all_content += q_html
            
            # 화면에 즉시 미리보기 업데이트
            with display_area:
                st.markdown(q_html, unsafe_allow_html=True)
            
            # 진행도 업데이트
            progress_bar.progress(i / total_q)
            
            # 무료 API 한도를 위해 아주 짧게 쉬기 (0.2초)
            time.sleep(0.2)
            
        except Exception as e:
            st.error(f"{i}번 생성 중 오류 발생. 잠시 후 다시 시도하거나 문항 수를 줄여주세요.")
            break

    status_text.success(f"✅ 총 {total_q}문제 생성 완료!")
    
    # 전체 다운로드 버튼
    st.download_button(
        label="📥 전체 시험지 HTML 다운로드",
        data=all_content,
        file_name="exam.html",
        mime="text/html"
    )
