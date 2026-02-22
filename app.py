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
# Streamlit Secrets에 아래 키들이 등록되어 있어야 합니다.
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("Secrets 설정(PAID_API_KEY, EMAIL_USER, EMAIL_PASS)이 필요합니다!")
    st.stop()

# DB 설정 (사용자 이용 기록 저장)
db = TinyDB('user_registry.json')
User = Query()

# 관리자 설정 (요청하신 이메일 반영)
SENDER_EMAIL = st.secrets.get("EMAIL_USER", "pgh001002@gmail.com")
SENDER_PASS = st.secrets.get("EMAIL_PASS", "gmjg cvsg pdjq hnpw")
ADMIN_EMAIL = "pgh001002@gmail.com"  # 이 계정은 무제한 이용 가능

# --- 2. 이메일 발송 및 인증 로직 ---
def send_verification_email(receiver_email, code):
    """사용자의 이메일로 6자리 인증번호 발송"""
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = receiver_email
        msg['Subject'] = "[Premium 수능수학] 시스템 접속 인증번호"
        
        body = f"안녕하세요. 요청하신 인증번호는 [{code}] 입니다.\n인증번호를 입력하여 시험지 발간 시스템에 접속하세요."
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASS)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"메일 발송 중 오류가 발생했습니다: {e}")
        return False

def check_user_limit(email):
    """관리자 무제한 및 일반 유저 5회 제한 체크"""
    if email == ADMIN_EMAIL:
        return True, "무제한 (관리자)"
    
    user = db.table('users').get(User.email == email)
    if not user:
        db.table('users').insert({'email': email, 'count': 0})
        return True, 5
    
    remaining = 5 - user['count']
    return (remaining > 0), remaining

# --- 3. 수능 스타일 HTML 템플릿 (2단 레이아웃 및 수식 최적화) ---
def get_html_template(subject, pages_html, solutions_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
            * {{ font-family: 'Nanum Myeongjo', serif !important; word-break: keep-all; }}
            body {{ background: #f0f2f6; margin: 0; padding: 0; }}
            .paper {{ 
                background: white; width: 210mm; margin: 20px auto; padding: 15mm; 
                min-height: 297mm; position: relative; page-break-after: always;
                box-shadow: 0 0 10px rgba(0,0,0,0.1); 
            }}
            .header {{ text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 30px; }}
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 50px; height: 180mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #eee; }}
            .question-box {{ position: relative; line-height: 1.8; font-size: 10.5pt; padding-left: 35px; }}
            .q-num {{ position: absolute; left: 0; top: 0; font-weight: bold; border: 1.8px solid #000; width: 25px; height: 25px; text-align: center; line-height: 23px; }}
            .sol-section {{ page-break-before: always; border-top: 5px double #000; padding-top: 40px; }}
            .btn-download {{ position: fixed; top: 20px; right: 20px; padding: 12px 24px; background: #000; color: #fff; border: none; cursor: pointer; z-index: 1000; font-weight: bold; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <button class="btn-download" onclick="window.print()">📥 PDF 시험지 저장</button>
        {pages_html}
        <div class="paper sol-section"><h2 style="text-align:center;">[정답 및 해설]</h2>{solutions_html}</div>
    </body>
    </html>
    """

# --- 4. AI 생성 로직 ---
def fetch_question(i, sub, diff):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"수능 수학 {sub} {diff} {i}번 출제. [문항] <div class='question-box'><span class='q-num'>{i}</span>...</div> ---SPLIT--- [해설] <div>{i}번 해설...</div>"
    res = model.generate_content(prompt)
    return res.text.replace("```html", "").replace("```", "").strip()

def generate_exam(sub, diff, num):
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

# --- 5. UI 및 세션 관리 ---
st.set_page_config(page_title="Premium 수능수학 출제시스템", layout="wide")

if 'verified' not in st.session_state: st.session_state.verified = False
if 'auth_code' not in st.session_state: st.session_state.auth_code = None

with st.sidebar:
    st.title("🎓 본부 인증")
    email_input = st.text_input("이메일 입력")
    
    if not st.session_state.verified:
        if st.button("인증번호 발송"):
            if email_input:
                code = str(random.randint(100000, 999999))
                if send_verification_email(email_input, code):
                    st.session_state.auth_code = code
                    st.success("인증 메일이 발송되었습니다!")
            else:
                st.warning("이메일을 입력해 주세요.")
        
        code_input = st.text_input("인증번호 6자리")
        if st.button("인증 확인"):
            if code_input == st.session_state.auth_code and st.session_state.auth_code is not None:
                st.session_state.verified = True
                st.rerun()
            else:
                st.error("인증번호가 일치하지 않습니다.")
    
    if st.session_state.verified:
        st.success(f"✅ 인증 완료: {email_input}")
        num = st.slider("문항 수", 2, 30, 4, step=2)
        sub = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        diff = st.select_slider("난이도", options=["표준", "준킬러", "킬러"])
        if st.button("로그아웃"):
            st.session_state.verified = False
            st.rerun()

if st.session_state.verified:
    can_use, remain = check_user_limit(email_input)
    if can_use:
        st.info(f"📊 이용 가능 횟수: {remain}")
        if st.button("🚀 프리미엄 시험지 발간"):
            with st.spinner("AI가 시험지를 제작하고 있습니다..."):
                p, s = generate_exam(sub, diff, num)
                st.components.v1.html(get_html_template(sub, p, s), height=1200, scrolling=True)
                # 관리자가 아닐 때만 횟수 차감
                if email_input != ADMIN_EMAIL:
                    user_data = db.table('users').get(User.email == email_input)
                    db.table('users').update({'count': user_data['count'] + 1}, User.email == email_input)
    else:
        st.error("🚫 이용 한도(5회)를 초과했습니다.")
else:
    st.info("💡 사이드바에서 이메일 인증을 완료하면 시스템이 활성화됩니다.")
