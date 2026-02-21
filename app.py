import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="2026 수능 모의고사 발간", page_icon="📝", layout="wide")

# 1. 수능 전용 폰트 및 레이아웃 (색상 배제, 2단 고정)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        @page {{ size: A4; margin: 15mm; }}
        body {{ font-family: 'Batang', 'Times New Roman', serif; line-height: 1.6; color: black; background: #f0f0f0; }}
        .no-print {{ text-align: right; max-width: 210mm; margin: 10px auto; }}
        .btn-print {{ padding: 8px 16px; background: #333; color: white; border: none; cursor: pointer; font-weight: bold; }}
        .paper {{ max-width: 210mm; margin: 0 auto; background: white; padding: 15mm; min-height: 297mm; box-shadow: 0 0 10px rgba(0,0,0,0.2); }}
        .header {{ text-align: center; border-bottom: 2px solid black; padding-bottom: 10px; margin-bottom: 30px; }}
        .header h1 {{ font-size: 24pt; margin: 0; }}
        .header h2 {{ font-size: 18pt; margin: 5px 0; }}
        .twocolumn {{ column-count: 2; column-gap: 50px; column-rule: 0.5px solid black; }}
        .question {{ margin-bottom: 200px; /* 문제 풀이 공간 */ position: relative; padding-left: 30px; page-break-inside: avoid; }}
        .q-num {{ font-weight: bold; font-size: 14pt; position: absolute; left: 0; top: 0; }}
        .options {{ display: flex; justify-content: space-between; margin-top: 15px; font-size: 10pt; }}
        .solution-page {{ page-break-before: always; border-top: 2px dashed black; margin-top: 60px; padding-top: 40px; }}
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
            <h1>2026학년도 대학수학능력시험 모의평가 문제지</h1>
            <h2>수학 영역 ({subject})</h2>
        </div>
        <div class="twocolumn">{questions}</div>
        <div class="solution-page">
            <h2 style="text-align:center; border: 1px solid black; display: inline-block; padding: 5px 20px; margin-bottom: 20px;">정답 및 해설</h2>
            <div>{solutions}</div>
        </div>
    </div>
    <script>
        window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};
    </script>
</body>
</html>
"""

async def generate_exam_data(model, subject, num_q, difficulty):
    q_prompt = f"수능 수학 {subject} {num_q}문제를 HTML <div class='question'><span class='q-num'>번호.</span> 문제내용 <div class='options'>①..②..③..④..⑤..</div></div> 구조로 만들어. 수식은 $ 사용. 파란색이나 박스 쓰지마."
    s_prompt = f"위 문제들의 정답과 상세 풀이를 HTML로 작성해줘."
    try:
        q_resp = await model.generate_content_async(q_prompt)
        s_resp = await model.generate_content_async(s_prompt)
        # 역슬래시 및 특수기호 정제
        def clean(t): return t.text.replace('```html', '').replace('```', '').replace('\\\\', '\\').replace('\\W', '\\')
        return clean(q_resp), clean(s_resp)
    except: return "오류 발생", ""

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('models/gemini-2.5-flash') #

    with st.sidebar:
        st.header("📄 시험지 설정")
        subject = st.selectbox("과목", ["미적분", "확률과 통계", "수학 I, II"])
        num_q = st.radio("문항 수", [5, 10, 30])
        st.info("💡 팁: PDF 저장 시 '배경 그래픽' 옵션을 끄면 더 깔끔합니다.")

    if st.sidebar.button("🚀 모의고사 발간"):
        st.info("⏳ 실제 수능 양식에 맞춰 시험지를 제작 중입니다...")
        q_html, s_html = asyncio.run(generate_exam_data(model, subject, num_q, "표준"))
        
        final_html = HTML_TEMPLATE.format(subject=subject, questions=q_html, solutions=s_html)
        st.components.v1.html(final_html, height=1200, scrolling=True)

