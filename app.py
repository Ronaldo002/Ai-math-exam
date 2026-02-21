import streamlit as st
import google.generativeai as genai

st.set_page_config(page_title="AI 모의고사 생성기", page_icon="⚡", layout="wide")
st.title("⚡ AI 수능 모의고사 생성기 (초고속 30초 완성)")
st.markdown("클라우드 서버의 한계를 돌파했습니다! 10초 만에 다운로드 후 브라우저에서 바로 인쇄(PDF 저장)하세요.")

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
        .paper { max-width: 210mm; min-height: 1200mm; margin: 0 auto; background: white; padding: 20mm; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .header { text-align: center; border-bottom: 2px solid black; padding-bottom: 10px; margin-bottom: 20px; }
        .header h1 { margin: 0; font-size: 24px; font-weight: bold; }
        .header h2 { margin: 5px 0 0 0; font-size: 18px; font-weight: bold; }
        .twocolumn { column-count: 2; column-gap: 30px; column-rule: 1px solid #ccc; }
        .question { margin-bottom: 40px; page-break-inside: avoid; }
        .q-number { font-weight: bold; font-size: 1.1em; margin-right: 5px; }
        .options { display: flex; justify-content: space-between; margin-top: 15px; font-size: 0.9em; }
        .score { float: right; font-weight: bold; }
        @media print {
            body { background: white; }
            .paper { box-shadow: none; margin: 0; padding: 0; max-width: 100%; height: auto; }
        }
    </style>
</head>
<body>
    <div class="paper">
        <div class="header">
            <h1>2026학년도 대학수학능력시험 모의평가 문제지</h1>
            <h2>수학 영역</h2>
        </div>
        <div class="twocolumn">
            {content}
        </div>
    </div>
</body>
</html>
"""

st.sidebar.header("출제 옵션 설정")
subject = st.sidebar.selectbox("📚 과목 선택", ["미적분", "확률과 통계", "수학 I, II"])
num_questions = st.sidebar.radio("🔢 문항 수", ["5문항 (테스트용)", "10문항", "20문항", "30문항"])
difficulty = st.sidebar.select_slider("🔥 난이도", options=["개념 확인", "수능 실전형", "최상위권 킬러형"])

if st.sidebar.button("🚀 초고속 시험지 만들기"):
    try:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash') 
        
        prompt = f"""
        너는 수능 수학 출제 위원이야. {subject} 과목의 {num_questions} 수능 모의고사를 출제해. 난이도는 '{difficulty}'에 맞춰줘.
        반드시 아래의 HTML 태그 구조를 100% 똑같이 유지해서 작성해. 설명이나 인사말 없이 오직 HTML 코드만 출력할 것.
        수식은 반드시 MathJax 문법(인라인 수식은 \\( ... \\), 블록 수식은 \\[ ... \\])을 사용해.
        
        [필수 조건]
        - 총 12페이지 분량이 되도록 문항 사이에 <br><br> 등으로 여백을 넉넉히 둘 것.
        - 만약 17번 문항을 생성하게 된다면 문제 내용에 [그림 삽입 공간]을 텍스트로 표시할 것.
        - 만약 26번 문항을 생성하게 된다면 문제 내용에 [그래프 삽입 공간]을 텍스트로 표시할 것.

        [반드시 지켜야 할 출력 구조 예시]
        <div class="question">
            <span class="q-number">1.</span> 두 집합 \\( A=\\{{1, 2, 3\\}} \\), \\( B=\\{{2, 3, 4\\}} \\) 에 대하여 \\( A \\cap B \\) 의 모든 원소의 합은? <span class="score">[2점]</span>
            <div class="options">
                <span>① 1</span><span>② 2</span><span>③ 3</span><span>④ 4</span><span>⑤ 5</span>
            </div>
        </div>
        """
        
        st.info("⏳ AI가 초고속으로 문제를 출제하고 있습니다... (약 10~15초 소요)")
        
        response = model.generate_content(prompt)
        
        # AI가 붙일 수 있는 마크다운 찌꺼기 제거
        html_content = response.text.replace('```html', '').replace('```', '')
        
        # 디자인 템플릿에 문제 쏙 넣기
        final_html = HTML_TEMPLATE.replace("{content}", html_content)
        
        st.success("🎉 생성 완료! 아래 버튼을 눌러 다운로드하세요.")
        st.markdown("💡 **꿀팁:** 다운받은 파일을 인터넷 브라우저로 열고, **`Ctrl + P` (인쇄)를 눌러 'PDF로 저장'**을 선택하면 완벽한 2단 분할 PDF 시험지가 됩니다!")
        
        st.download_button(
            label="📥 초고속 시험지 다운로드 (HTML)",
            data=final_html,
            file_name=f"수능_모의고사_{subject}.html",
            mime="text/html"
        )

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
