import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
import concurrent.futures
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 1. 환경 설정 및 API 보안 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("Secrets 설정(API_KEY, EMAIL_USER, EMAIL_PASS)이 필요합니다!")
    st.stop()

db = TinyDB('user_registry.json')
User = Query()

# 관리자 및 이메일 설정
SENDER_EMAIL = st.secrets.get("EMAIL_USER", "pgh001002@gmail.com")
SENDER_PASS = st.secrets.get("EMAIL_PASS", "gmjg cvsg pdjq hnpw")
ADMIN_EMAIL = "pgh001002@gmail.com"

# --- 2. 수능 표준 문항 구성 (PDF 분석 기반) ---
# 공통과목(1~22번) + 선택과목(23~30번) 배치
def get_exam_blueprint(choice_subject):
    blueprint = []
    # 공통과목 (수학 I, II)
    for i in range(1, 23):
        diff = "쉬움(2점)" if i <= 2 else "보통(3점)" if i <= 8 else "준킬러(4점)"
        if i in [15, 21, 22]: diff = "킬러(고난도)"
        blueprint.append({"num": i, "sub": "수학 I, II", "diff": diff})
    # 선택과목
    for i in range(23, 31):
        diff = "기초(2,3점)" if i <= 27 else "고난도(4점)"
        if i == 30: diff = "최종 킬러"
        blueprint.append({"num": i, "sub": choice_subject, "diff": diff})
    return blueprint

# --- 3. [1번 해결] 레이아웃 최적화 템플릿 ---
def get_html_template(subject, pages_html, solutions_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script>
            window.MathJax = {{
                tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$']] }},
                chtml: {{ scale: 1.05 }}
            }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
            * {{ font-family: 'Nanum Myeongjo', serif !important; word-break: keep-all; }}
            body {{ background: #f0f2f6; margin: 0; padding: 0; color: #000; }}
            /* 시험지 출력 위치 고정 */
            .paper-container {{ display: flex; flex-direction: column; align-items: center; padding: 20px 0; }}
            .paper {{ 
                background: white; width: 210mm; padding: 15mm; margin-bottom: 30px;
                min-height: 297mm; position: relative; box-shadow: 0 4px 15px rgba(0,0,0,0.1); 
            }}
            .header {{ text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 30px; }}
            /* 2단 그리드 레이아웃 */
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 50px; min-height: 220mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #eee; }}
            .question-box {{ position: relative; line-height: 1.8; font-size: 10.5pt; padding-left: 35px; margin-bottom: 40px; text-align: justify; }}
            /* 번호 박스 */
            .q-num {{ position: absolute; left: 0; top: 0; font-weight: bold; border: 1.8px solid #000; width: 25px; height: 25px; text-align: center; line-height: 23px; font-size: 11pt; }}
            .sol-section {{ border-top: 5px double #000; padding-top: 40px; }}
            mjx-container {{ vertical-align: middle !important; margin: 0 2px !important; }}
        </style>
    </head>
    <body>
        <div class="paper-container">
            {pages_html}
            <div class="paper sol-section"><h2 style="text-align:center;">[정답 및 해설]</h2>{solutions_html}</div>
        </div>
    </body>
    </html>
    """

# --- 4. [2번 해결] 초고속 병렬 생성 로직 ---
def fetch_paged_question(q_info):
    # 유료 모델 활용
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"""
    당신은 수능 출제 위원입니다. {q_info['sub']} {q_info['diff']} 난이도 {q_info['num']}번 문항을 출제하세요.
    - 인사말 금지. 오직 HTML 태그만 출력. 수식은 $ LaTeX 사용.
    형식: [문항] <div class='question-box'><span class='q-num'>{q_info['num']}</span> 문제내용...</div> ---SPLIT--- [해설] <div><b>{q_info['num']}번 해설:</b> 풀이...</div>
    """
    try:
        response = model.generate_content(prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except: return f"Error {q_info['num']}"

def generate_full_mock_exam(choice_subject):
    blueprint = get_exam_blueprint(choice_subject)
    # AI 15명을 동시에 투입하여 1분 이내 완성 (2번 문제 해결)
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        results = list(executor.map(fetch_paged_question, blueprint))
    
    # 번호순 정렬
    results.sort(key=lambda x: int(x.split('q-num\'>')[1].split('</span>')[0]) if 'q-num\'>' in x else 999)
    
    pages_html, sol_html = "", ""
    for i in range(0, len(results), 2):
        pair = results[i:i+2]
        q_content = ""
        for item in pair:
            if "---SPLIT---" in item:
                parts = item.split("---SPLIT---")
                q_content += parts[0].replace("[문항]", "")
                sol_html += parts[1].replace("[해설]", "")
        
        pages_html += f"""
        <div class="paper">
            <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h3>수학 영역 ({choice_subject})</h3></div>
            <div class="question-grid">{q_content}</div>
        </div>
        """
    return pages_html, sol_html

# --- 5. UI 및 인증 로직 ---
st.set_page_config(page_title="Premium 수능 시스템", layout="wide")
if 'verified' not in st.session_state: st.session_state.verified = False

with st.sidebar:
    st.title("🎓 모의고사 출제")
    email_input = st.text_input("이메일", value=ADMIN_EMAIL if st.session_state.verified else "")
    if email_input == ADMIN_EMAIL:
        st.session_state.verified = True
    
    if st.session_state.verified:
        st.divider()
        choice_sub = st.selectbox("선택과목", ["미적분", "확률과 통계", "기하"])
        generate_btn = st.button("🚀 30문항 풀세트 발간 시작")

# 메인 화면 영역 (1번 문제 해결: 발간 위치 고정)
if st.session_state.verified:
    if 'generate_btn' in locals() and generate_btn:
        with st.spinner("AI 군단이 30문항을 동시에 제작 중입니다 (약 45초 소요)..."):
            p, s = generate_full_mock_exam(choice_sub)
            st.components.v1.html(get_html_template(choice_sub, p, s), height=1200, scrolling=True)
else:
    st.info("이메일을 입력하면 시스템이 활성화됩니다.")
