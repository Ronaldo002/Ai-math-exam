import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
from datetime import datetime
import concurrent.futures

# --- 1. 환경 설정 및 API 연결 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("Secrets에 PAID_API_KEY를 등록해주세요!")
    st.stop()

# 사용자 데이터베이스 설정 (service_data.json 파일 생성)
db = TinyDB('user_registry.json')
User = Query()

# 질문자님의 이메일 (여기에 실제 이메일을 적으세요)
ADMIN_EMAIL = "your-email@example.com" 

# --- 2. [사용자 인증 로직] ---
def check_user_auth(email):
    # 관리자 이메일은 무조건 통과 (무제한)
    if email == ADMIN_EMAIL:
        return True, "무제한 (관리자)"
    
    today = datetime.now().strftime("%Y-%m-%d")
    user = db.table('users').get(User.email == email)
    
    if not user:
        # 신규 유저 등록 (오늘 0회 사용으로 시작)
        db.table('users').insert({'email': email, 'count': 0, 'last_date': today})
        return True, 5
    
    # 날짜가 바뀌었을 경우 횟수 초기화 여부는 정책에 따라 결정 (여기서는 누적 5회 제한 기준)
    # 만약 '하루 5회'를 원하시면 아래 주석을 해제하세요.
    # if user['last_date'] != today:
    #     db.table('users').update({'count': 0, 'last_date': today}, User.email == email)
    #     user['count'] = 0

    remaining = 5 - user['count']
    if remaining > 0:
        return True, remaining
    else:
        return False, 0

def update_usage_count(email):
    if email == ADMIN_EMAIL:
        return
    user = db.table('users').get(User.email == email)
    db.table('users').update({'count': user['count'] + 1}, User.email == email)

# --- 3. HTML/CSS 템플릿 (기존 수능 복제 버전 유지) ---
def get_html_template(subject, pages_html, solutions_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
            * {{ font-family: 'Nanum Myeongjo', serif !important; word-break: keep-all; }}
            body {{ background: #f0f2f6; margin: 0; padding: 0; }}
            .paper {{ background: white; width: 210mm; margin: 20px auto; padding: 15mm; min-height: 297mm; position: relative; page-break-after: always; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
            .header {{ text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 30px; }}
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 50px; height: 180mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #eee; }}
            .question-box {{ position: relative; line-height: 1.8; font-size: 10.5pt; padding-left: 35px; }}
            .q-num {{ position: absolute; left: 0; top: 0; font-weight: bold; border: 1.5px solid #000; width: 25px; height: 25px; text-align: center; line-height: 23px; }}
            .sol-section {{ page-break-before: always; padding-top: 40px; }}
            .btn-download {{ position: fixed; top: 20px; right: 20px; padding: 12px 24px; background: #000; color: #fff; border: none; cursor: pointer; z-index: 1000; font-weight: bold; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <button class="btn-download" onclick="window.print()">📥 PDF로 저장 (인쇄)</button>
        <div id="exam-paper-container">
            {pages_html}
            <div class="paper sol-section">
                <h2 style="text-align:center; font-weight:800;">[정답 및 해설]</h2>
                {solutions_html}
            </div>
        </div>
    </body>
    </html>
    """

# --- 4. 생성 로직 (병렬 처리) ---
def fetch_question(i, subject, difficulty):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"수능 수학 {subject} {difficulty} {i}번 문항 출제. [문항] <div class='question-box'><span class='q-num'>{i}</span>...</div> ---SPLIT--- [해설] <div>{i}번 해설...</div>"
    try:
        res = model.generate_content(prompt)
        return res.text.replace("```html", "").replace("```", "").strip()
    except: return f"Error {i}"

def generate_exam_paged(subject, difficulty, count):
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda i: fetch_question(i, subject, difficulty), range(1, count + 1)))
    
    results.sort(key=lambda x: int(x.split('q-num\'>')[1].split('</span>')[0]) if 'q-num\'>' in x else 999)
    pages_html, sol_html = "", ""
    
    for i in range(0, len(results), 2):
        pair = results[i:i+2]
        q_content = ""
        for item in pair:
            if "---SPLIT---" in item:
                p = item.split("---SPLIT---")
                q_content += p[0].replace("[문항]", "")
                sol_html += p[1].replace("[해설]", "")
        
        pages_html += f"""
        <div class="paper">
            <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h3>수학 영역 ({subject})</h3></div>
            <div class="question-grid">{q_content}</div>
        </div>
        """
    return pages_html, sol_html

# --- 5. Streamlit 메인 UI ---
st.set_page_config(page_title="수능 수학 출제 관리 시스템", layout="wide")

with st.sidebar:
    st.title("🎓 회원 전용 시스템")
    user_email = st.text_input("이메일 주소를 입력하세요", placeholder="example@gmail.com")
    st.divider()
    num = st.slider("문항 수", 2, 30, 4, step=2)
    sub = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
    diff = st.select_slider("난이도", options=["표준", "준킬러", "킬러"])

if user_email:
    # 인증 체크
    can_use, status = check_user_auth(user_email)
    
    if can_use:
        st.success(f"✅ 인증 완료! 남은 횟수: {status}")
        if st.button("🚀 프리미엄 시험지 발간"):
            with st.spinner("AI가 고퀄리티 문항을 생성 중입니다..."):
                pages, sols = generate_exam_paged(sub, diff, num)
                final_html = get_html_template(sub, pages, sols)
                st.components.v1.html(final_html, height=1200, scrolling=True)
                # 사용 후 횟수 차감
                update_usage_count(user_email)
    else:
        st.error("🚫 오늘(또는 계정당) 할당된 5회의 생성 기회를 모두 사용하셨습니다.")
else:
    st.info("💡 사이트를 이용하려면 왼쪽 사이드바에 이메일을 입력해 주세요.")
