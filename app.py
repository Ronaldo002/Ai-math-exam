import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
from datetime import datetime
import time

# --- 1. 환경 설정 및 보안 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("Streamlit Secrets에 PAID_API_KEY를 등록해주세요!")
    st.stop()

db = TinyDB('service_data.json')
User = Query()

# --- 2. 시험지 HTML/CSS 템플릿 (수식 및 PDF 최적화) ---
# MathJax(수식)와 html2pdf(PDF저장) 라이브러리를 내장했습니다.
def get_html_template(subject, questions_html, solutions_html):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700&display=swap');
            body {{ font-family: 'Noto Serif KR', serif; background: #f0f2f6; padding: 20px; }}
            .paper {{ background: white; width: 210mm; margin: 0 auto; padding: 20mm; box-shadow: 0 0 10px rgba(0,0,0,0.1); min-height: 297mm; }}
            .header {{ text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 30px; }}
            .columns {{ display: flex; gap: 40px; }}
            .column {{ flex: 1; }}
            .question {{ margin-bottom: 40px; position: relative; line-height: 1.8; }}
            .q-num {{ font-weight: bold; margin-right: 10px; font-size: 1.2em; }}
            .sol-section {{ page-break-before: always; border-top: 3px double #000; padding-top: 40px; margin-top: 50px; }}
            .btn-download {{ position: fixed; top: 20px; right: 20px; padding: 12px 24px; background: #ff4b4b; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; z-index: 1000; }}
        </style>
    </head>
    <body>
        <button class="btn-download" onclick="downloadPDF()">📥 PDF 시험지 다운로드</button>
        <div id="exam-paper" class="paper">
            <div class="header">
                <h1>2026학년도 대학수학능력시험 모의평가</h1>
                <h3>수학 영역 ({subject})</h3>
            </div>
            <div class="columns">
                <div class="column">{questions_html}</div>
            </div>
            <div class="sol-section">
                <h2 style="text-align:center;">[정답 및 해설]</h2>
                {solutions_html}
            </div>
        </div>
        <script>
            function downloadPDF() {{
                const element = document.getElementById('exam-paper');
                const opt = {{
                    margin: 10,
                    filename: '2026_수능_수학_모의고사.pdf',
                    image: {{ type: 'jpeg', quality: 0.98 }},
                    html2canvas: {{ scale: 2 }},
                    jsPDF: {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
                }};
                html2pdf().set(opt).from(element).save();
            }}
        </script>
    </body>
    </html>
    """

# --- 3. 핵심 로직 ---
def check_user_access(email):
    today = datetime.now().strftime("%Y-%m-%d")
    user = db.table('users').get(User.email == email)
    if not user:
        db.table('users').insert({'email': email, 'count': 0, 'last_date': today})
        return True, 5
    if user['last_date'] != today:
        db.table('users').update({'count': 0, 'last_date': today}, User.email == email)
        return True, 5
    return (5 - user['count'] > 0), (5 - user['count'])

def generate_exam(subject, difficulty, count, email):
    model = genai.GenerativeModel('gemini-2.0-flash')
    q_html, s_html = "", ""
    progress = st.progress(0)
    
    for i in range(1, count + 1):
        st.write(f"✍️ {i}번 문항 출제 및 검수 중...")
        prompt = f"""
        수능 수학 {subject} {difficulty} 난이도 {i}번 문항을 출제하세요.
        - 문제내용은 <div class='question'><span class='q-num'>{i}.</span>내용</div> 형식으로 작성.
        - 수식은 반드시 $...$ (인라인) 또는 $$...$$ (블록) 형식을 지킬 것.
        - 해설은 <div class='sol'><b>{i}번 정답 및 해설:</b> 내용</div> 형식으로 작성.
        - [해설구분] 이라는 단어로 문제와 해설을 구분할 것.
        """
        try:
            response = model.generate_content(prompt)
            parts = response.text.split("[해설구분]")
            q_html += parts[0].replace("```html", "").replace("```", "")
            if len(parts) > 1:
                s_html += parts[1].replace("```html", "").replace("```", "")
            
            progress.progress(i / count)
            time.sleep(0.5)
        except:
            continue
            
    # 카운트 차감
    curr = db.table('users').get(User.email == email)['count']
    db.table('users').update({'count': curr + 1}, User.email == email)
    return get_html_template(subject, q_html, s_html)

# --- 4. UI ---
st.set_page_config(page_title="Premium 수능 수학 생성기", layout="wide")

with st.sidebar:
    st.title("🎓 Premium 모드")
    email = st.text_input("사용자 이메일")
    st.divider()
    num = st.slider("문항 수", 1, 30, 5)
    sub = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
    diff = st.select_slider("난이도", options=["표준", "준킬러", "킬러"])

if email:
    active, left = check_user_access(email)
    if active:
        if st.button("🚀 시험지 발간 및 PDF 생성"):
            final_html = generate_exam(sub, diff, num, email)
            st.components.v1.html(final_html, height=1200, scrolling=True)
    else:
        st.error("오늘의 발간 횟수를 모두 소진했습니다.")
else:
    st.info("이메일을 입력하면 프리미엄 엔진이 활성화됩니다.")
