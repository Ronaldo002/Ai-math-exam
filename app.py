import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="수능 모의고사 마스터", page_icon="🎓", layout="wide")
st.title("🎓 AI 수능 모의고사 시스템 (해설지 & 난이도 지원)")

# 1. 디자인 템플릿 (250px 여백 및 해설지 전용 섹션 추가)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        @page {{ size: A4; margin: 12mm; }}
        body {{ font-family: 'Batang', serif; line-height: 1.6; color: black; background: #fff; }}
        .no-print {{ text-align: right; max-width: 210mm; margin: 10px auto; }}
        .btn-print {{ padding: 10px 20px; background: #333; color: white; border: none; cursor: pointer; border-radius: 4px; }}
        .paper {{ max-width: 210mm; margin: 0 auto; background: white; padding: 12mm; min-height: 297mm; }}
        .header {{ text-align: center; border-bottom: 2.5px solid black; padding-bottom: 10px; margin-bottom: 25px; }}
        .twocolumn {{ column-count: 2; column-gap: 45px; column-rule: 0.8px solid black; }}
        .question {{ margin-bottom: 250px; position: relative; padding-left: 30px; page-break-inside: avoid; }}
        .q-num {{ font-weight: bold; font-size: 14pt; position: absolute; left: 0; top: 0; }}
        .solution-page {{ page-break-before: always; border-top: 3px double black; margin-top: 60px; padding-top: 40px; }}
        @media print {{ .no-print {{ display: none; }} .paper {{ border: none; width: 100%; }} }}
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-print" onclick="window.print()">📥 PDF 저장 / 인쇄</button></div>
    <div class="paper">
        <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h2>수학 영역 ({subject})</h2></div>
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

# 2. 고속 병렬 처리 로직 (문제와 해설을 함께 생성)
async def fetch_chunk(model, start_num, end_num, subject, difficulty):
    # AI에게 문제와 해설을 구분해서 출력하도록 요청
    prompt = f"""인사말 없이 HTML 태그만 출력. 수능 수학 {subject} {start_num}~{end_num}번 문항을 만드시오. 
    난이도는 {difficulty} 수준으로 하시오. 
    1. 문제는 <div class='question'> 구조로 작성. 
    2. 모든 문제 뒤에 [해설] 표시를 한 뒤 상세 풀이를 작성하시오. 
    수식은 $ 사용."""
    
    try:
        response = await model.generate_content_async(prompt)
        text = response.text.replace('```html', '').replace('```', '').strip()
        text = text.replace('\\\\', '\\').replace('\\W', '\\') # 수식 교정
        
        # 문제와 해설 분리
        if "[해설]" in text:
            parts = text.split("[해설]")
            return parts[0], parts[1]
        return text, ""
    except:
        return "", ""

async def generate_full_exam(model, subject, total_q, difficulty):
    chunk_size = 5
    tasks = [fetch_chunk(model, i, min(i+chunk_size-1, total_q), subject, difficulty) 
             for i in range(1, total_q + 1, chunk_size)]
    results = await asyncio.gather(*tasks)
    
    all_q = "".join([r[0] for r in results])
    all_s = "".join([r[1] for r in results])
    return all_q, all_s

# 3. 메인 실행부
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('models/gemini-2.5-flash') #

    with st.sidebar:
        st.header("⚙️ 설정")
        subject_opt = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        num_q = st.radio("문항 수", [5, 10, 30])
        diff_opt = st.select_slider("난이도", options=["기초", "수능형", "킬러"])
        st.info("💡 해설지가 포함된 버전입니다.")

    if st.sidebar.button("🚀 모의고사 발간"):
        with st.status("⏳ 문항과 해설을 동시에 제작 중입니다...") as status:
            q_html, s_html = asyncio.run(generate_full_exam(model, subject_opt, num_q, diff_opt))
            
            if q_html:
                final_page = HTML_TEMPLATE.format(subject=subject_opt, questions=q_html, solutions=s_html)
                st.success("✅ 발간 완료!")
                st.components.v1.html(final_page, height=1000, scrolling=True)
            else:
                st.error("❌ 생성 실패. API 한도를 확인해 주세요.")
            status.update(label="발간 완료", state="complete")
