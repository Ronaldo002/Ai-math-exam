import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
from datetime import datetime
import concurrent.futures

# --- 1. 환경 설정 및 보안 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("Secrets에 PAID_API_KEY를 등록해주세요!")
    st.stop()

# --- 2. [파일 분석 기반] 수능 전용 HTML/CSS 템플릿 ---
def get_html_template(subject, questions_html, solutions_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
        <style>
            /* 1. 수능 고유 폰트 및 글자 깨짐 방지 */
            @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
            
            * {{ 
                font-family: 'Nanum Myeongjo', serif !important; 
                -webkit-font-smoothing: antialiased;
                word-break: keep-all;
                box-sizing: border-box;
            }}
            
            body {{ background: #f4f7f9; padding: 0; margin: 0; color: #000; }}
            
            /* A4 용지 규격 복제 */
            .paper {{ 
                background: white; width: 210mm; margin: 30px auto; 
                padding: 15mm 15mm 20mm 15mm; box-shadow: 0 4px 20px rgba(0,0,0,0.15);
                min-height: 297mm; position: relative;
            }}

            /* 수능 시험지 상단 헤더 */
            .header {{ 
                text-align: center; border-bottom: 3px solid #000; 
                padding-bottom: 12px; margin-bottom: 40px; 
            }}
            .header h1 {{ font-size: 28pt; margin: 0; font-weight: 800; letter-spacing: -1px; }}
            .header h3 {{ font-size: 18pt; margin: 12px 0; font-weight: 700; }}

            /* 2단 그리드 (킬러 문항 최적화) */
            .question-grid {{ 
                display: grid; grid-template-columns: 1fr 1fr; 
                column-gap: 50px; row-gap: 60px; position: relative;
            }}
            
            /* 중앙 수직 구분선 */
            .question-grid::after {{
                content: ""; position: absolute; left: 50%; top: 0; bottom: 0;
                width: 1px; background-color: #ddd;
            }}

            /* 개별 문항 스타일 */
            .question {{ 
                position: relative; line-height: 1.9; font-size: 11pt; 
                padding-left: 38px; text-align: justify;
            }}

            /* 수능 특유의 정사각형 번호 박스 */
            .q-num {{ 
                position: absolute; left: 0; top: 2px;
                font-weight: bold; border: 2px solid #000; 
                width: 28px; height: 28px; text-align: center; 
                line-height: 25px; font-size: 13pt; background: #fff;
            }}

            /* 해설 섹션 완전 분리 (PDF 출력 시 자동 페이지 넘김) */
            .sol-section {{ 
                page-break-before: always; border-top: 5px double #000; 
                padding-top: 50px; margin-top: 80px; 
            }}
            .sol-item {{ 
                margin-bottom: 35px; padding: 20px; 
                border-bottom: 1px dashed #bbb; font-size: 10.5pt;
                background-color: #fcfcfc;
            }}

            /* 수식 렌더링 최적화 (글자 겹침 방지) */
            mjx-container {{ 
                display: inline-block; margin: 0 2px;
                vertical-align: middle; font-size: 108% !important; 
            }}

            .btn-download {{ 
                position: fixed; top: 25px; right: 25px; 
                padding: 15px 30px; background: #222; color: #fff; 
                border: none; border-radius: 6px; cursor: pointer; 
                font-weight: 700; z-index: 1000; box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            }}
            .btn-download:hover {{ background: #ff4b4b; }}
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
                <h2 style="text-align:center; font-weight:800; font-size:22pt;">[정답 및 해설]</h2>
                {solutions_html}
            </div>
        </div>
        <script>
            function downloadPDF() {{
                const element = document.getElementById('exam-paper');
                const opt = {{
                    margin: 0,
                    filename: '2026_수능_수학_모의평가.pdf',
                    image: {{ type: 'jpeg', quality: 1.0 }},
                    html2canvas: {{ scale: 3, useCORS: true }},
                    jsPDF: {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
                }};
                html2pdf().set(opt).from(element).save();
            }}
            // 수식 로드 후 강제 재렌더링
            window.MathJax && MathJax.typesetPromise();
        </script>
    </body>
    </html>
    """

# --- 3. 고속 병렬 생성 로직 (API 지연 시간 극복) ---
def fetch_question(i, subject, difficulty):
    # 진단 결과에서 확인된 최신 모델 사용
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"""
    당신은 한국 교육과정평가원 수능 출제 위원입니다. {subject} {difficulty} 난이도 {i}번 문항을 출제하세요.
    - 수식은 반드시 $...$ (인라인) 또는 $$...$$ (블록) LaTeX 형식을 지키세요.
    - 한국어는 깨지지 않게 표준 문체(~구하시오, ~이다)를 사용하세요.
    - 형식: [문항] <div class='question'><span class='q-num'>{i}</span> 문제내용...</div> ---SPLIT--- [해설] <div class='sol-item'><b>{i}번 해설:</b> 상세 풀이...</div>
    """
    try:
        response = model.generate_content(prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except Exception as e:
        return f"Error {i}: {str(e)}"

def generate_parallel(subject, difficulty, count):
    # AI 10명을 동시에 투입하여 킬러 문항도 빠르게 생성
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_question, i, subject, difficulty) for i in range(1, count + 1)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    # 번호 순서 정렬 및 조립
    q_final, s_final = [], []
    results.sort(key=lambda x: int(x.split('q-num\'>')[1].split('</span>')[0]) if 'q-num\'>' in x else 999)
    
    for raw in results:
        if "---SPLIT---" in raw:
            parts = raw.split("---SPLIT---")
            q_final.append(parts[0].replace("[문항]", ""))
            s_final.append(parts[1].replace("[해설]", ""))
    return "".join(q_final), "".join(s_final)

# --- 4. Streamlit UI 구성 ---
st.set_page_config(page_title="수능 시험지 완벽 복제 시스템", layout="wide")

with st.sidebar:
    st.title("🎓 수능 출제 본부")
    email = st.text_input("사용자 이메일 인증")
    st.divider()
    num = st.slider("발간 문항 수", 1, 30, 5)
    sub = st.selectbox("과목 선택", ["수학 I, II", "미적분", "확률과 통계"])
    diff = st.select_slider("난이도 설정", options=["표준", "준킬러", "킬러"])
    st.info("유료 API 병렬 모드로 속도와 품질을 동시에 잡았습니다.")

if email:
    if st.button("🚀 초고속 시험지 발간 및 수식 검수"):
        with st.spinner(f"AI 군단이 {num}개의 문항을 실시간 출제 중입니다..."):
            q_html, s_html = generate_parallel(sub, diff, num)
            final_content = get_html_template(sub, q_html, s_html)
            # 결과 렌더링
            st.components.v1.html(final_content, height=1200, scrolling=True)
else:
    st.info("이메일을 입력하면 출제 시스템이 활성화됩니다.")
