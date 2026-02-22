import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
from datetime import datetime
import concurrent.futures
import time

# --- 1. 환경 설정 및 API 보안 ---
# Streamlit Secrets에 PAID_API_KEY가 등록되어 있어야 합니다.
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("Secrets에 PAID_API_KEY를 등록해주세요!")
    st.stop()

# 사용자 데이터베이스 설정 (로컬에 user_registry.json 파일로 저장됨)
db = TinyDB('user_registry.json')
User = Query()

# [중요] 관리자 이메일 설정 (본인의 이메일 주소를 여기에 넣으세요)
# 이 이메일은 횟수 제한 없이 무제한으로 사용 가능합니다.
ADMIN_EMAIL = "your-email@example.com" 

# --- 2. 사용자 인증 및 권한 관리 함수 ---
def check_user_auth(email):
    """사용자의 이메일을 확인하고 남은 이용 횟수를 반환합니다."""
    # 관리자 이메일은 무조건 통과 (무제한)
    if email == ADMIN_EMAIL:
        return True, "무제한 (관리자)"
    
    today = datetime.now().strftime("%Y-%m-%d")
    user = db.table('users').get(User.email == email)
    
    if not user:
        # 신규 사용자 등록 (기본 0회 사용부터 시작)
        db.table('users').insert({'email': email, 'count': 0, 'last_date': today})
        return True, 5
    
    # 계정당 총 5회 제한 (필요 시 날짜별 초기화 로직으로 변경 가능)
    remaining = 5 - user['count']
    if remaining > 0:
        return True, remaining
    else:
        return False, 0

def update_usage_count(email):
    """생성이 완료되면 사용 횟수를 1 차감(기록상 1 증가)합니다."""
    if email == ADMIN_EMAIL:
        return
    user = db.table('users').get(User.email == email)
    db.table('users').update({'count': user['count'] + 1}, User.email == email)

# --- 3. [분석 기반] 수능 스타일 HTML/CSS 템플릿 ---
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
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
            
            * {{ font-family: 'Nanum Myeongjo', serif !important; word-break: keep-all; }}
            body {{ background: #f0f2f6; margin: 0; padding: 0; color: #000; }}
            
            .paper {{ 
                background: white; width: 210mm; margin: 20px auto; 
                padding: 15mm 15mm 25mm 15mm; box-shadow: 0 0 10px rgba(0,0,0,0.1);
                min-height: 297mm; box-sizing: border-box; position: relative;
                page-break-after: always;
            }}

            .header {{ text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 30px; }}
            .header h1 {{ font-size: 24pt; margin: 0; font-weight: 800; }}
            .header h3 {{ font-size: 14pt; margin: 8px 0; font-weight: 700; }}

            .question-grid {{ 
                display: grid; grid-template-columns: 1fr 1fr; 
                column-gap: 50px; height: 180mm; position: relative;
            }}
            
            .question-grid::after {{
                content: ""; position: absolute; left: 50%; top: 0; bottom: 0;
                width: 1px; background-color: #eee;
            }}

            .question-box {{ position: relative; line-height: 1.8; font-size: 10.5pt; padding-left: 35px; text-align: justify; }}
            .q-num {{ 
                position: absolute; left: 0; top: 0; font-weight: bold; 
                border: 1.5px solid #000; width: 25px; height: 25px; 
                text-align: center; line-height: 23px; font-size: 11pt;
            }}

            .sol-section {{ padding-top: 40px; }}
            .sol-item {{ margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px dashed #ddd; }}

            mjx-container {{ vertical-align: middle !important; margin: 0 2px !important; }}

            .btn-download {{ 
                position: fixed; top: 20px; right: 20px; 
                padding: 12px 24px; background: #000; color: #fff; 
                border: none; border-radius: 4px; cursor: pointer; 
                font-weight: bold; z-index: 1000; 
            }}
        </style>
    </head>
    <body>
        <button class="btn-download" onclick="downloadPDF()">📥 PDF 시험지 저장</button>
        <div id="exam-paper-container">
            {pages_html}
            <div class="paper sol-section">
                <h2 style="text-align:center; font-weight:800;">[정답 및 해설]</h2>
                {solutions_html}
            </div>
        </div>
        <script>
            function downloadPDF() {{
                const element = document.getElementById('exam-paper-container');
                const opt = {{
                    margin: 0,
                    filename: '2026_수능_수학_모의평가.pdf',
                    image: {{ type: 'jpeg', quality: 0.98 }},
                    html2canvas: {{ scale: 2, useCORS: true }},
                    jsPDF: {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
                }};
                html2pdf().set(opt).from(element).save();
            }}
            window.MathJax && MathJax.typesetPromise();
        </script>
    </body>
    </html>
    """

# --- 4. 고속 병렬 생성 로직 ---
def fetch_question(i, subject, difficulty):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"""
    당신은 수능 출제 위원입니다. {subject} {difficulty} 난이도 {i}번 문항을 출제하세요.
    수식은 LaTeX($)를 사용하고, 질문은 '~구하시오.'로 끝내세요.
    형식: [문항] <div class='question-box'><span class='q-num'>{i}</span> 문제내용...</div> ---SPLIT--- [해설] <div class='sol-item'><b>{i}번 해설:</b> 풀이...</div>
    """
    try:
        response = model.generate_content(prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except Exception as e:
        return f"Error {i}: {e}"

def generate_exam_paged(subject, difficulty, count):
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_question, i, subject, difficulty) for i in range(1, count + 1)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    results.sort(key=lambda x: int(x.split('q-num\'>')[1].split('</span>')[0]) if 'q-num\'>' in x else 999)
    
    pages_html, sol_html = "", ""
    for i in range(0, len(results), 2):
        pair = results[i:i+2]
        q_pair_content = ""
        for item in pair:
            if "---SPLIT---" in item:
                parts = item.split("---SPLIT---")
                q_pair_content += parts[0].replace("[문항]", "")
                sol_html += parts[1].replace("[해설]", "")
        
        pages_html += f"""
        <div class="paper">
            <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h3>수학 영역 ({subject})</h3></div>
            <div class="question-grid">{q_pair_content}</div>
        </div>
        """
    return pages_html, sol_html

# --- 5. Streamlit 메인 UI ---
st.set_page_config(page_title="2026 수능 수학 출제 시스템", layout="wide")

with st.sidebar:
    st.title("🎓 Premium 서비스")
    user_email = st.text_input("사용자 이메일 주소", placeholder="example@gmail.com")
    st.divider()
    num = st.slider("발간 문항 수", 2, 30, 4, step=2)
    sub = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
    diff = st.select_slider("난이도", options=["표준", "준킬러", "킬러"])

if user_email:
    # 횟수 및 인증 체크
    can_use, status = check_user_auth(user_email)
    
    if can_use:
        st.success(f"✅ 인증 성공! (남은 횟수: {status})")
        if st.button("🚀 프리미엄 시험지 발간"):
            with st.spinner("AI 출제 위원들이 문항을 제작 중입니다..."):
                pages, sols = generate_exam_paged(sub, diff, num)
                final_html = get_html_template(sub, pages, sols)
                st.components.v1.html(final_html, height=1200, scrolling=True)
                # 사용 후 횟수 업데이트
                update_usage_count(user_email)
    else:
        st.error(f"🚫 계정당 할당된 이용 횟수(5회)를 모두 소진하셨습니다.")
else:
    st.info("💡 사이드바에 이메일을 입력하면 서비스를 이용할 수 있습니다.")
