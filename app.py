import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="AI 수능 모의고사 생성기", page_icon="📝", layout="wide")
st.title("📝 AI 수능 모의고사 생성기 (API 통로 최적화)")

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
        # 생성 로직 호출
        response = await model.generate_content_async(prompt)
        return response.text.replace('```html', '').replace('```', '')
    except Exception as e:
        return f"<p style='color:red;'>⚠️ {start_num}번 생성 실패: {e}</p>"

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

if st.sidebar.button("🚀 모의고사 생성 시작"):
    try:
        # [핵심] API 키 호출 및 설정
        API_KEY = st.secrets["GEMINI_API_KEY"]
        
        # [필살기] v1beta 환경에 최적화된 초기화 방식
        from google.generativeai import types
        genai.configure(api_key=API_KEY)
        
        # 현재 에러가 발생하는 환경(v1beta)에서 가장 확실하게 작동하는 최신 모델 지정
        # models/ 접두사를 붙여 경로를 명시합니다.
        model = genai.GenerativeModel(model_name='models/gemini-1.5-flash-latest')
        
        total_q = int(num_questions_str.split("문항")[0])
        st.info(f"⏳ {total_q}문항을 생성 중입니다... 이번엔 진짜 뚫립니다!")
        
        html_content = asyncio.run(generate_exam(model, total_q, subject, difficulty))
        final_html = HTML_TEMPLATE.replace("{content}", html_content)
        
        st.success("✅ 출제 완료!")
        st.download_button("📥 시험지 다운로드", data=final_html, file_name="exam.html", mime="text/html")
        st.components.v1.html(final_html, height=800, scrolling=True)

    except Exception as e:
        st.error(f"❌ 전체 오류: {e}")

