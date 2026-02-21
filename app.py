import streamlit as st
import google.generativeai as genai
import time

# 1. 페이지 설정
st.set_page_config(page_title="2026 수능 수학 테스트 모드", page_icon="🧪", layout="wide")

# [HTML_TEMPLATE 디자인 부분은 이전과 동일하게 유지]
HTML_TEMPLATE = """
<div style="font-family: 'Batang', serif; padding: 20px; background: white; border: 1px solid #ddd;">
    <h2 style="text-align:center;">2026학년도 수능 수학 모의고사 (테스트)</h2>
    <div style="column-count: 2; column-gap: 40px;">{questions}</div>
</div>
"""

# 2. 사이드바 - 모델 및 키 설정
with st.sidebar:
    st.title("🧪 테스트 컨트롤 타워")
    st.markdown("---")
    
    # [핵심] 모델 선택 기능 - 한도 초과 시 8B로 전환 유도
    selected_model = st.selectbox(
        "사용할 AI 모델 선택",
        ["gemini-1.5-flash-8b", "gemini-1.5-flash", "gemini-2.0-flash"],
        index=0,
        help="한도 초과(429)가 계속 뜨면 8B 모델을 선택하세요."
    )
    
    st.info(f"현재 선택된 모델: **{selected_model}**")
    
    # 비상용 개인 키 입력 (새 계정용)
    emergency_key = st.text_input("비상용 API Key 입력", type="password")
    st.link_button("🌐 새 키 발급받기", "https://aistudio.google.com/app/apikey")
    st.markdown("---")
    
    sub_opt = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
    num_opt = st.slider("테스트 문항 수", 1, 10, 5)

# 3. 테스트 전용 생성 엔진
def run_test_generation(subject, total, model_name, extra_key):
    all_qs = ""
    progress_bar = st.progress(0)
    
    # 키 결정 (입력된 비상키 > 기존 10배럭의 첫 번째 키)
    api_key = extra_key if extra_key else st.secrets["API_KEYS"][0]
    genai.configure(api_key=api_key)
    
    try:
        model = genai.GenerativeModel(model_name)
        
        for i in range(1, total + 1):
            st.write(f"🔄 {i}번 문항 생성 시도 중...")
            
            # 8B 모델은 지능이 낮으므로 프롬프트를 더 단순하고 명확하게 전달
            prompt = f"수능 수학 {subject} {i}번 문제를 HTML <div class='question'> 형식으로 1개만 만들어줘. 수식은 $ 사용."
            
            response = model.generate_content(prompt)
            all_qs += response.text.replace('```html', '').replace('```', '')
            
            progress_bar.progress(i / total)
            # 8B라도 안전을 위해 3초간 휴식 (연속 차단 방지)
            time.sleep(3)
            
        return all_qs
    except Exception as e:
        st.error(f"❌ 에러 발생: {e}")
        if "429" in str(e):
            st.warning("⚠️ 8B 모델마저 한도에 도달했습니다. 새로운 구글 계정의 키가 필요합니다.")
        return None

# 4. 실행 버튼
if st.sidebar.button("🚀 테스트 발간 시작"):
    with st.spinner("테스트 엔진 가동 중..."):
        result = run_test_generation(sub_opt, num_opt, selected_model, emergency_key)
        if result:
            final_html = HTML_TEMPLATE.format(questions=result)
            st.components.v1.html(final_html, height=800, scrolling=True)
            st.success("✅ 테스트 생성이 완료되었습니다!")
