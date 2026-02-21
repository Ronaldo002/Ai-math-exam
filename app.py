import streamlit as st
import google.generativeai as genai
import itertools
import time

# 1. 페이지 및 모델 설정
MODEL_NAME = 'gemini-2.0-flash'
st.set_page_config(page_title="2026 수능 수학 무한 마스터", page_icon="♾️", layout="wide")

# [HTML_TEMPLATE 디자인 및 PDF 다운로드 로직은 이전과 동일]
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script>
        window.MathJax = {{
            tex: {{
                inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
                displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
                processEscapes: true
            }}
        }};
    </script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
    <script>
        function downloadPDF() {{
            const element = document.querySelector('.paper');
            const opt = {{
                margin: [10, 10, 10, 10],
                filename: '2026_수능수학_모의고사.pdf',
                image: {{ type: 'jpeg', quality: 0.98 }},
                html2canvas: {{ scale: 2, useCORS: true }},
                jsPDF: {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
            }};
            html2pdf().set(opt).from(element).save();
        }}
    </script>
    <style>
        @page {{ size: A4; margin: 10mm; }}
        body {{ font-family: 'Batang', serif; line-height: 1.6; color: black; background: #f4f4f4; padding: 20px; }}
        .no-print {{ text-align: right; max-width: 210mm; margin: 0 auto 20px; }}
        .btn-download {{ padding: 12px 25px; background: #28a745; color: white; border: none; cursor: pointer; border-radius: 8px; font-weight: bold; }}
        .paper {{ max-width: 210mm; margin: 0 auto; background: white; padding: 15mm; min-height: 297mm; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; border-bottom: 2.5px solid black; padding-bottom: 10px; margin-bottom: 25px; }}
        .twocolumn {{ column-count: 2; column-gap: 45px; column-rule: 0.8px solid black; }}
        .question {{ margin-bottom: 250px; position: relative; padding-left: 30px; page-break-inside: avoid; word-break: keep-all; }}
        .q-num {{ font-weight: bold; font-size: 14pt; position: absolute; left: 0; top: 0; }}
        .solution-page {{ page-break-before: always; border-top: 3px double black; margin-top: 60px; padding-top: 40px; }}
        .sol-card {{ border: 1.5px solid #000; padding: 15px; margin-bottom: 25px; background: #fafafa; }}
        @media (max-width: 768px) {{
            .twocolumn {{ column-count: 1; }}
            .question {{ margin-bottom: 60px; }}
        }}
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-download" onclick="downloadPDF()">📥 PDF 직접 저장</button></div>
    <div class="paper">
        <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h2>수학 영역 ({subject})</h2></div>
        <div class="twocolumn">{questions}</div>
        <div class="solution-page">
            <h2 style="text-align:center; border: 2px solid black; display: inline-block; padding: 5px 30px; margin-bottom: 30px;">정답 및 상세 해설</h2>
            <div>{solutions}</div>
        </div>
    </div>
</body>
</html>
"""

# 2. 세션 상태 및 키 관리 로직
if "user_api_key" not in st.session_state:
    st.session_state.user_api_key = ""

if "API_KEYS" in st.secrets:
    admin_keys = list(st.secrets["API_KEYS"])
    if "key_pool" not in st.session_state:
        st.session_state.key_pool = {k: True for k in admin_keys}
else:
    st.error("Secrets 설정이 필요합니다.")
    st.stop()

def get_active_key():
    # 1순위: 브라우저 세션에 저장된 사용자 키
    if st.session_state.user_api_key and len(st.session_state.user_api_key) > 20:
        return st.session_state.user_api_key, "개인 배럭 (무한)"
    
    # 2순위: 관리자의 건강한 공용 키
    healthy_keys = [k for k, v in st.session_state.key_pool.items() if v]
    if healthy_keys:
        return healthy_keys[0], "공용 배럭 (체험용)"
    return None, None

# 3. 무중단 생성 엔진
def generate_infinity_exam(subject, total, diff):
    all_qs, all_sols = "", ""
    progress_bar = st.progress(0)
    status_msg = st.empty()
    
    i = 1
    while i <= total:
        current_key, key_desc = get_active_key()
        if not current_key:
            st.error("🚨 모든 배럭이 소진되었습니다! 개인 키를 입력하면 바로 재개됩니다.")
            break
            
        genai.configure(api_key=current_key)
        model = genai.GenerativeModel(MODEL_NAME)
        
        status_msg.info(f"⏳ {i}번 문항 생성 중... [사용 중: {key_desc}]")
        
        prompt = f"수능 수학 {subject} {i}번 킬러 문항 제작. 난이도: {diff}. HTML <div class='question'>과 [해설시작] 뒤 <div class='sol-card'> 형식으로 출력. 수식은 $ 사용."
        
        try:
            response = model.generate_content(prompt)
            text = response.text.replace('```html', '').replace('```', '').strip()
            text = text.replace('\\\\', '\\').replace('\\W', '\\')
            
            if "[해설시작]" in text:
                q, s = text.split("[해설시작]", 1)
                all_qs += q.strip()
                all_sols += s.strip()
                i += 1
                progress_bar.progress(min((i-1)/total, 1.0))
                time.sleep(2)
            else:
                continue
        except Exception as e:
            if "429" in str(e):
                if "개인" in key_desc:
                    st.warning("⚠️ 개인 키 한도 도달! 잠시 후 공용으로 전환합니다.")
                    st.session_state.user_api_key = "" # 세션 키 비우기
                else:
                    st.session_state.key_pool[current_key] = False
                continue
            else:
                st.error(f"오류: {e}")
                break
    return all_qs, all_sols

# 4. 사이드바 UI (로컬 기억 기능)
with st.sidebar:
    st.title("♾️ 무한 킬러 시스템")
    st.divider()
    st.subheader("🔑 내 API 키 기억하기")
    # 사용자가 입력하면 세션에 즉시 반영
    user_input = st.text_input(
        "Gemini API Key", 
        value=st.session_state.user_api_key,
        type="password", 
        help="한 번 입력하면 브라우저가 기억합니다."
    )
    if user_input != st.session_state.user_api_key:
        st.session_state.user_api_key = user_input
        st.success("키 저장 완료!")
    
    st.link_button("🌐 무료 키 10초 발급", "https://aistudio.google.com/app/apikey")
    st.divider()
    
    sub_opt = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
    num_opt = st.radio("문항 수", [5, 10, 30])
    diff_opt = st.select_slider("난이도", options=["표준", "준킬러", "킬러"], value="킬러")

if st.sidebar.button("🚀 무중단 발간"):
    with st.status("🔮 최적의 배럭을 찾아 문항 생성 중...") as status:
        qs, sols = generate_infinity_exam(sub_opt, num_opt, diff_opt)
        if qs:
            final_html = HTML_TEMPLATE.format(subject=sub_opt, questions=qs, solutions=sols)
            st.components.v1.html(final_html, height=1200, scrolling=True)
        status.update(label="작업 완료", state="complete")
