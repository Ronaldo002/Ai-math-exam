import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="2026 수능 수학 마스터", page_icon="📝", layout="wide")

# 1. 수능 시험지 원형 레이아웃 (여백 250px 유지)
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
        .question {{ 
            margin-bottom: 250px; /* 넉넉한 문제 풀이 공간 */
            position: relative; padding-left: 30px; 
            page-break-inside: avoid; word-break: keep-all; 
        }}
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
            <div style="column-count: 1;">{solutions}</div>
        </div>
    </div>
    <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};</script>
</body>
</html>
"""

# 2. 고속 병렬 처리 (문제와 해설 바구니 분리)
async def fetch_exam_part(model, start, end, subject, diff):
    # '수학' 전문 지시 및 사족 제거 강화
    instr = "인사말 없이 HTML만 출력. 수식은 $ 사용. 자바스크립트 등 타 분야 금지."
    q_p = f"{instr} 수능 수학 {subject} {start}~{end}번 문항 제작. 난이도: {diff}. <div class='question'> 사용."
    s_p = f"{instr} 위 {start}~{end}번 문항의 수학적 풀이와 정답만 작성."
    
    try:
        await asyncio.sleep(0.5)
        # 문제와 해설을 동시에 요청
        q_r = await model.generate_content_async(q_p)
        s_r = await model.generate_content_async(s_p)
        
        def clean(t):
            res = t.text.replace('```html', '').replace('```', '').strip()
            # AI의 사족 제거 필터
            if any(x in res[:60] for x in ["네", "요청", "수능", "생성"]):
                res = res.split("</div>", 1)[-1] if "</div>" in res else res
            return res.replace('\\\\', '\\').replace('\\W', '\\')
            
        return clean(q_r), clean(s_r)
    except: return "", ""

async def run_fast_generation(model, subject, total, diff):
    chunk_size = 5 # 비서 5명 투입
    tasks = [fetch_exam_part(model, i, min(i+chunk_size-1, total), subject, diff) 
             for i in range(1, total + 1, chunk_size)]
    results = await asyncio.gather(*tasks)
    # 바구니별로 따로 모으기
    all_q = "".join([r[0] for r in results])
    all_s = "".join([r[1] for r in results])
    return all_q, all_s

# 3. 사이드바 및 메인 로직
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('models/gemini-2.5-flash')

    with st.sidebar:
        st.header("📋 고속 출제 시스템")
        sub = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        num = st.radio("문항 수", [5, 10, 30])
        diff = st.select_slider("난이도", options=["기초", "수능형", "심화"])

    if st.sidebar.button("🚀 초고속 모의고사 발간"):
        st.info(f"⏳ 비서 5명이 {num}문항과 해설을 안전하게 제작 중입니다...")
        questions, solutions = asyncio.run(run_fast_generation(model, sub, num, diff))
        
        if questions.strip():
            final_page = HTML_TEMPLATE.format(subject=sub, questions=questions, solutions=solutions)
            st.success("✅ 발간 완료! PDF로 저장하세요.")
            st.components.v1.html(final_page, height=1200, scrolling=True)
        else:
            st.error("❌ 데이터 생성 실패. 잠시 후 다시 시도해 주세요.")
