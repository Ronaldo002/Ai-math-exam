import streamlit as st
import google.generativeai as genai
import time

st.set_page_config(page_title="2026 수능 수학 완성기", page_icon="📝", layout="wide")

# 1. 넉넉한 여백(250px)과 깨끗한 수능 양식 유지
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
        .question {{ margin-bottom: 250px; position: relative; padding-left: 30px; page-break-inside: avoid; word-break: keep-all; }}
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
        <div class="header">
            <h1>2026학년도 대학수학능력시험 모의평가</h1>
            <h2>수학 영역 ({subject})</h2>
        </div>
        <div class="twocolumn">{questions}</div>
        <div class="solution-page">
            <h2 style="text-align:center; border: 1.5px solid black; display: inline-block; padding: 5px 30px; margin-bottom: 30px;">정답 및 상세 해설</h2>
            <div>{solutions}</div>
        </div>
    </div>
    <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};</script>
</body>
</html>
"""

# 2. 쿼터 초과 방지형 순차 생성기
def generate_stable_exam(model, subject, total, diff):
    all_content = ""
    bar = st.progress(0)
    status = st.empty()
    
    # 쿼터 문제를 피하기 위해 3문제씩 아주 천천히 생성합니다.
    chunk_size = 3 
    for i in range(1, total + 1, chunk_size):
        end = min(i + chunk_size - 1, total)
        status.info(f"⏳ {i}~{end}번 문항 생성 중... (서버 안정화 대기 포함)")
        
        prompt = f"인사말 없이 HTML만 출력. 수능 수학 {subject} {i}~{end}번 문항과 해설을 <div class='question'> 구조로 만드시오. 난이도: {diff}."
        
        try:
            # 1. 생성 시도
            response = model.generate_content(prompt)
            res_text = response.text.replace('```html', '').replace('```', '').strip()
            all_content += res_text.replace('\\\\', '\\').replace('\\W', '\\')
            
            # 2. 진행바 업데이트
            bar.progress(end / total)
            
            # 3. [핵심] 무료 한도(Quota)를 지키기 위해 강제 휴식 (10초)
            if end < total:
                time.sleep(10) 
                
        except Exception as e:
            st.warning(f"⚠️ 서버 한도 도달! 20초간 휴식 후 자동으로 재시도합니다... (에러: {e})")
            time.sleep(20) # 차단 시 더 길게 대기
            # 실패한 부분부터 다시 시도하기 위해 루프 인덱스 조정
            continue 
            
    return all_content

# 3. 메인 로직
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('models/gemini-2.5-flash')

    with st.sidebar:
        st.header("📄 시험지 설정 (안전 모드)")
        sub = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        num = st.radio("문항 수", [5, 10, 30])
        diff = st.select_slider("난이도", options=["기초", "수능형", "심화"])

    if st.sidebar.button("🚀 안전 모드로 완주하기"):
        st.warning("안전 모드는 서버 차단을 막기 위해 약 2~3분이 소요됩니다. 잠시만 기다려주세요.")
        full_html = generate_stable_exam(model, sub, num, diff)
        
        if full_html:
            final_page = HTML_TEMPLATE.format(subject=sub, questions=full_html, solutions="해설은 하단에 자동 포함되었습니다.")
            st.success("✅ 드디어 30문항 완주 성공! PDF로 저장하세요.")
            st.components.v1.html(final_page, height=1200, scrolling=True)
