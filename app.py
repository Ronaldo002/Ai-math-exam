import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="고속 수능 모의고사 시스템", page_icon="⚡", layout="wide")
st.title("⚡ AI 수능 모의고사 생성기 (고속 모드)")

# 1. 디자인 템플릿 (깔끔한 수능 양식 유지)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        @page { size: A4; margin: 12mm; }
        body { font-family: 'Batang', 'Times New Roman', serif; line-height: 1.5; color: black; background: #fff; }
        .no-print { text-align: right; max-width: 210mm; margin: 10px auto; }
        .btn-print { padding: 10px 20px; background: #222; color: white; border: none; cursor: pointer; font-weight: bold; border-radius: 4px; }
        .paper { max-width: 210mm; margin: 0 auto; background: white; padding: 12mm; min-height: 297mm; }
        .header { text-align: center; border-bottom: 2.5px solid black; padding-bottom: 10px; margin-bottom: 25px; }
        .twocolumn { column-count: 2; column-gap: 40px; column-rule: 0.8px solid black; }
        .question { margin-bottom: 180px; position: relative; padding-left: 25px; page-break-inside: avoid; }
        .q-num { font-weight: bold; font-size: 13pt; position: absolute; left: 0; top: 0; }
        .options { display: flex; flex-wrap: wrap; justify-content: space-between; margin-top: 12px; font-size: 10pt; }
        .opt-item { min-width: 18%; margin-bottom: 5px; }
        @media print { .no-print { display: none; } .paper { border: none; width: 100%; } }
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-print" onclick="window.print()">📥 PDF 저장 / 인쇄</button></div>
    <div class="paper">
        <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h2>수학 영역 ({subject})</h2></div>
        <div class="twocolumn">{content}</div>
    </div>
    <script>window.MathJax = { tex: { inlineMath: [['$', '$']] } };</script>
</body>
</html>
"""

# 2. 고속 병렬 처리 로직
async def fetch_chunk(model, start_num, end_num, subject):
    prompt = f"인사말 없이 HTML 태그만 출력. 수능 수학 {subject} {start_num}~{end_num}번 문항 제작. <div class='question'> 구조 사용. 수식은 $ 사용."
    try:
        response = await model.generate_content_async(prompt)
        # 불필요한 마크다운 및 기호 정제
        return response.text.replace('```html', '').replace('```', '').replace('\\\\', '\\').replace('\\W', '\\')
    except: return ""

async def generate_fast(model, subject, total_q):
    chunk_size = 5 # 5문제씩 비서들에게 배분
    tasks = [fetch_chunk(model, i, min(i+chunk_size-1, total_q), subject) 
             for i in range(1, total_q + 1, chunk_size)]
    results = await asyncio.gather(*tasks)
    return "".join(results)

# 3. 화면 구성 및 실행
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('models/gemini-2.5-flash') # 사용 가능 모델 적용

    with st.sidebar:
        st.header("📋 출제 옵션")
        subject = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        num_q = st.radio("문항 수", [5, 10, 30])
        st.divider()
        st.info("⚡ 비서 5명 버전으로 롤백되었습니다.")

    if st.sidebar.button("🚀 초고속 모의고사 발간"):
        st.info(f"⏳ {num_q}문항을 동시에 제작 중입니다...")
        full_content = asyncio.run(generate_fast(model, subject, num_q))
        
        if full_content:
            final_html = HTML_TEMPLATE.format(subject=subject, content=full_content)
            st.success("✅ 발간 완료!")
            st.components.v1.html(final_html, height=1000, scrolling=True)
        else:
            st.error("❌ 생성 실패. API 한도를 확인해 주세요.")

