import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
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

SENDER_EMAIL = st.secrets.get("EMAIL_USER", "pgh001002@gmail.com")
SENDER_PASS = st.secrets.get("EMAIL_PASS", "gmjg cvsg pdjq hnpw")
ADMIN_EMAIL = "pgh001002@gmail.com"

# --- 2. 이메일 인증 및 권한 로직 ---
def send_verification_email(receiver_email, code):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = receiver_email
        msg['Subject'] = "[Premium 수능수학] 인증번호 발송"
        msg.attach(MIMEText(f"안녕하세요. 요청하신 인증번호는 [{code}] 입니다.\n화면에 번호를 입력하여 인증을 완료해 주세요.", 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASS)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"메일 발송 에러: {e}")
        return False

def check_user_limit(email):
    if email == ADMIN_EMAIL:
        return True, "무제한 (관리자)"
    
    user = db.table('users').get(User.email == email)
    if not user:
        db.table('users').insert({'email': email, 'count': 0})
        return True, 5
    
    remaining = 5 - user['count']
    return (remaining > 0), remaining

# --- 3. 수능 표준 블루프린트 (배점 포함) ---
def get_exam_blueprint(choice_subject, total_num):
    blueprint = []
    if total_num == 30:
        for i in range(1, 23):
            if i <= 2: score = 2; diff = "쉬움"
            elif i <= 8: score = 3; diff = "보통"
            elif i in [15, 21, 22]: score = 4; diff = "킬러(고난도)"
            else: score = 4; diff = "준킬러"
            blueprint.append({"num": i, "sub": "수학 I, II", "diff": diff, "score": score})
        for i in range(23, 31):
            if i <= 24: score = 2; diff = "쉬움"
            elif i <= 27: score = 3; diff = "보통"
            elif i == 30: score = 4; diff = "최종 킬러"
            else: score = 4; diff = "준킬러"
            blueprint.append({"num": i, "sub": choice_subject, "diff": diff, "score": score})
    else:
        for i in range(1, total_num + 1):
            blueprint.append({"num": i, "sub": choice_subject, "diff": "표준", "score": 3})
    return blueprint

