import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
from datetime import datetime
import concurrent.futures
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 1. 환경 설정 및 API 보안 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("Secrets 설정(PAID_API_KEY, EMAIL_USER, EMAIL_PASS)이 필요합니다!")
    st.stop()

db = TinyDB('user_registry.json')
User = Query()

# 관리자 설정 (알려주신 정보 반영)
SENDER_EMAIL = st.secrets.get("EMAIL_USER", "pgh001002@gmail.com")
SENDER_PASS = st.secrets.get("EMAIL_PASS", "gmjg cvsg pdjq hnpw")
ADMIN_EMAIL = "pgh001002@gmail.com"

# --- 2. HTML/CSS 템플릿 (수식 및 불필요 문구 방어) ---
def get_html_template(subject, pages_html, solutions_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script>
            window.MathJax = {{
                tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$']] }},
                chtml: {{ scale: 1.02 }}
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
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 50px; height: 180mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #eee; }}
            .question-box {{ position: relative; line-height: 1.8; font-size: 10.5pt; padding-left: 35px; text-align: justify; }}
            .q-num {{ position: absolute; left: 0; top: 0; font-weight: bold; border: 1.8px solid #000; width: 25px; height: 25px; text-align: center; line-height: 23px; }}
            .sol-section {{ page-break-before: always; border-top: 5px double #000; padding-top: 40px; }}
            mjx-container {{ vertical-align: middle !important; margin: 0 2px !important; }}
        </style>
    </head>
    <body>
        {pages_html}
        <div class="paper sol-section"><h2 style="text-align:center;">[정답 및 해설]</h2>{solutions_html}</div>
    </body>
    </html>
    """

# --- 3. AI 생성 로직 (불필요 문구 엄격 제어) ---
def fetch_question(i, sub, diff):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"""
    당신은 수능 출제 위원입니다. {sub} {diff} 난이도 {i}번 문항을 만드세요.
    반드시 HTML 태그만 출력하고, 인사말이나 제목(##...)은 절대 쓰지 마세요.
    [형식]
    [문항] <div class='question-box'><span class='q-num'>{i}</span> 문제내용...</div> ---SPLIT--- [해설] <div class='sol-item'><b>{i}번 해설:</b> 풀이...</div>
    """
    try:
        response = model.generate_content(prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except: return f"Error {i}"

def generate_exam_paged(sub, diff, num):
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(lambda i: fetch_question(i, sub, diff), range(1, num + 1)))
    results.sort(key=lambda x: int(x.split('q-num\'>')[1].split('</span>')[0]) if 'q-num\'>' in x else 999)
    p_html, s_html = "", ""
    for i in range(0, len(results), 2):
        pair = results[i:i+2]
        q_cont = "".join([p.split("---SPLIT---")[0].replace("[문항]", "") for p in pair if "---SPLIT---" in p])
        s_html += "".join([p.split("---SPLIT---")[1].replace("[해설]", "") for p in pair if "---SPLIT---" in p])
        p_html += f"<div class='paper'><div class='header'><h1>2026 수능 모의평가</h1><h3>{sub}</h3></div><div class='question-grid'>{q_cont}</div></div>"
    return p_html, s_html

# --- 4. 이메일 발송 함수 ---
def send_verification_email(receiver_email, code):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = receiver_email
        msg['Subject'] = "[Premium 수능수학] 인증번호"
        msg.attach(MIMEText(f"인증번호는 [{code}] 입니다.", 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASS)
        server.send_message(msg)
        server.quit()
        return True
    except: return False

# --- 5. 메인 UI 및 인증 로직 ---
st.set_page_config(page_title="Ultra Premium 수능 수학", layout="wide")

# 세션 초기화
if 'verified' not in st.session_state: st.session_state.verified = False
if 'auth_code' not in st.session_state: st.session_state.auth_code = None

with st.sidebar:
    st.title("🎓 본부 인증")
    email_input = st.text_input("이메일 입력", value=ADMIN_EMAIL if st.session_state.verified else "")
    
    # [핵심 기능] 관리자 자동 인증 체크
    if email_input == ADMIN_EMAIL:
        st.session_state.verified = True
        st.success("👑 관리자 계정으로 자동 인증되었습니다.")
    
    if not st.session_state.verified:
        if st.button("인증번호 발송"):
            if email_input:
                code = str(random.randint(100000, 999999))
                if send_verification_email(email_input, code):
                    st.session_state.auth_code = code
                    st.success("메일 발송 완료!")
        
        code_input = st.text_input("인증번호 6자리")
        if st.button("인증 확인"):
            if code_input == st.session_state.auth_code and st.session_state.auth_code:
                st.session_state.verified = True
                st.rerun()
            else: st.error("번호가 일치하지 않습니다.")
    
    if st.session_state.verified:
        st.divider()
        num = st.slider("문항 수", 2, 30, 4, step=2)
        sub = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        diff = st.select_slider("난이도", options=["표준", "준킬러", "킬러"])
        if st.button("로그아웃"):
            st.session_state.verified = False
            st.rerun()

if st.session_state.verified:
    # 횟수 제한 체크 (관리자는 무제한)
    can_use = True
    if email_input != ADMIN_EMAIL:
        user = db.table('users').get(User.email == email_input)
        if not user: db.table('users').insert({'email': email_input, 'count': 0})
        user = db.table('users').get(User.email == email_input)
        can_use = user['count'] < 5
        st.info(f"📊 남은 이용 횟수: {5 - user['count']}회")

    if can_use:
        if st.button("🚀 프리미엄 시험지 발간"):
            with st.spinner("AI가 최적화된 수식으로 출제 중입니다..."):
                p, s = generate_exam_paged(sub, diff, num)
                st.components.v1.html(get_html_template(sub, p, s), height=1200, scrolling=True)
                if email_input != ADMIN_EMAIL:
                    db.table('users').update({'count': user['count'] + 1}, User.email == email_input)
    else: st.error("🚫 이용 한도를 초과했습니다.")
else:
    st.info("💡 이메일을 입력하면 시스템이 활성화됩니다.")
