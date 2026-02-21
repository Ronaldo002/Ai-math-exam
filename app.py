import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="2026 수능 모의고사 시스템", page_icon="📝", layout="wide")

# 1. 삐져나옴 방지 및 수능 레이아웃 정밀 보정
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
        .question {{ 
            margin-bottom: 160px; /* 적당한 풀이 공간 확보 */
            position: relative; 
            padding-left: 25px; 
            page-break-inside: avoid; /* 문제 잘림 방지 */
            word-break: keep-all; /* 텍스트 삐져나옴 방지 */
            overflow: hidden; /* 영역 이탈 방지 */
        }}
        .q-num {{ font-weight: bold; font-size: 13pt; position: absolute; left: 0; top: 0; }}
        .options {{ display: flex; flex-wrap: wrap; justify-content: space-between; margin-top: 12px; font-size: 10pt; }}
        .option-item {{ min-width: 18%; margin-bottom: 5px; }}
        .solution-page {{ page-break-before: always; border-top: 2px dashed #333; margin-top: 50px; padding-top: 30px; }}
        @media print {{ 
            body {{ background: white; }}
            .paper {{ box-shadow: none; border: none; width: 100%; padding: 0; }}
            .no-print {{ display: none; }}
        }}
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
    <script>
        window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};
    </script>
</body>
</html>
"""

async def generate_exam_data(model, subject, num_q, difficulty):
    # AI 사족 방지를 위한 초강력 프롬프트
    base_instruction = "너는 수능 출제 위원이야. 인사말이나 설명 없이 오직 요구된 HTML 태그만 출력해."
    
    q_prompt = f"""{base_instruction}
    수능 수학 {subject} 과목의 {num_q}문제를 만드시오. 난이도는 '{difficulty}' 수준으로 출제할 것.
    형식: <div class='question'><span class='q-num'>번호.</span> 문제내용 <div class='options'><div class='option-item'>①..</div><div class='option-item'>②..</div><div class='option-item'>③..</div><div class='option-item'>④..</div><div class='option-item'>⑤..</div></div></div>
    수식은 $ 기호 사용. 텍스트가 줄바꿈 없이 길어지지 않게 주의할 것.
    """
    
    s_prompt = f"{base_instruction} 위 문제들에 대한 번호별 정답과 상세한 풀이 과정을 HTML로 작성해줘."

    try:
        q_resp = await model.generate_content_async(q_prompt)
        s_resp = await model.generate_content_async(s_prompt)
        
        def clean(t):
            # 1. 마크다운 기호 제거 2. 사족(인사말 등) 제거 시도 3. 수식 기호 정제
            text = t.text.replace('```html', '').replace('```', '').strip()
            # 첫 문장이 "네, ..."로 시작하는 사족이 있다면 제거
            if text.startswith(("네", "요청하신", "수능")):
                text = text.split("</div>", 1)[-1] if "</div>" in text else text
            return text.replace('\\\\', '\\').replace('\\W', '\\')
            
        return clean(q_resp), clean(s_resp)
    except Exception as e:
        return f"생성 중 오류 발생: {e}", ""

# 3. 사이드바 메뉴 (난이도 부활)
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('models/gemini-2.5-flash')

    with st.sidebar:
        st.header("📋 시험지 설정")
        subject = st.selectbox("과목 선택", ["수학 I, II", "미적분", "확률과 통계"])
        num_q = st.radio("문항 수", [5, 10, 30], index=0)
        difficulty = st.select_slider("출제 난이도", options=["개념기초", "수능실전", "심화킬러"], value="수능실전")
        st.divider()
        st.info("💡 PDF 저장 시 '배경 그래픽'을 체크하면 시험지 느낌이 더 살아납니다.")

    if st.sidebar.button("🚀 모의고사 발간"):
        st.info(f"⏳ {difficulty} 난이도로 {num_q}문항을 제작 중입니다...")
        q_html, s_html = asyncio.run(generate_exam_data(model, subject, num_q, difficulty))
        
        final_html = HTML_TEMPLATE.format(subject=subject, questions=q_html, solutions=s_html)
        st.components.v1.html(final_html, height=1200, scrolling=True)

