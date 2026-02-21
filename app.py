import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="AI 모의고사 생성기", page_icon="📝", layout="wide")
st.title("📝 AI 수능 모의고사 생성기 (안정적 고속 모드)")

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
        body { font-family: 'Malgun Gothic', sans-serif; line-height: 1.6; background: #eee; }
        .paper { max-width: 210mm; margin: 0 auto; background: white; padding: 20mm; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .header { text-align: center; border-bottom: 2px solid black; padding-bottom: 10px; margin-bottom: 20px; }
        .twocolumn { column-count: 2; column-gap: 30px; column-rule: 1px solid #ccc; }
        .question { margin-bottom: 50px; page-break-inside: avoid; }
        .q-number { font-weight: bold; font-size: 1.1em; }
        .options { display: flex; justify-content: space-between; margin-top: 10px; }
        @media print { body { background: white; } .paper { box-shadow: none; margin: 0; padding: 0; } }
    </style>
</head>
<body>
    <div class="paper">
        <div class="header"><h1>수학 영역 모의평가</h1></div>
        <div class="twocolumn">{content}</div>
    </div>
</body>
</html>
"""

async def fetch_questions(model, start_num, end_num, subject, difficulty):
    prompt = f"너는 수능 출제 위원이야. {subject} 과목 {start_num}~{end_num}번 문제를 HTML로 만들어. 난이도: {difficulty}. 설명 없이 <div>태그만 출력해."
    try:
        # 비동기 호출 시 약간의 시차(0.5초)를 줘서 구글 서버의 차단을 피합니다.
        await asyncio.sleep(0.5) 
        response = await model.generate_content_async(prompt)
        return response.text.replace('```html', '').replace('```', '')
    except:
        return f"<p> {start_num}~{end_num}번 생성 중 지연이 발생했습니다. 다시 시도해 주세요.</p>"

async def generate_exam(model, total_questions, subject, difficulty):
    # 6문제씩 5명으로 조정 (안정성 확보)
    chunk_size = 6 
    tasks = [fetch_questions(model, i, min(i+chunk_size-1, total_questions), subject, difficulty) 
             for i in range(1, total_questions + 1, chunk_size)]
    results = await asyncio.gather(*tasks)
    return "".join(results)

st.sidebar.header("설정")
subject = st.sidebar.selectbox("과목", ["미적분", "확률과 통계", "수학 I, II"])
num_questions_str = st.sidebar.radio("문항 수", ["5문항", "10문항", "30문항"])
difficulty = st.sidebar.select_slider("난이도", options=["개념", "수능형", "킬러"])

if st.sidebar.button("🚀 시험지 생성"):
    try:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash') # 속도가 더 빠른 flash 모델 고정
        
        total_q = int(num_questions_str.split("문항")[0])
        st.info(f"⏳ {total_q}문항을 안정적으로 생성 중입니다...")
        
        html_content = asyncio.run(generate_exam(model, total_q, subject, difficulty))
        final_html = HTML_TEMPLATE.replace("{content}", html_content)
        
        st.success("✅ 생성 완료!")
        st.download_button("📥 HTML 다운로드", data=final_html, file_name="exam.html", mime="text/html")
        st.components.v1.html(final_html, height=800, scrolling=True) # 화면에서 미리보기 추가

    except Exception as e:
        st.error(f"오류: {e}")
