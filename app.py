import streamlit as st
import google.generativeai as genai

st.set_page_config(page_title="고속 수능 모의고사", page_icon="⚡", layout="wide")
st.title("⚡ 1분 완성: 고속 수능 모의고사 시스템")

# 1. 넉넉한 풀이 공간(250px)과 2단 레이아웃 유지
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        @page {{ size: A4; margin: 10mm; }}
        body {{ font-family: 'Batang', serif; line-height: 1.6; color: black; background: #fff; }}
        .no-print {{ text-align: right; max-width: 210mm; margin: 10px auto; }}
        .btn-print {{ padding: 10px 20px; background: #000; color: white; border: none; cursor: pointer; font-weight: bold; border-radius: 5px; }}
        .paper {{ max-width: 210mm; margin: 0 auto; background: white; padding: 15mm; min-height: 297mm; }}
        .header {{ text-align: center; border-bottom: 2.5px solid black; padding-bottom: 10px; margin-bottom: 25px; }}
        .twocolumn {{ column-count: 2; column-gap: 45px; column-rule: 0.8px solid black; }}
        .question {{ margin-bottom: 250px; position: relative; padding-left: 30px; page-break-inside: avoid; }}
        .q-num {{ font-weight: bold; font-size: 14pt; position: absolute; left: 0; top: 0; }}
        .options {{ display: flex; flex-wrap: wrap; justify-content: space-between; margin-top: 15px; font-size: 10.5pt; }}
        .opt-item {{ min-width: 18%; margin-bottom: 8px; }}
        .solution-page {{ page-break-before: always; border-top: 3px double black; margin-top: 60px; padding-top: 40px; }}
        @media print {{ .no-print {{ display: none; }} }}
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-print" onclick="window.print()">📥 PDF 저장 / 인쇄</button></div>
    <div class="paper">
        <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h2>수학 영역 ({subject})</h2></div>
        <div class="twocolumn">{content}</div>
    </div>
    <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};</script>
</body>
</html>
"""

# 2. 메인 로직: 단일 호출 고속 생성
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    # 가장 빠르고 답변 한도가 넉넉한 2.5 Flash 모델 사용
    model = genai.GenerativeModel('models/gemini-2.5-flash')

    with st.sidebar:
        st.header("📋 고속 출제 설정")
        sub = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        num = st.radio("문항 수", [5, 10, 30], index=2)
        diff = st.select_slider("난이도", options=["기초", "수능형", "심화"], value="수능형")

    if st.sidebar.button("🚀 1분 이내 초고속 발간"):
        with st.status("🚀 AI가 시험지를 통째로 찍어내는 중입니다...", expanded=True) as status:
            # AI에게 끊김 없이 한 번에 다 내놓으라고 강력히 지시
            prompt = f"""
            너는 수능 출제 위원이야. 인사말 없이 오직 HTML 태그만 출력해.
            수능 수학 {sub} {num}문제를 한 번에 작성해. 난이도: {diff}.
            수식은 $ 기호를 사용하고, 각 문제는 <div class='question'> 구조를 지켜야 해.
            문제 뒤에 바로 '정답과 해설' 섹션을 이어서 HTML로 작성해.
            절대 중간에 끊지 말고 끝까지 한 번에 출력해.
            """
            
            try:
                # [핵심] 답변 길이를 최대(8192 토큰)로 설정하여 끊김 방지
                response = model.generate_content(
                    prompt, 
                    generation_config={"max_output_tokens": 8192, "temperature": 0.7}
                )
                
                res_text = response.text.replace('```html', '').replace('```', '').strip()
                # 수식 및 기호 정제
                clean_html = res_text.replace('\\\\', '\\').replace('\\W', '\\')
                
                if clean_html:
                    final_page = HTML_TEMPLATE.format(subject=sub, content=clean_html)
                    st.success("✅ 생성 완료!")
                    st.components.v1.html(final_page, height=1200, scrolling=True)
                else:
                    st.error("❌ 생성된 내용이 없습니다. 다시 시도해 주세요.")
                    
            except Exception as e:
                st.error(f"❌ 고속 생성 실패: {e}")
            
            status.update(label="⚡ 발간 작업 종료", state="complete")
