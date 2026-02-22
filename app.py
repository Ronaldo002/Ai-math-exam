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

# --- 2. [파일 분석 기반] 수능 스타일 HTML/CSS 템플릿 ---
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
            /* 실제 수능 시험지와 가장 유사한 나눔명조 폰트 적용 */
            @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
            
            * {{ 
                font-family: 'Nanum Myeongjo', serif !important; 
                -webkit-font-smoothing: antialiased;
                word-break: keep-all;
            }}
            
            body {{ background: #f0f2f6; padding: 0; margin: 0; color: #000; }}
            
            /* A4 규격 최적화 */
            .paper {{ 
                background: white; 
                width: 210mm; 
                margin: 20px auto; 
                padding: 15mm 15mm 20mm 15mm; 
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
                box-sizing: border-box;
            }}

            /* 수능 시험지 상단 헤더 */
            .header {{ 
                text-align: center; 
                border-bottom: 2px solid #000; 
                padding-bottom: 10px; 
                margin-bottom: 30px; 
                position: relative;
            }}
            .header h1 {{ font-size: 26pt; margin: 0; font-weight: 800; }}
            .header h3 {{ font-size: 16pt; margin: 10px 0; font-weight: 700; }}

            /* 2단 그리드 레이아웃 (수능 시험지 핵심) */
            .question-grid {{ 
                display: grid; 
                grid-template-columns: 1fr 1fr; 
                column-gap: 50px; 
                row-gap: 40px; 
                position: relative;
            }}
            
            /* 중앙 구분선 */
            .question-grid::after {{
                content: "";
                position: absolute;
                left: 50%;
                top: 0;
                bottom: 0;
                width: 1px;
                background-color: #ccc;
            }}

            .question {{ 
                position: relative; 
                line-height: 1.7; 
                font-size: 10.5pt; 
                padding-left: 35px;
                text-align: justify;
            }}

            /* 수능 특유의 정사각형 번호 박스 */
            .q-num {{ 
                position: absolute;
                left: 0;
                top: 0;
                font-weight: bold; 
                border: 1.5px solid #000; 
                width: 26px; 
                height: 26px; 
                text-align: center; 
                line-height: 26px;
                font-size: 12pt;
                background: white;
            }}

            /* 해설 섹션 분리 (PDF 출력 시 새 페이지) */
            .sol-section {{ 
                page-break-before: always; 
                border-top: 3px double #000; 
                padding-top: 40px; 
                margin-top: 60px; 
            }}
            .sol-item {{ 
                margin-bottom: 30px; 
                padding: 15px; 
                border-bottom: 1px dashed #ddd;
                font-size: 10pt;
            }}

            /* 수식 폰트 크기 미세조정 */
            mjx-container {{ font-size: 105% !important; }}

            .btn-download {{ 
                position: fixed; top: 20px; right: 20px; 
                padding: 15px 25px; background: #000; color: white; 
                border: none; border-radius: 4px; cursor: pointer; 
                font-weight: bold; z-index: 1000; 
            }}
        </style>
    </head>
    <body>
        <button class="btn-download" onclick="downloadPDF()">📥 PDF 저장</button>
        <div id="exam-paper" class="paper">
            <div class="header">
                <h1>2026학년도 대학수학능력시험 모의평가</h1>
                <h3>수학 영역 ({subject})</h3>
            </div>
            <div class="question-grid">
                {questions_html}
            </div>
            <div class="sol-section">
                <h2 style="text-align:center; font-weight:800;">[정답 및 해설]</h2>
                {solutions_html}
            </div>
        </div>
        <script>
            function downloadPDF() {{
                const element = document.getElementById('exam-paper');
                const opt = {{
                    margin: 0,
                    filename: '2026_수능_수학_모의평가.pdf',
                    html2canvas: {{ scale: 3, useCORS: true, logging: false }},
                    jsPDF: {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
                }};
                html2pdf().set(opt).from(element).save();
            }}
            window.MathJax && MathJax.typesetPromise();
        </script>
    </body>
    </html>
    """

# --- 3. 고속 병렬 생성 로직 ---
def fetch_question(i, subject, difficulty):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    # AI에게 수능 시험지 형식을 따르도록 강력히 지시
    prompt = f"""
    당신은 수능 출제 위원입니다. {subject} {difficulty} 난이도 {i}번 문항을 만드세요.
    반드시 수식은 $...$ 안에 LaTeX로 작성하고, 문장 끝은 '~구하시오.', '~이다.'로 끝내세요.
    형식: [문항] <div class='question'><span class='q-num'>{i}</span> 문제내용...</div> ---SPLIT--- [해설] <div class='sol-item'><b>{i}번 해설:</b> 풀이내용...</div>
    """
    try:
        response = model.generate_content(prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except Exception as e:
        return f"Error {i}: {str(e)}"

def generate_parallel(subject, difficulty, count):
    # AI 10명을 동시에 투입하여 속도 극대화
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_question, i, subject, difficulty) for i in range(1, count + 1)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    # 번호순으로 정렬하여 조립
    q_final, s_final = [], []
    results.sort(key=lambda x: int(x.split('q-num\'>')[1].split('</span>')[0]) if 'q-num\'>' in x else 999)
    
    for raw in results:
        if "---SPLIT---" in raw:
            parts = raw.split("---SPLIT---")
            q_final.append(parts[0].replace("[문항]", ""))
            s_final.append(parts[1].replace("[해설]", ""))
    return "".join(q_final), "".join(s_final)

# --- 4. Streamlit UI ---
st.set_page_config(page_title="2026 수능 수학 복제기", layout="wide")

with st.sidebar:
    st.title("🎓 수능 출제 시스템")
    email = st.text_input("사용자 인증(이메일)")
    num = st.slider("생성 문항 수", 1, 30, 5)
    sub = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
    diff = st.select_slider("난이도", options=["표준", "준킬러", "킬러"])

if email:
    if st.button("🚀 초고속 시험지 발간"):
        with st.spinner(f"AI 출제 위원 {num}명이 동시에 문제를 검수 중입니다..."):
            q_html, s_html = generate_parallel(sub, diff, num)
            final_content = get_html_template(sub, q_html, s_html)
            st.components.v1.html(final_content, height=1200, scrolling=True)
else:
    st.info("이메일을 입력하면 출제 시스템이 활성화됩니다.")
