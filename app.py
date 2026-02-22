import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
from datetime import datetime
import concurrent.futures

# --- 1. 환경 설정 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("Secrets에 PAID_API_KEY를 등록해주세요!")
    st.stop()

# --- 2. [문제 해결 핵심] HTML/CSS 템플릿 ---
def get_html_template(subject, questions_html, solutions_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700&display=swap');
            
            /* 1번 해결: 글자 깨짐 방지 스타일 */
            * {{ font-family: 'Noto Serif KR', serif !important; -webkit-font-smoothing: antialiased; }}
            body {{ background: #f0f2f6; padding: 20px; color: #000; }}
            
            .paper {{ background: white; width: 210mm; margin: 0 auto; padding: 15mm; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
            .header {{ text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 30px; }}
            
            /* 3번 해결: 한 페이지 2문항 (강력한 2단 그리드) */
            .question-grid {{ 
                display: grid; 
                grid-template-columns: 1fr 1fr; 
                column-gap: 40px; 
                row-gap: 60px; 
                text-align: justify;
            }}
            .question {{ position: relative; line-height: 1.8; font-size: 1.05em; page-break-inside: avoid; }}
            .q-num {{ 
                display: inline-block;
                font-weight: bold; 
                border: 2px solid #000; 
                width: 30px; height: 30px; 
                text-align: center; line-height: 30px;
                margin-right: 10px; 
            }}
            
            /* 2번 해결: 문제/해설 완전 분리 */
            .sol-section {{ page-break-before: always; border-top: 4px double #000; padding-top: 40px; margin-top: 80px; }}
            .sol-item {{ margin-bottom: 40px; padding: 20px; background: #fcfcfc; border: 1px solid #eee; }}
            
            /* 수식 가독성 최적화 */
            mjx-container {{ margin: 10px 0 !important; font-size: 1.15em !important; }}
            
            .btn-download {{ position: fixed; top: 20px; right: 20px; padding: 15px 30px; background: #ff4b4b; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; z-index: 1000; }}
        </style>
    </head>
    <body>
        <button class="btn-download" onclick="downloadPDF()">📥 PDF 시험지 다운로드</button>
        <div id="exam-paper" class="paper">
            <div class="header">
                <h1>2026학년도 대학수학능력시험 모의평가</h1>
                <h3>수학 영역 ({subject})</h3>
            </div>
            <div class="question-grid">
                {questions_html}
            </div>
            <div class="sol-section">
                <h2 style="text-align:center;">[정답 및 해설]</h2>
                <div class="sol-container">
                    {solutions_html}
                </div>
            </div>
        </div>
        <script>
            function downloadPDF() {{
                const element = document.getElementById('exam-paper');
                const opt = {{
                    margin: 0,
                    filename: '2026_수능_수학_프리미엄.pdf',
                    html2canvas: {{ scale: 2, useCORS: true }},
                    jsPDF: {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
                }};
                html2pdf().set(opt).from(element).save();
            }}
            // 수식 렌더링 강제 실행
            window.onload = function() {{
                if (window.MathJax) {{ MathJax.typesetPromise(); }}
            }};
        </script>
    </body>
    </html>
    """

# --- 3. [4번 해결] AI 군단 병렬 생성 로직 ---
def fetch_question(i, subject, difficulty):
    # 진단 결과에서 확인된 가장 빠른 모델 사용
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"""
    수능 수학 {subject} {difficulty} 난이도 {i}번 문항을 출제하라.
    형식: [문항] <div class='question'><span class='q-num'>{i}</span> 문제내용...</div> ---SPLIT--- [해설] <div class='sol-item'><b>{i}번 정답 및 해설:</b> 풀이내용...</div>
    규칙: 수식은 반드시 $...$ 를 사용하고, 한국어 글자가 깨지지 않도록 표준 HTML 엔티티를 사용하지 말 것.
    """
    try:
        response = model.generate_content(prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except Exception as e:
        return f"Error {i}: {str(e)}"

def generate_parallel(subject, difficulty, count):
    # AI 8명을 동시에 투입하여 속도를 극대화합니다.
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_question, i, subject, difficulty) for i in range(1, count + 1)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    q_final, s_final = [], []
    # 결과 정렬 (번호순)
    results.sort(key=lambda x: int(x.split('<span class=\'q-num\'>')[1].split('</span>')[0]) if '<span class=\'q-num\'>' in x else 999)
    
    for raw in results:
        if "---SPLIT---" in raw:
            parts = raw.split("---SPLIT---")
            q_final.append(parts[0].replace("[문항]", ""))
            s_final.append(parts[1].replace("[해설]", ""))
    return "".join(q_final), "".join(s_final)

# --- 4. UI 구성 ---
st.set_page_config(page_title="Ultra Premium 수능 수학", layout="wide")

with st.sidebar:
    st.title("🎓 Ultra Premium v2")
    email = st.text_input("사용자 이메일")
    num = st.slider("문항 수", 1, 30, 5)
    sub = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
    diff = st.select_slider("난이도", options=["표준", "준킬러", "킬러"])

if email:
    if st.button("🚀 초고속 AI 군단 발간 시작"):
        with st.spinner(f"AI 8명이 동시에 {num}문항을 제작 중입니다..."):
            q_html, s_html = generate_parallel(sub, diff, num)
            final_content = get_html_template(sub, q_html, s_html)
            st.components.v1.html(final_content, height=1200, scrolling=True)
else:
    st.info("이메일 입력 후 시작하세요.")
