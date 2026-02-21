import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="AI 수능 모의고사 생성기", page_icon="📝", layout="wide")
st.title("📝 AI 수능 모의고사 생성기 (경로 최적화)")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>수능 모의고사</title>
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        @page { size: A4; margin: 15mm; }
        body { font-family: 'Malgun Gothic', sans-serif; line-height: 1.6; background: white; }
        .paper { max-width: 210mm; margin: 0 auto; padding: 10mm; }
        .header { text-align: center; border-bottom: 2px solid black; padding-bottom: 10px; margin-bottom: 20px; }
        .twocolumn { column-count: 2; column-gap: 30px; column-rule: 1px solid #ccc; }
        .question { margin-bottom: 40px; page-break-inside: avoid; }
        .q-number { font-weight: bold; font-size: 1.1em; }
        .options { display: flex; justify-content: space-between; margin-top: 10px; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="paper">
        <div class="header"><h1>2026학년도 대학수학능력시험</h1><h2>수학 영역</h2></div>
        <div class="twocolumn">{content}</div>
    </div>
</body>
</html>
"""

async def fetch_questions(model, start_num, end_num, subject, difficulty):
    prompt = f"수능 수학 {subject} 과목 {start_num}~{end_num}번 문항을 HTML <div>로 만들어. 난이도: {difficulty}. 설명 없이 코드만 출력."
    try:
        await asyncio.sleep(0.5)
        response = await model.generate_content_async(prompt)
        return response.text.replace('```html', '').replace('```', '')
    except Exception as e:
        return f"<p style='color:red;'>⚠️ {start_num}번 생성 오류: {e}</p>"

async def generate_exam(model, total_questions, subject, difficulty):
    chunk_size = 5
    tasks = [fetch_questions(model, i, min(i+chunk_size-1, total_questions), subject, difficulty) 
             for i in range(1, total_questions + 1, chunk_size)]
    results = await asyncio.gather(*tasks)
    return "".join(results)

st.sidebar.header("설정")
subject = st.sidebar.selectbox("과목", ["미적분", "확률과 통계", "수학 I, II"])
num_questions_str = st.sidebar.radio("문항 수", ["5문항", "10문항", "30문항"])
difficulty = st.sidebar.select_slider("난이도", options=["개념", "실전", "킬러"])

if st.sidebar.button("🚀 모의고사 생성"):
    try:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        
        # [핵심 변경] 모델 이름 앞에 'models/'를 명시하여 404 에러 원천 차단
        # flash-001 버전이 가장 안정적으로 호출됩니다.
        model = genai.GenerativeModel('models/gemini-1.5-flash-001') 
        
        total_q = int(num_questions_str.split("문항")[0])
        st.info(f"⏳ {total_q}문항 생성 중...")
        
        html_content = asyncio.run(generate_exam(model, total_q, subject, difficulty))
        final_html = HTML_TEMPLATE.replace("{content}", html_content)
        
        st.success("✅ 완료!")
        st.download_button("📥 다운로드", data=final_html, file_name="exam.html", mime="text/html")
        st.components.v1.html(final_html, height=800, scrolling=True)

    except Exception as e:
        st.error(f"❌ 오류: {e}")
