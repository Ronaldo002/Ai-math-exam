import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="AI 수능 모의고사 마스터", page_icon="🎓", layout="wide")
st.title("🎓 AI 수능 모의고사 시스템 (PDF & 해설지 지원)")

# 1. 인쇄 및 PDF 최적화 디자인 (여백 확보)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        @page {{ size: A4; margin: 20mm; }}
        body {{ font-family: 'Malgun Gothic', sans-serif; line-height: 1.8; }}
        .paper {{ max-width: 210mm; margin: 0 auto; padding: 10mm; }}
        .header {{ text-align: center; border-bottom: 2px solid black; padding-bottom: 15px; margin-bottom: 30px; }}
        .twocolumn {{ column-count: 2; column-gap: 50px; column-rule: 1px solid #000; }}
        .question {{ 
            margin-bottom: 180px; /* 문제 풀이 공간(여백) 확보 */
            page-break-inside: avoid; 
            min-height: 200px; 
        }}
        .q-number {{ font-weight: bold; font-size: 1.2em; }}
        .ans-section {{ margin-top: 50px; border-top: 3px double #000; padding-top: 20px; page-break-before: always; }}
        @media print {{ 
            .no-print {{ display: none; }} 
            body {{ background: white; }}
            .paper {{ border: none; }}
        }}
    </style>
</head>
<body>
    <div class="paper">
        <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h2>수학 영역 ({subject})</h2></div>
        <div class="twocolumn">{content}</div>
        <div class="ans-section">
            <h2 style="text-align:center;">[ 정답 및 해설 ]</h2>
            <div style="column-count: 1;">{answers}</div>
        </div>
    </div>
    <script>
        window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};
    </script>
</body>
</html>
"""

# 2. AI 문제 및 해설 생성 엔진
async def fetch_exam_data(model, subject, total_q, difficulty):
    prompt = f"""
    너는 수능 수학 출제 위원이야. {subject} 과목의 {total_q}문제를 만들어줘.
    1. 문제는 HTML <div class='question'> 안에 넣어줘. 수식은 $ 기호로 감싸줘.
    2. 모든 문제 뒤에는 반드시 '해설' 섹션을 따로 만들어서 상세한 풀이 과정과 정답을 포함해줘.
    3. 수식 기호 오류(\\W 등)를 범하지 마.
    """
    try:
        response = await model.generate_content_async(prompt)
        raw_text = response.text.replace('```html', '').replace('```', '')
        # 기호 교정 로직 적용
        clean_text = raw_text.replace('\\W', '\\').replace('\\\\', '\\')
        
        # 문제와 해설 분리 시도 (AI에게 구조화 요청)
        if "해설" in clean_text:
            parts = clean_text.split("해설")
            return parts[0], "<h3>풀이 과정</h3>" + "".join(parts[1:])
        return clean_text, "해설 생성 중 오류가 발생했습니다."
    except Exception as e:
        return f"오류 발생: {e}", ""

# 3. UI 및 실행부
with st.sidebar:
    st.header("⚙️ 출제 설정")
    subject = st.sidebar.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
    num_q = st.sidebar.radio("문항 수", [5, 10, 30])
    difficulty = st.sidebar.select_slider("난이도", options=["기초", "표준", "킬러"])
    st.warning("⚠️ PDF 저장은 생성된 화면에서 '인쇄' 버튼을 눌러 'PDF로 저장'을 선택하세요.")

if st.sidebar.button("🚀 모의고사 & 해설지 생성"):
    try:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('models/gemini-2.5-flash') #
        
        st.info(f"⏳ {num_q}문항과 상세 해설을 생성 중입니다... (약 30초 소요)")
        
        # 문제 및 해설 생성
        exam_html, answer_html = asyncio.run(fetch_exam_data(model, subject, num_q, difficulty))
        
        final_page = HTML_TEMPLATE.format(
            subject=subject, 
            content=exam_html, 
            answers=answer_html
        )
        
        st.success("✅ 생성 완료! 아래 미리보기에서 수식을 확인하고 인쇄(PDF 저장)하세요.")
        
        # 브라우저 인쇄 기능을 유도하는 버튼
        st.components.v1.html(final_page, height=1000, scrolling=True)
        
    except Exception as e:
        st.error(f"❌ 실패: {e}")

