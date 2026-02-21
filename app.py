import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="수능 수학 킬러 마스터", page_icon="🔥", layout="wide")
st.title("🔥 AI 수능 수학 시스템 (킬러형 고속 최적화)")

# 1. 디자인 템플릿 (250px 여백 및 해설 가독성 강화)
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
        .btn-print {{ padding: 10px 20px; background: #000; color: white; border: none; cursor: pointer; border-radius: 4px; font-weight: bold; }}
        .paper {{ max-width: 210mm; margin: 0 auto; background: white; padding: 12mm; min-height: 297mm; }}
        .header {{ text-align: center; border-bottom: 2.5px solid black; padding-bottom: 10px; margin-bottom: 25px; }}
        .twocolumn {{ column-count: 2; column-gap: 45px; column-rule: 0.8px solid black; }}
        .question {{ margin-bottom: 250px; position: relative; padding-left: 30px; page-break-inside: avoid; word-break: keep-all; }}
        .q-num {{ font-weight: bold; font-size: 14pt; position: absolute; left: 0; top: 0; }}
        .solution-box {{ border: 1px solid #ddd; padding: 15px; margin-bottom: 20px; background: #f9f9f9; border-radius: 5px; }}
        .sol-step {{ margin-bottom: 10px; border-left: 3px solid #333; padding-left: 10px; }}
        .solution-page {{ page-break-before: always; border-top: 3px double black; margin-top: 60px; padding-top: 40px; }}
        @media print {{ .no-print {{ display: none; }} }}
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-print" onclick="window.print()">📥 PDF 저장 / 인쇄</button></div>
    <div class="paper">
        <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h2>수학 영역 ({subject})</h2></div>
        <div class="twocolumn">{questions}</div>
        <div class="solution-page">
            <h2 style="text-align:center; border: 1.5px solid black; padding: 5px 30px; margin-bottom: 30px;">정답 및 상세 해설</h2>
            <div>{solutions}</div>
        </div>
    </div>
    <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};</script>
</body>
</html>
"""

# 2. 고속 병렬 처리 로직 (킬러형 최적화)
async def fetch_chunk(model, start_num, end_num, subject, difficulty):
    target_count = end_num - start_num + 1
    # 해설 가독성을 위한 단계별 풀이 지시 강화
    prompt = f"""
    인사말 없이 HTML만 출력. 수능 수학 {subject} {start_num}~{end_num}번 문항({target_count}개) 제작.
    난이도: {difficulty} (최상위권 변별력을 위한 복잡한 사고력 요구)

    [출력 가이드]
    1. 문제는 <div class='question'> 구조 유지.
    2. 해설은 [해설시작] 뒤에 작성하되, 반드시 아래 구조를 지킬 것:
       <div class='solution-box'>
         <b>[{start_num}번 정답: ○]</b>
         <div class='sol-step'><b>단계 1: 문제 해석</b> - ...</div>
         <div class='sol-step'><b>단계 2: 핵심 원리 적용</b> - ...</div>
         <div class='sol-step'><b>단계 3: 최종 계산</b> - ...</div>
       </div>
    3. 수식은 $ 사용.
    """
    
    try:
        response = await model.generate_content_async(prompt)
        text = response.text.replace('```html', '').replace('```', '').strip()
        text = text.replace('\\\\', '\\').replace('\\W', '\\')
        
        if "[해설시작]" in text:
            parts = text.split("[해설시작]")
            return parts[0].strip(), parts[1].strip()
        return text, ""
    except:
        return "", ""

async def generate_full_exam(model, subject, total_q, difficulty):
    # 킬러형은 2문제씩 더 잘게 쪼개서 병렬도를 높임 (속도 개선 핵심)
    chunk_size = 2 if difficulty == "킬러" else 5
    tasks = [fetch_chunk(model, i, min(i+chunk_size-1, total_q), subject, difficulty) 
             for i in range(1, total_q + 1, chunk_size)]
    results = await asyncio.gather(*tasks)
    
    all_questions = "".join([r[0] for r in results])
    all_solutions = "".join([r[1] for r in results])
    return all_questions, all_solutions

# 3. 메인 실행부
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('models/gemini-2.5-flash')

    with st.sidebar:
        st.header("⚙️ 스마트 출제 엔진")
        subject_opt = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        num_q = st.radio("문항 수", [5, 10, 30])
        diff_opt = st.select_slider("난이도", options=["기초", "수능형", "킬러"])
        st.divider()
        st.info("⚡ 킬러형 전용 고속 병렬 엔진 가동 중")

    if st.sidebar.button("🚀 모의고사 발간"):
        with st.status(f"⏳ {diff_opt} 모드로 제작 중입니다. 잠시만 기다려주세요...") as status:
            q_html, s_html = asyncio.run(generate_full_exam(model, subject_opt, num_q, diff_opt))
            
            if q_html:
                final_page = HTML_TEMPLATE.format(subject=subject_opt, questions=q_html, solutions=s_html)
                st.success(f"✅ 발간 완료!")
                st.components.v1.html(final_page, height=1200, scrolling=True)
            else:
                st.error("❌ 생성 실패. API 한도를 확인하세요.")
            status.update(label="발간 완료", state="complete")
