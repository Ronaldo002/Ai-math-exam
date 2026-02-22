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
    st.error("Secrets 설정(API_KEY, EMAIL_USER, EMAIL_PASS)이 필요합니다!")
    st.stop()

db = TinyDB('user_registry.json')
User = Query()

# 관리자 및 이메일 설정 (알려주신 암호 반영)
SENDER_EMAIL = st.secrets.get("EMAIL_USER", "pgh001002@gmail.com")
SENDER_PASS = st.secrets.get("EMAIL_PASS", "gmjg cvsg pdjq hnpw")
ADMIN_EMAIL = "pgh001002@gmail.com"

# --- 2. [핵심] HTML/CSS 템플릿 (수식 깨짐 방지 최적화) ---
def get_html_template(subject, pages_html, solutions_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script>
            window.MathJax = {{
                tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$']] }},
                svg: {{ fontCache: 'global' }},
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
            /* 2단 그리드 레이아웃 */
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 50px; height: 180mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #eee; }}
            .question-box {{ position: relative; line-height: 1.8; font-size: 10.5pt; padding-left: 35px; text-align: justify; }}
            /* 정사각형 번호 박스 */
            .q-num {{ position: absolute; left: 0; top: 0; font-weight: bold; border: 1.8px solid #000; width: 25px; height: 25px; text-align: center; line-height: 23px; font-size: 11pt; }}
            .sol-section {{ page-break-before: always; border-top: 5px double #000; padding-top: 40px; }}
            .sol-item {{ margin-bottom: 25px; border-bottom: 1px dashed #ddd; padding-bottom: 10px; }}
            mjx-container {{ vertical-align: middle !important; margin: 0 2px !important; }}
        </style>
    </head>
    <body>
        <div id="exam-paper-container">
            {pages_html}
            <div class="paper sol-section"><h2 style="text-align:center;">[정답 및 해설]</h2>{solutions_html}</div>
        </div>
        <script>
            // 수식 렌더링 강제 실행 트리거
            window.onload = function() {{ if (window.MathJax) {{ MathJax.typesetPromise(); }} }};
        </script>
    </body>
    </html>
    """

# --- 3. [핵심] AI 생성 로직 (불필요 문구 제거용 프롬프트 지시) ---
def fetch_question(i, sub, diff):
    # 가장 안정적인 모델로 설정
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    
    # 이미지 f7eeb9의 문제를 해결하기 위해 "인사말 금지" 및 "HTML 태그만 출력" 강조
    prompt = f"""
    당신은 수능 출제 위원입니다. {sub} {diff} 난이도 {i}번 문항을 만드세요.
    
    [필수 규칙]
    1. "## 수능 수학..." 같은 제목이나 인사말, 설명 등 쓸데없는 문구를 절대 포함하지 마세요. 
    2. 오직 아래의 [형식]에 맞춘 HTML 코드만 출력하세요.
    3. 수식은 $ 기호를 사용한 LaTeX로 작성하세요.
    
    [형식]
    [문항] <div class='question-box'><span class='q-num'>{i}</span> 문제내용...</div> ---SPLIT--- [해설] <div class='sol-item'><b>{i}번 해설:</b> 풀이...</div>
    """
    try:
        response = model.generate_content(prompt)
        # 불필요한 마크다운 기호 제거
        clean_text = response.text.replace("```html", "").replace("```", "").strip()
        return clean_text
    except:
        return f"Error {i}"

def generate_exam_paged(sub, diff, num):
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda i: fetch_question(i, sub, diff), range(1, num + 1)))
    
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
            <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h3>수학 영역 ({sub})</h3></div>
            <div class="question-grid">{q_content}</div>
        </div>
        """
    return pages_html, sol_html

# --- 4. 이메일 인증 및 UI 로직 (기존 유지) ---
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
    except Exception as e:
        st.error(f"메일 발송 에러: {e}")
        return False

# --- 5. 메인 UI ---
st.set_page_config(page_title="Ultra Premium 수능 수학", layout="wide")

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
                    st.success("메일 발송 완료!")
        code_input = st.text_input("인증번호 6자리")
        if st.button("인증 확인"):
            if code_input == st.session_state.auth_code and st.session_state.auth_code:
                st.session_state.verified = True
                st.rerun()
    if st.session_state.verified:
        st.success(f"✅ 인증: {email_input}")
        num = st.slider("문항 수", 2, 30, 4, step=2)
        sub = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        diff = st.select_slider("난이도", options=["표준", "준킬러", "킬러"])

if st.session_state.verified:
    if st.button("🚀 프리미엄 시험지 발간"):
        with st.spinner("AI가 불필요한 문구를 제거하고 수식을 검수하며 출제 중입니다..."):
            pages, sols = generate_exam_paged(sub, diff, num)
            final_html = get_html_template(sub, pages, sols)
            st.components.v1.html(final_html, height=1200, scrolling=True)
else:
    st.info("이메일 인증을 완료하면 시스템이 활성화됩니다.")
