import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="2026 수능 수학 모의고사", page_icon="📝", layout="wide")

# 1. 인쇄 시 실제 수능 시험지 여백과 동일하게 설정
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        @page {{ size: A4; margin: 10mm; }}
        body {{ font-family: 'Batang', serif; line-height: 1.5; color: black; background: #f9f9f9; }}
        .no-print {{ text-align: right; max-width: 210mm; margin: 10px auto; }}
        .btn-print {{ padding: 10px 20px; background: #000; color: white; border: none; cursor: pointer; font-weight: bold; }}
        .paper {{ max-width: 210mm; margin: 0 auto; background: white; padding: 15mm; min-height: 297mm; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; border-bottom: 2.5px solid black; padding-bottom: 10px; margin-bottom: 25px; }}
        .twocolumn {{ column-count: 2; column-gap: 45px; column-rule: 0.8px solid black; }}
        .question {{ 
            margin-bottom: 250px; /* 문제를 풀 수 있는 넉넉한 여백 확보 */
            position: relative; padding-left: 28px; 
            page-break-inside: avoid; word-break: keep-all; 
        }}
        .q-num {{ font-weight: bold; font-size: 14pt; position: absolute; left: 0; top: 0; }}
        .options {{ display: flex; flex-wrap: wrap; justify-content: space-between; margin-top: 15px; font-size: 10.5pt; }}
        .opt-item {{ min-width: 18%; margin-bottom: 8px; }}
        .solution-page {{ page-break-before: always; border-top: 3px double black; margin-top: 60px; padding-top: 40px; }}
        @media print {{ 
            body {{ background: white; }}
            .paper {{ box-shadow: none; border: none; width: 100%; }}
            .no-print {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-print" onclick="window.print()">📥 PDF 저장 / 인쇄하기</button></div>
    <div class="paper">
        <div class="header">
            <h1>2026학년도 대학수학능력시험 모의평가</h1>
            <h2>수학 영역 ({subject})</h2>
        </div>
        <div class="twocolumn">{questions}</div>
        <div class="solution-page">
            <h2 style="text-align:center; border: 1.5px solid black; display: inline-block; padding: 5px 30px; margin-bottom: 30px;">정답 및 상세 해설</h2>
            <div style="column-count: 1;">{solutions}</div>
        </div>
    </div>
    <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};</script>
</body>
</html>
"""

async def generate_chunk(model, start, end, subject, difficulty):
    # '수학' 과목임을 엄격히 강조하여 자바스크립트 등 엉뚱한 내용 방지
    instr = "인사말 없이 HTML만 출력. 수식은 $ 사용. 오직 고등학교 수학 내용만 다룰 것."
    q_p = f"{instr} 수능 수학 {subject} {start}~{end}번 문항. 난이도: {difficulty}. <div class='question'> 사용."
    s_p = f"{instr} 위 수학 문항의 상세 풀이와 정답. 프로그래밍 등 타 분야 금지."
    
    try:
        await asyncio.sleep(0.8)
        q_r = await model.generate_content_async(q_p)
        s_r = await model.generate_content_async(s_p)
        
        def clean(t):
            text = t.text.replace('```html', '').replace('```', '').strip()
            # 사족 제거 로직 강화
            if any(x in text[:60] for x in ["네", "요청", "수능", "생성"]):
                text = text.split("</div>", 1)[-1] if "</div>" in text else text
            return text.replace('\\\\', '\\').replace('\\W', '\\')
            
        return clean(q_r), clean(s_r)
    except: return "", ""

async def run_exam_generation(model, subject, total, difficulty):
    chunk_size = 5 # 비서 5명 병렬 처리
    tasks = [generate_chunk(model, i, min(i+chunk_size-1, total), subject, difficulty) 
             for i in range(1, total + 1, chunk_size)]
    results = await asyncio.gather(*tasks)
    return "".join([r[0] for r in results]), "".join([r[1] for r in results])

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('models/gemini-2.5-flash')

    with st.sidebar:
        st.header("📋 고속 출제 시스템")
        subject = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        num_q = st.radio("문항 수", [5, 10, 30])
        diff = st.select_slider("난이도", options=["기초", "수능형", "심화"])

    if st.sidebar.button("🚀 모의고사 발간"):
        st.info(f"⏳ {num_q}문항과 상세 수학 해설을 제작 중입니다...")
        q_html, s_html = asyncio.run(run_exam_generation(model, subject, num_q, diff))
        
        final = HTML_TEMPLATE.format(subject=subject, questions=q_html, solutions=s_html)
        st.success("✅ 완료! PDF로 저장하여 문제를 풀어보세요.")
        st.components.v1.html(final, height=1200, scrolling=True)
