import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="AI 수능 모의고사 시스템", page_icon="🎓", layout="wide")

# 1. 실제 시험지 레이아웃을 재현한 CSS 및 스크립트
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        @page {{ size: A4; margin: 15mm; }}
        body {{ font-family: 'Times New Roman', 'Malgun Gothic', serif; line-height: 1.7; }}
        .no-print {{ text-align: right; margin-bottom: 20px; }}
        .btn-print {{ padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }}
        .paper {{ max-width: 210mm; margin: 0 auto; background: white; padding: 10mm; }}
        .header {{ text-align: center; border-bottom: 2px solid black; padding-bottom: 10px; margin-bottom: 30px; }}
        .twocolumn {{ column-count: 2; column-gap: 40px; column-rule: 0.5px solid #333; }}
        .question {{ margin-bottom: 150px; page-break-inside: avoid; position: relative; }}
        .q-num {{ font-weight: bold; font-size: 1.2em; position: absolute; left: -25px; }}
        .options {{ margin-top: 10px; display: flex; justify-content: space-between; font-size: 0.9em; }}
        .solution-page {{ page-break-before: always; border-top: 3px double black; margin-top: 50px; padding-top: 30px; }}
        @media print {{ .no-print {{ display: none; }} .paper {{ border: none; box-shadow: none; }} }}
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-print" onclick="window.print()">📥 PDF로 저장 / 인쇄하기</button></div>
    <div class="paper">
        <div class="header"><h1>2026학년도 대학수학능력시험 모의평가 문제지</h1><h2>수학 영역 ({subject})</h2></div>
        <div class="twocolumn">{questions}</div>
        <div class="solution-page">
            <h2 style="text-align:center;">[ 정답 및 해설 ]</h2>
            <div style="column-count: 1;">{solutions}</div>
        </div>
    </div>
    <script>
        window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};
    </script>
</body>
</html>
"""

async def generate_content(model, prompt):
    try:
        await asyncio.sleep(1)
        response = await model.generate_content_async(prompt)
        # 역슬래시 중복 및 깨짐 방지
        return response.text.replace('```html', '').replace('```', '').replace('\\\\', '\\').replace('\\W', '\\')
    except: return "내용 생성 실패"

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('models/gemini-2.5-flash') # 최신 모델 적용

    with st.sidebar:
        st.header("📋 시험지 설정")
        subject = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        num_q = st.radio("문항 수", [5, 10, 30])
        difficulty = st.select_slider("난이도", options=["기초", "표준", "킬러"])

    if st.sidebar.button("🚀 모의고사 발간"):
        st.info("⏳ AI 출제 위원이 문제를 구성하고 해설을 작성 중입니다...")
        
        # 문제와 해설을 따로 생성하여 뒤섞임을 원천 차단
        q_prompt = f"수능 수학 {subject} {num_q}문제를 HTML <div class='question'> 구조로 만들어. 수식은 $ 사용."
        s_prompt = f"위 문제들에 대한 상세한 풀이 과정과 정답을 HTML로 작성해줘."
        
        q_html = asyncio.run(generate_content(model, q_prompt))
        s_html = asyncio.run(generate_content(model, s_prompt))
        
        final_exam = HTML_TEMPLATE.format(subject=subject, questions=q_html, solutions=s_html)
        
        st.success("✅ 발간 완료! 상단의 버튼을 눌러 PDF로 저장하세요.")
        st.components.v1.html(final_exam, height=1200, scrolling=True)