# --- 4. 디자인이 강화된 HTML/CSS 템플릿 ---
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
            * {{ font-family: 'Nanum Myeongjo', serif !important; word-break: keep-all; letter-spacing: -0.6px; }}
            body {{ background: #f0f2f6; margin: 0; padding: 0; color: #000; }}
            .paper-container {{ display: flex; flex-direction: column; align-items: center; padding: 20px 0; }}
            .paper {{ background: white; width: 210mm; padding: 15mm 18mm; margin-bottom: 30px; min-height: 297mm; position: relative; box-shadow: 0 5px 20px rgba(0,0,0,0.08); }}
            .header {{ text-align: center; border-bottom: 2.5px solid #000; padding-bottom: 12px; margin-bottom: 35px; }}
            .header h1 {{ font-weight: 800; font-size: 26pt; margin: 0; letter-spacing: -1.5px; }}
            .header h3 {{ font-weight: 700; font-size: 14pt; margin-top: 10px; }}
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 55px; min-height: 220mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #ddd; }}
            .question-box {{ position: relative; line-height: 1.85; font-size: 11pt; padding-left: 38px; margin-bottom: 45px; text-align: justify; }}
            .q-num {{ position: absolute; left: 0; top: 2px; font-weight: 800; border: 2px solid #000; width: 26px; height: 26px; text-align: center; line-height: 23px; font-size: 12pt; background: #fff; }}
            .q-score {{ font-weight: 700; font-size: 10.5pt; margin-left: 5px; }}
            .sol-section {{ border-top: 5px double #000; padding-top: 40px; }}
            .sol-item {{ margin-bottom: 30px; padding-bottom: 15px; border-bottom: 1px dashed #eee; line-height: 1.7; }}
            mjx-container {{ vertical-align: middle !important; margin: 0 3px !important; }}
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

# --- 5. 속도 극대화 30스레드 병렬 생성 ---
def fetch_paged_question(q_info):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"""
    당신은 수능 출제 위원입니다. {q_info['sub']} {q_info['diff']} 난이도 {q_info['num']}번 문항을 출제하세요. 배점은 {q_info['score']}점입니다.
    - 인사말 금지. 오직 HTML 태그만 출력. 수식은 $ LaTeX 사용.
    형식: [문항] <div class='question-box'><span class='q-num'>{q_info['num']}</span> 문제내용... <span class='q-score'>[{q_info['score']}점]</span></div> ---SPLIT--- [해설] <div class='sol-item'><b>{q_info['num']}번 해설:</b> 풀이...</div>
    """
    try:
        response = model.generate_content(prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except: return f"Error {q_info['num']}"

def generate_exam(choice_subject, total_num):
    blueprint = get_exam_blueprint(choice_subject, total_num)
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        results = list(executor.map(fetch_paged_question, blueprint))
    
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

# --- 6. UI 및 세션 관리 (인증 로직 완벽 복구) ---
st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")

# 세션 초기화
if 'verified' not in st.session_state: st.session_state.verified = False
if 'auth_code' not in st.session_state: st.session_state.auth_code = None
if 'mail_sent' not in st.session_state: st.session_state.mail_sent = False

with st.sidebar:
    st.title("🎓 본부 인증")
    email_input = st.text_input("이메일 입력", value=ADMIN_EMAIL if st.session_state.verified else "")
    
    # 관리자 자동 패스
    if email_input == ADMIN_EMAIL:
        st.session_state.verified = True
        st.success("👑 관리자 자동 인증 완료")
    
    # 일반 사용자 OTP 인증 로직
    if not st.session_state.verified:
        if st.button("인증번호 발송"):
            if email_input:
                code = str(random.randint(100000, 999999))
                if send_verification_email(email_input, code):
                    st.session_state.auth_code = code
                    st.session_state.mail_sent = True
                    st.success("인증번호가 발송되었습니다! 메일함을 확인하세요.")
            else:
                st.warning("이메일을 입력하세요.")
        
        # 메일 발송이 성공해야만 인증번호 입력창과 확인 버튼이 나타납니다.
        if st.session_state.mail_sent:
            code_input = st.text_input("인증번호 6자리 입력")
            if st.button("인증 확인"):
                if code_input == st.session_state.auth_code and st.session_state.auth_code:
                    st.session_state.verified = True
                    st.session_state.mail_sent = False # 성공 시 초기화
                    st.rerun() # 화면 새로고침하여 발간 패널 표시
                else:
                    st.error("인증번호가 일치하지 않습니다. 다시 확인해 주세요.")

    # 인증 완료 후 컨트롤 패널
    if st.session_state.verified:
        st.divider()
        mode = st.radio("발간 모드", ["맞춤 문항 발간", "30문항 풀세트 발간"])
        choice_sub = st.selectbox("선택과목", ["미적분", "확률과 통계", "기하"])
        num = 30 if mode == "30문항 풀세트 발간" else st.slider("문항 수", 2, 10, 4, step=2)
        generate_btn = st.button("🚀 초고속 시험지 발간 시작")

# --- 7. 메인 화면 (시험지 렌더링 및 횟수 제한) ---
if st.session_state.verified:
    can_use, remain = check_user_limit(email_input)
    if can_use:
        st.info(f"📊 이용 가능 횟수: {remain}")
        if 'generate_btn' in locals() and generate_btn:
            with st.spinner(f"AI 코어 30개가 동시에 {num}문항을 렌더링 중입니다..."):
                p, s = generate_exam(choice_sub, num)
                st.components.v1.html(get_html_template(choice_sub, p, s), height=1200, scrolling=True)
                
                # 생성 완료 시 일반 유저만 카운트 증가
                if email_input != ADMIN_EMAIL:
                    user_data = db.table('users').get(User.email == email_input)
                    db.table('users').update({'count': user_data['count'] + 1}, User.email == email_input)
    else:
        st.error("🚫 이용 한도(계정당 5회)를 모두 소진했습니다.")
else:
    st.info("💡 좌측 사이드바에서 이메일 인증을 완료하면 시스템이 활성화됩니다.")
