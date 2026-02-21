import streamlit as st
import google.generativeai as genai
import time

st.set_page_config(page_title="AI 시험지 생성기 v2", page_icon="📝")
st.title("📝 수능 모의고사 생성기 (안전 모드)")

# 1. API 키 설정
if "GEMINI_API_KEY" not in st.secrets:
    st.error("Secrets에 키가 없습니다! 설정을 확인해 주세요.")
else:
    api_key = st.secrets["GEMINI_API_KEY"]
    # 구글 서버 설정 초기화
    genai.configure(api_key=api_key)
    
    # 사이드바 설정
    st.sidebar.header("출제 옵션")
    subject = st.sidebar.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
    num_q = st.sidebar.slider("문항 수", 1, 10, 5) # 일단 5문제로 테스트

    if st.sidebar.button("🚀 출제 시작"):
        # [핵심] 404 에러를 피하기 위해 가장 낮은 사양의 모델을 정식 명칭으로 호출
        try:
            model = genai.GenerativeModel('gemini-1.5-flash-8b') # 가장 에러 없는 모델
            
            all_exam_text = ""
            progress_bar = st.progress(0)
            
            for i in range(1, num_q + 1):
                st.write(f"⏳ {i}번 문제 만드는 중...")
                
                # 아주 단순한 요청 (에러 방지용)
                prompt = f"수능 수학 {subject} 과목의 {i}번 문제를 HTML <div> 태그로 만들어줘. 수식은 ( )를 써줘."
                
                # 1문제씩 차례대로 호출
                response = model.generate_content(prompt)
                q_text = response.text.replace('```html', '').replace('```', '')
                
                # 화면에 즉시 표시
                st.markdown(q_text, unsafe_allow_html=True)
                all_exam_text += q_text
                
                # 무료 한도를 위해 2초씩 강제 휴식
                progress_bar.progress(i / num_q)
                time.sleep(2.0)
            
            st.success("✅ 출제 완료!")
            st.download_button("📥 결과 저장(HTML)", data=all_exam_text, file_name="exam.html")

        except Exception as e:
            # 에러 발생 시 아주 상세하게 출력하여 원인 파악
            st.error(f"❌ 접속 오류 발생: {e}")
            st.info("이 에러는 구글 서버가 일시적으로 거부하는 것입니다. 10분 뒤에 다시 시도해 보세요.")

