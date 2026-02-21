import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="2026 수능 수학 킬러 마스터", page_icon="🔥", layout="wide")
st.title("🔥 최종 킬러 마스터: 고속 생성 & 정밀 해설")

# 1. 디자인 템플릿 (250px 여백 및 해설 가독성 극대화)
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
        .question {{ 
            margin-bottom: 250px; /* 문제 풀이 공간 충분히 확보 */
            position: relative; padding-left: 30px; 
            page-break-inside: avoid; word-break: keep-all; 
        }}
        .q-num {{ font-weight: bold; font-size: 14pt; position: absolute; left: 0; top: 0; }}
        .solution-page {{ page-break-before: always; border-top: 3px double black; margin-top: 60px; padding-top: 40px; }}
        .sol-card {{ border: 1.5px solid #000; padding: 15px; margin-bottom: 25px; background: #fafafa; }}
        .sol-header {{ font-weight: bold; font-size: 1.1em; border-bottom: 1px solid #000; padding-bottom: 5px; margin-bottom: 10px; }}
        .sol-step {{ margin-bottom: 8px; padding-left: 10px; border-left: 3px solid #666; }}
        @media print {{ .no-print {{ display: none; }} }}
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-print" onclick="window.print()">📥 PDF 저장 / 인쇄</button></div>
    <div class="paper">
        <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h2>수학 영역 ({subject})</h2></div>
        <div class="twocolumn">{questions}</div>
        <div class="solution-page">
            <h2 style="text-align:center; border: 2px solid black; display: inline-block; padding: 5px 30px; margin-bottom: 30px;">정답 및 상세 해설</h2>
            <div>{solutions}</div>
        </div>
    </div>
    <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};</script>
</body>
</html>
"""

# 2. 고속 병렬 처리 (킬러 최적화: 2문항씩 쪼개기)
async def fetch_killer_chunk(model, start, end, subject, diff):
    count = end - start + 1
    # 환각 방지 및 수학 전문성 강화 지시
    prompt = f"""
    너는 대한민국 수능 수학 출제 위원이야. 인사말이나 프로그래밍 코드(Javascript 등)는 절대 출력하지 마.
    오직 고등학교 수학 교육과정에 맞는 HTML 태그만 출력해.
    
    {subject} 과목의 {start}번부터 {end}번까지 총 {count}문제를 만드시오. 난이도: {diff}(최상).
    
    [구조 가이드]
    1. 문제: <div class='question'><span class='q-num'>{start}.</span> 문제내용... </div>
    2. 문제들 바로 다음에 반드시 [해설시작] 구분자를 넣으시오.
    3. 해설: <div class='sol-card'>
               <div class='sol-header'>[{start}번 정답 및 해설]</div>
               <div class='sol-step'><b>단계 1: 문제 해석</b> - ...</div>
               <div class='sol-step'><b>단계 2: 전략 수립</b> - ...</div>
               <div class='sol-step'><b>단계 3: 정답 도출</b> - ...</div>
             </div>
    4. 수식은 $ 기호를 사용해.
    """
    
    try:
        # API 할당량 소진 방지를 위한 미세한 지연
        await asyncio.sleep(1) 
        response = await model.generate_content_async(prompt)
        text = response.text.replace('```html', '').replace('```', '').strip()
        text = text.replace('\\\\', '\\').replace('\\W', '\\') # 기호 교정
        
        if "[해설시작]" in text:
            q_part, s_part = text.split("[해설시작]", 1)
            return q_part.strip(), s_part.strip()
        return text, ""
    except:
        return "", ""

async def generate_fast_killer(model, subject, total, diff):
    # 킬러는 2개씩, 일반은 5개씩 쪼개어 비서 투입
    chunk_size = 2 if diff == "킬러" else 5
    tasks = [fetch_killer_chunk(model, i, min(i+chunk_size-1, total), subject, diff) 
             for i in range(1, total + 1, chunk_size)]
    
    results = await asyncio.gather(*tasks)
    
    # 순서대로 모으기
    all_q = "".join([r[0] for r in results])
    all_s = "".join([r[1] for r in results])
    return all_q, all_s

# 3. 메인 로직
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('models/gemini-2.5-flash') # 고속 모델

    with st.sidebar:
        st.header("⚙️ 킬러 고속 발간 설정")
        sub_opt = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        num_opt = st.radio("문항 수", [5, 10, 30], index=1)
        diff_opt = st.select_slider("난이도", options=["기초", "표준", "킬러"], value="킬러")
        st.divider()
        st.warning("⚠️ 30문항 킬러는 AI 연산량이 많아 2~3분이 소요됩니다.")

    if st.sidebar.button("🚀 3분 이내 고속 발간"):
        with st.status(f"⏳ {diff_opt}형 문제를 병렬로 제작 중입니다...") as status:
            try:
                # 비동기 실행
                questions, solutions = asyncio.run(generate_fast_killer(model, sub_opt, num_opt, diff_opt))
                
                if questions:
                    final_html = HTML_TEMPLATE.format(subject=sub_opt, questions=questions, solutions=solutions)
                    st.success("✅ 발간 완료! 상단 버튼을 눌러 PDF로 저장하세요.")
                    st.components.v1.html(final_html, height=1200, scrolling=True)
                else:
                    st.error("❌ 생성 실패. API 키의 일일 한도를 확인해 주세요.")
            except Exception as e:
                st.error(f"❌ 오류 발생: {e}")
            status.update(label="발간 작업 종료", state="complete")

