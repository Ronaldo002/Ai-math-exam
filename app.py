import streamlit as st
import google.generativeai as genai
import time

# 1. 모델 설정 (404 방지를 위해 순수 명칭 사용)
MODEL_NAME = 'gemini-2.0-flash'

st.set_page_config(page_title="2026 수능 수학 고속 마스터", page_icon="⚡", layout="wide")

# [HTML_TEMPLATE 디자인 부분은 기존의 완성된 버전을 유지합니다]

# 2. 고속 생성 엔진 (가변 지연 시간 적용)
def generate_fast_exam(subject, total, diff, user_key):
    all_qs = ""
    all_sols = ""
    progress_bar = st.progress(0)
    status_msg = st.empty()
    
    # 키 설정: 입력된 새 키를 1순위로 사용
    api_key = user_key if user_key and len(user_key) > 20 else st.secrets["API_KEYS"][0]
    genai.configure(api_key=api_key)
    
    # 새 키일 경우 기본 대기 시간을 1.5초로 단축 (기존 4초에서 대폭 개선)
    base_delay = 1.5 if user_key else 3.0
    
    i = 1
    while i <= total:
        try:
            model = genai.GenerativeModel(MODEL_NAME)
            status_msg.info(f"⚡ {i}번 문항 고속 생성 중... (모델: {MODEL_NAME})")
            
            # 프롬프트 최적화: 답변 속도를 높이기 위해 형식을 더 명확히 지시
            prompt = f"""
            수능 수학 {subject} {i}번 {diff} 문항 제작.
            인사말 없이 HTML <div class='question'>과 [해설시작] 뒤 <div class='sol-card'> 형식으로만 출력.
            수식은 $ 기호 사용, 백슬래시는 2개(\\\\)씩 입력.
            """
            
            response = model.generate_content(prompt)
            text = response.text.replace('```html', '').replace('```', '').strip()
            
            if "[해설시작]" in text:
                q, s = text.split("[해설시작]", 1)
                all_qs += q.strip()
                all_sols += s.strip()
                i += 1
                progress_bar.progress(min((i-1)/total, 1.0))
                
                # 성공 시 짧은 휴식 후 바로 다음 문항
                time.sleep(base_delay)
            else:
                time.sleep(1) # 형식 오류 시 살짝 쉬고 재시도
                continue
                
        except Exception as e:
            if "429" in str(e):
                status_msg.warning("⚠️ 한도 감지! 안전을 위해 10초간 엔진을 냉각합니다...")
                time.sleep(10) # 한도 초과 시 긴 휴식 후 재시도
                base_delay += 0.5 # 이후 속도를 조금 늦춤
                continue
            else:
                st.error(f"오류 발생: {e}")
                break
                
    return all_qs, all_sols

# 3. 사이드바 및 UI
with st.sidebar:
    st.title("⚡ 고속 생성 컨트롤러")
    # 새로 발급받으신 API 키를 여기에 입력하세요!
    user_api_key = st.text_input("🔑 새 API Key 입력", value="", type="password")
    st.divider()
    sub_opt = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
    num_opt = st.radio("문항 수", [5, 10, 30], index=0)
    diff_opt = st.select_slider("난이도", options=["표준", "준킬러", "킬러"], value="킬러")

if st.sidebar.button("🚀 고속 발간 시작"):
    with st.status("🔮 새로운 배럭 가동 중...") as status:
        qs, sols = generate_fast_exam(sub_opt, num_opt, diff_opt, user_api_key)
        if qs:
            # HTML_TEMPLATE에 데이터 채우기 (기존 디자인 유지)
            # final_html = HTML_TEMPLATE.format(subject=sub_opt, questions=qs, solutions=sols)
            # st.components.v1.html(final_html, height=1200, scrolling=True)
            st.success("✅ 고속 생성이 완료되었습니다!")
        status.update(label="발간 완료", state="complete")
