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
    st.error("Secrets 설정이 필요합니다!")
    st.stop()

db = TinyDB('user_registry.json')
User = Query()

SENDER_EMAIL = st.secrets.get("EMAIL_USER", "pgh001002@gmail.com")
SENDER_PASS = st.secrets.get("EMAIL_PASS", "gmjg cvsg pdjq hnpw")
ADMIN_EMAIL = "pgh001002@gmail.com"

# --- 2. 수능 표준 문항 구성 (분석 기반) ---
# 공통과목(22문항) + 선택과목(8문항) = 30문항 풀세트
def get_exam_blueprint(choice_subject):
    blueprint = []
    # 1~22번: 공통과목 (수학 I, II)
    for i in range(1, 23):
        diff = "쉬움(2점)" if i <= 2 else "보통(3점)" if i <= 8 else "준킬러(4점)"
        if i in [15, 21, 22]: diff = "킬러(고난도)" # 수능 킬러 번호 배치
        blueprint.append({"num": i, "sub": "수학 I, II", "diff": diff})
    
    # 23~30번: 선택과목
    for i in range(23, 31):
        diff = "기초(2,3점)" if i <= 27 else "고난도(4점)"
        if i == 30: diff = "최종 킬러"
        blueprint.append({"num": i, "sub": choice_subject, "diff": diff})
    
    return blueprint

# --- 3. HTML/CSS 템플릿 (PDF 분석 반영) ---
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
            .paper {{ 
                background: white; width: 210mm; margin: 20px auto; padding: 15mm; 
                min-height: 297mm; position: relative; page-break-after: always;
                box-shadow: 0 0 10px rgba(0,0,0,0.1); 
            }}
            .header {{ text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 30px; }}
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 50px; min-height: 220mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #eee; }}
            .question-box {{ position: relative; line-height: 1.8; font-size: 10.5pt; padding-left: 35px; margin-bottom: 30px; }}
            .q-num {{ position: absolute; left: 0; top: 0; font-weight: bold; border: 1.8px solid #000; width: 25px; height: 25px; text-align: center; line-height: 23px; font-size: 11pt; }}
            .sol-section {{ page-break-before: always; border-top: 5px double #000; padding-top: 40px; }}
            mjx-container {{ vertical-align: middle !important; margin: 0 2px !important; }}
        </style>
    </head>
    <body>
        <div id="exam-paper-container">
            {pages_html}
            <div class="paper sol-section"><h2 style="text-align:center;">[정답 및 해설]</h2>{solutions_html}</div>
        </div>
    </body>
    </html>
    """

# --- 4. AI 생성 로직 (30문항 초고속 병렬 처리) ---
def fetch_paged_question(q_info):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"""
    당신은 수능 출제 위원입니다. {q_info['sub']} {q_info['diff']} 난이도 {q_info['num']}번 문항을 출제하세요.
    - 불필요한 인사말이나 제목(##...) 절대 금지. 오직 HTML만 출력.
    - 수식은 $ LaTeX 형식을 사용.
    형식: [문항] <div class='question-box'><span class='q-num'>{q_info['num']}</span> 문제내용...</div> ---SPLIT--- [해설] <div><b>{q_info['num']}번 해설:</b> 풀이...</div>
    """
    try:
        response = model.generate_content(prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except: return f"Error {q_info['num']}"

def generate_full_mock_exam(choice_subject):
    blueprint = get_exam_blueprint(choice_subject)
    
    # 30문항을 10개의 스레드로 병렬 생성 (속도 극대화)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_paged_question, blueprint))
    
    pages_html, sol_html = "", ""
    # 2문항씩 페이지 분할
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
st.set_page_config(page_title="Ultra Premium 수능 출제 시스템", layout="wide")

if 'verified' not in st.session_state: st.session_state.verified = False

with st.sidebar:
    st.title("🎓 모의고사 출제 본부")
    email_input = st.text_input("이메일 입력", value=ADMIN_EMAIL if st.session_state.verified else "")
    
    if email_input == ADMIN_EMAIL:
        st.session_state.verified = True
        st.success("👑 관리자 자동 인증 완료")
    
    if st.session_state.verified:
        st.divider()
        mode = st.radio("발간 모드", ["단일 문항 생성", "30문항 풀세트 발간"])
        choice_sub = st.selectbox("선택과목", ["미적분", "확률과 통계", "기하"])
        if st.button("🚀 모의고사 발간 시작"):
            with st.spinner("AI 출제위원 30명이 동시에 시험지를 제작 중입니다..."):
                p, s = generate_full_mock_exam(choice_sub)
                st.components.v1.html(get_html_template(choice_sub, p, s), height=1200, scrolling=True)

if not st.session_state.verified:
    st.info("💡 이메일을 입력하면 시스템이 활성화됩니다.")
