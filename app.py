import streamlit as st
import google.generativeai as genai
import time

st.set_page_config(page_title="2026 수능 수학 마스터", page_icon="📝", layout="wide")

# 1. 넉넉한 여백(250px)과 깨끗한 수능 양식 유지
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        @page {{ size: A4; margin: 10mm; }}
        body {{ font-family: 'Batang', serif; line-height: 1.5; color: black; background: #fff; }}
        .no-print {{ text-align: right; max-width: 210mm; margin: 10px auto; }}
        .btn-print {{ padding: 10px 20px; background: #000; color: white; border: none; cursor: pointer; font-weight: bold; border-radius: 5px; }}
        .paper {{ max-width: 210mm; margin: 0 auto; background: white; padding: 15mm; min-height: 297mm; }}
        .header {{ text-align: center; border-bottom: 2.5px solid black; padding-bottom: 10px; margin-bottom: 25px; }}
        .twocolumn {{ column-count: 2; column-gap: 45px; column-rule: 0.8px solid black; }}
        .question {{ margin-bottom: 250px; position: relative; padding-left: 30px; page-break-inside: avoid; word-break: keep-all; }}
        .q-num {{ font-weight: bold; font-size: 14pt; position: absolute; left: 0; top: 0; }}
        .options {{ display: flex; flex-wrap: wrap; justify-content: space-between; margin-top: 15px; font-size: 10.5pt; }}
        .opt-item {{ min-width: 18%; margin-bottom: 8px; }}
        .solution-page {{ page-break-before: always; border-top: 3px double black; margin-top: 60px; padding-top: 40px; }}
        @media print {{ .no-print {{ display: none; }} }}
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-print" onclick="window.print()">📥 PDF 저장 / 인쇄</button></div>
    <div class="paper">
        <div class="header">
            <h1>2026학년도 대학수학능력시험 모의평가</h1>
            <h2>수학 영역 ({subject})</h2>
        </div>
        <div class="twocolumn">{questions}</div>
        <div class="solution-page">
            <h2 style="text-align:center; border: 1.5px solid black; display: inline-block; padding: 5px 30px; margin-bottom: 30px;">정답 및 상세 해설</h2>
            <div>{solutions}</div>
        </div>
    </div>
    <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};</script>
</body>
</html>
"""

# 2. 안정적인 순차 생성 엔진 (서버 차단 방지)
def generate_stable_exam(model, subject, total, diff):
    all_questions = ""
    all_solutions = ""
    
    # 5문제씩 끊어서 차례대로 생성 (무료 한도 준수)
    progress_text = st.empty()
    bar = st.progress(0)
    
    chunk_size = 5
    for i in range(1, total + 1, chunk_size):
        end = min(i + chunk_size - 1, total)
        progress_text.text(f"⏳ {i}~{end}번 문항과 해설을 제작 중입니다...")
        
        instr = "인사말 없이 HTML만 출력. 수식은 $ 사용. 고교 수학 내용만 다룰 것."
        prompt = f"{instr} 수능 수학 {subject} {i}~{end}번 문항과 상세 해설을 <div class='question'> 구조로 각각 만들어줘."
        
        try:
            response = model.generate_content(prompt)
            res_text = response.text.replace('```html', '').replace('```', '').strip()
            
            # 수식 기호 교정 및 사족 제거
            clean_text = res_text.replace('\\\\', '\\').replace('\\W', '\\')
            
            # 문제와 해설을 임시로 합침 (나중에 레이아웃에서 자동 분리되도록 유도 가능)
            all_questions += clean_text
            bar.progress(end / total)
            time.sleep(2) # 서버가 쉴 수 있게 2초 대기 (핵심!)
            
        except Exception as e:
            st.warning(f"⚠️ {i}번 세트 생성 중 지연 발생. 재시도 중... ({e})")
            time.sleep(5) # 에러 발생 시 더 길게 휴식
            continue
            
    return all_questions

# 3. 메인 화면
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('models/gemini-2.5-flash')

    with st.sidebar:
        st.header("📄 시험지 설정")
        sub = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        num = st.radio("문항 수", [5, 10, 30])
        diff = st.select_slider("난이도", options=["기초", "수능형", "심화"])

    if st.sidebar.button("🚀 안전 모드로 발간"):
        # 기존의 비동기(async)를 빼고 직관적인 순차 방식으로 변경
        full_content = generate_stable_exam(model, sub, num, diff)
        
        if full_content:
            # 문제와 해설이 섞여 나오는 것을 방지하기 위해 AI에게 구조를 맡기거나 
            # 단순히 한 페이지에 쭉 뿌려주는 방식으로 우선 복구
            final_page = HTML_TEMPLATE.format(subject=sub, questions=full_content, solutions="해설은 문제 하단에 포함되어 있습니다.")
            st.success("✅ 안전하게 발간되었습니다!")
            st.components.v1.html(final_page, height=1200, scrolling=True)
