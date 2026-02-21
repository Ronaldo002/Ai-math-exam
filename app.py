import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="AI 수능 모의고사 생성기", page_icon="📝", layout="wide")
st.title("📝 AI 수능 모의고사 생성기 (수식 최적화 완료)")

# 1. 디자인 템플릿 (MathJax 설정을 강화하여 수식 렌더링 보장)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <script>
        window.MathJax = {
            tex: { inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']] }
        };
    </script>
    <style>
        @page { size: A4; margin: 15mm; }
        body { font-family: 'Malgun Gothic', sans-serif; line-height: 1.8; background: white; }
        .paper { max-width: 210mm; margin: 0 auto; padding: 10mm; border: 1px solid #ccc; }
        .header { text-align: center; border-bottom: 2px solid black; padding-bottom: 10px; margin-bottom: 20px; }
        .twocolumn { column-count: 2; column-gap: 40px; column-rule: 1px solid #000; }
        .question { margin-bottom: 40px; page-break-inside: avoid; }
        .q-number { font-weight: bold; font-size: 1.1em; margin-right: 5px; }
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
    # AI에게 수식 기호를 명확히 사용하도록 지시
    prompt = f""" 너는 수능 수학 출제 위원이야. {subject} 과목 {start_num}~{end_num}번 문항을 HTML로 만들어. 
    수식은 반드시 LaTeX 형식으로 작성하고 양 끝을 $ 기호로 감싸줘. (예: $\\lim_{{x \\to 2}}$)
    역슬래시는 한 번씩만 사용해. 설명 없이 <div> 태그 결과물만 출력해. """
    
    try:
        await asyncio.sleep(0.5)
        response = await model.generate_content_async(prompt)
        # 깨진 글자(\W 등)를 정상적인 LaTeX 기호(\)로 강제 치환
        clean_text = response.text.replace('```html', '').replace('```', '')
        clean_text = clean_text.replace('\\W', '\\').replace('\\\\', '\\') 
        return clean_text
    except Exception as e:
        return f"<p style='color:red;'>⚠️ {start_num}번 생성 실패: {e}</p>"

async def generate_exam(model, total_questions, subject, difficulty):
    chunk_size = 5
    tasks = [fetch_questions(model, i, min(i+chunk_size-1, total_questions), subject, difficulty) 
             for i in range(1, total_questions + 1, chunk_size)]
    results = await asyncio.gather(*tasks)
    return "".join(results)

# 2. 사이드바 및 실행 로직
st.sidebar.header("설정")
subject = st.sidebar.selectbox("과목", ["미적분", "확률과 통계", "수학 I, II"])
num_questions_str = st.sidebar.radio("문항 수", ["5문항", "10문항", "30문항"])
difficulty = st.sidebar.select_slider("난이도", options=["개념 확인", "수능 실전형", "킬러"])

if st.sidebar.button("🚀 모의고사 생성 시작"):
    try:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        
        # 확인된 최신 모델 사용
        model = genai.GenerativeModel('models/gemini-2.5-flash') 
        
        total_q = int(num_questions_str.split("문항")[0])
        st.info(f"⏳ {total_q}문항 생성 중... 수식 렌더링 최적화 적용됨")
        
        html_content = asyncio.run(generate_exam(model, total_q, subject, difficulty))
        final_html = HTML_TEMPLATE.replace("{content}", html_content)
        
        st.success("✅ 출제 완료! 수식이 예쁘게 보일 때까지 1~2초만 기다려 주세요.")
        st.download_button("📥 시험지 저장(HTML)", data=final_html, file_name=f"exam_{subject}.html", mime="text/html")
        st.components.v1.html(final_html, height=1000, scrolling=True)

    except Exception as e:
        st.error(f"❌ 오류: {e}")
