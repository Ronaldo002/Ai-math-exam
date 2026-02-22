import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
import concurrent.futures
import time

# --- 1. API 설정 ---
genai.configure(api_key=st.secrets["PAID_API_KEY"])

# --- 2. 수식 교정 AI 프롬프트 (핵심) ---
def validate_formula(raw_text):
    """생성된 문제의 수식 문법을 교정하는 보조 AI"""
    model = genai.GenerativeModel('gemini-1.5-flash') # 교정은 가벼운 모델로 빠르게
    check_prompt = f"""
    다음은 수능 수학 문제이다. 아래 규칙에 따라 수식을 완벽하게 교정하라.
    1. 모든 수식은 반드시 $...$ 로 감싸져 있어야 한다.
    2. LaTeX 문법 오류(예: 괄호 불일치, 알 수 없는 기호)를 수정하라.
    3. 수식과 한글 텍스트 사이에 미세한 공백을 넣어 렌더링 시 겹침을 방지하라.
    4. HTML 태그는 그대로 유지하라.
    
    내용: {raw_text}
    """
    try:
        response = model.generate_content(check_prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except:
        return raw_text

# --- 3. HTML 템플릿 (CSS 보강) ---
def get_html_template(subject, questions_html, solutions_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700&display=swap');
            * {{ font-family: 'Nanum Myeongjo', serif !important; word-break: keep-all; }}
            body {{ background: #f0f2f6; padding: 20px; }}
            .paper {{ background: white; width: 210mm; margin: auto; padding: 15mm; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 40px; }}
            .question {{ position: relative; margin-bottom: 50px; padding-left: 35px; line-height: 1.8; }}
            .q-num {{ position: absolute; left: 0; border: 1.5px solid #000; width: 28px; height: 28px; text-align: center; font-weight: bold; line-height: 28px; }}
            /* 수식 깨짐 방지 핵심 CSS */
            mjx-container {{ font-size: 115% !important; margin: 0 4px !important; vertical-align: middle !important; }}
            .sol-section {{ page-break-before: always; border-top: 3px double #000; margin-top: 50px; padding-top: 30px; }}
        </style>
    </head>
    <body>
        <div class="paper">
            <h1 style="text-align:center;">2026학년도 수능 수학 모의평가 ({subject})</h1>
            <div class="grid">{questions_html}</div>
            <div class="sol-section"><h2 style="text-align:center;">[정답 및 해설]</h2>{solutions_html}</div>
        </div>
        <script>window.MathJax && MathJax.typesetPromise();</script>
    </body>
    </html>
    """

# --- 4. 병렬 처리 로직 ---
def process_full_task(i, subject, difficulty):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    # 1단계: 출제
    gen_prompt = f"수능 수학 {subject} {difficulty} {i}번 문항 출제. [문항] <div class='question'><span class='q-num'>{i}</span>...</div> ---SPLIT--- [해설] <div>{i}번 해설...</div>"
    raw_res = model.generate_content(gen_prompt).text
    
    # 2단계: 수식 교정 AI 가동
    clean_res = validate_formula(raw_res)
    return clean_res

# --- 5. UI ---
st.title("🎓 수능 수학 무결성 출제 시스템")
email = st.text_input("사용자 인증")
num = st.slider("문항 수", 1, 10, 5)

if st.button("🚀 초정밀 발간 시작"):
    with st.spinner("출제 AI와 수식 교정 AI가 협업 중입니다..."):
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(lambda i: process_full_task(i, "미적분", "킬러"), range(1, num + 1)))
        
        q_html = "".join([r.split("---SPLIT---")[0] for r in results if "---SPLIT---" in r])
        s_html = "".join([r.split("---SPLIT---")[1] for r in results if "---SPLIT---" in r])
        
        st.components.v1.html(get_html_template("미적분", q_html, s_html), height=1200, scrolling=True)
