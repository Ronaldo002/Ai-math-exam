import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="고속 수능 모의고사 시스템", page_icon="⚡", layout="wide")
st.title("⚡ AI 수능 모의고사 생성기 (고속 모드)")

# 1. 디자인 템플릿 (수능 양식 유지)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        @page {{ size: A4; margin: 12mm; }}
        body {{ font-family: 'Batang', 'Times New Roman', serif; line-height: 1.5; color: black; background: #f4f4f4; }}
        .no-print {{ text-align: right; max-width: 210mm; margin: 10px auto; }}
        .btn-print {{ padding: 10px 20px; background: #222; color: white; border: none; cursor: pointer; font-weight: bold; border-radius: 4px; }}
        .paper {{ max-width: 210mm; margin: 0 auto; background: white; padding: 12mm; min-height: 297mm; box-shadow: 0 0 15px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; border-bottom: 2.5px solid black; padding-bottom: 10px; margin-bottom: 25px; }}
        .header h1 {{ font-size: 22pt; margin: 0; letter-spacing: -1px; }}
        .header h2 {{ font-size: 16pt; margin: 5px 0; }}
        .twocolumn {{ column-count: 2; column-gap: 40px; column-rule: 0.8px solid black; }}
        .question {{ margin-bottom: 160px; position: relative; padding-left: 25px; page-break-inside: avoid; word-break: keep-all; overflow: hidden; }}
        .q-num {{ font-weight: bold; font-size: 13pt; position: absolute; left: 0; top: 0; }}
        .options {{ display: flex; flex-wrap: wrap; justify-content: space-between; margin-top: 12px; font-size: 10pt; }}
        .option-item {{ min-width: 18%; margin-bottom: 5px; }}
        .solution-page {{ page-break-before: always; border-top: 2px dashed #333; margin-top: 50px; padding-top: 30px; }}
        @media print {{ body {{ background: white; }} .paper {{ box-shadow: none; border: none; width: 100%; padding: 0; }} .no-print {{ display: none; }} }}
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-print" onclick="window.print()">📥 PDF 저장 / 인쇄</button></div>
    <div class="paper">
        <div class="header">
            <h1>2026학년도 대학수학능력시험 모의평가 문제지</h1>
            <h2>수학 영역 ({subject})</h2>
        </div>
        <div class="twocolumn">{questions}</div>
        <div class="solution-page">
            <h2 style="text-align:center; border: 1.5px solid black; display: inline-block; padding: 5px 25px; margin-bottom: 25px;">정답 및 해설</h2>
            <div style="column-count: 1;">{solutions}</div>
        </div>
    </div>
    <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};</script>
</body>
</html>
"""

# 2. 고속 병렬 처리 엔진
async def fetch_chunk(model, start_num, end_num, subject, difficulty):
    """지정된 범위의 문제와 해설을 생성하는 비서 한 명의 역할"""
    instruction = "인사말 없이 HTML 태그만 출력. 수식은 $ 사용."
    q_prompt = f"{instruction} 수능 수학 {subject} {start_num}~{end_num}번 문항 제작. 난이도: {difficulty}. <div class='question'> 구조 사용."
    s_prompt = f"{instruction} 위 {start_num}~{end_num}번 문항의 상세 풀이와 정답을 HTML로 작성."
    
    try:
        await asyncio.sleep(0.5) # API 과부하 방지 지연
        q_resp = await model.generate_content_async(q_prompt)
        s_resp = await model.generate_content_async(s_prompt)
        
        def clean(t):
            text = t.text.replace('```html', '').replace('```', '').strip()
            # 첫 문장 사족 제거 필터
            if any(word in text[:50] for word in ["네", "요청", "수능"]):
                text = text.split("</div>", 1)[-1] if "</div>" in text else text
            return text.replace('\\\\', '\\').replace('\\W', '\\')
            
        return clean(q_resp), clean(s_resp)
    except:
        return "", ""

async def generate_full_exam(model, subject, total_q, difficulty):
    # 5문제씩 비서들에게 나누어줌 (병렬 작업 실행)
    chunk_size = 5
    tasks = [fetch_chunk(model, i, min(i + chunk_size - 1, total_q), subject, difficulty) 
             for i in range(1, total_q + 1, chunk_size)]
    
    results = await asyncio.gather(*tasks)
    
    final_q = "".join([r[0] for r in results])
    final_s = "".join([r[1] for r in results])
    return final_q, final_s

# 3. 사이드바 및 실행
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('models/gemini-2.5-flash') #

    with st.sidebar:
        st.header("📋 고속 출제 설정")
        subject = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        num_q = st.radio("문항 수", [5, 10, 30])
        difficulty = st.select_slider("난이도", options=["개념기초", "수능실전", "심화킬러"], value="수능실전")

    if st.sidebar.button("🚀 초고속 모의고사 발간"):
        st.info(f"⏳ 비서 5명이 동시에 {num_q}문항을 제작 중입니다...")
        q_html, s_html = asyncio.run(generate_full_exam(model, subject, num_q, difficulty))
        
        final_html = HTML_TEMPLATE.format(subject=subject, questions=q_html, solutions=s_html)
        st.success("✅ 발간 완료!")
        st.components.v1.html(final_html, height=1200, scrolling=True)
