import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="수능 모의고사 마스터", page_icon="🎓", layout="wide")
st.title("🎓 AI 수능 모의고사 시스템 (문항 수 최적화)")

# 1. 디자인 템플릿 (250px 여백 및 해설 섹션 레이아웃 고정)
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
        .btn-print {{ padding: 10px 20px; background: #333; color: white; border: none; cursor: pointer; border-radius: 4px; }}
        .paper {{ max-width: 210mm; margin: 0 auto; background: white; padding: 12mm; min-height: 297mm; }}
        .header {{ text-align: center; border-bottom: 2.5px solid black; padding-bottom: 10px; margin-bottom: 25px; }}
        .twocolumn {{ column-count: 2; column-gap: 45px; column-rule: 0.8px solid black; }}
        .question {{ margin-bottom: 250px; position: relative; padding-left: 30px; page-break-inside: avoid; }}
        .q-num {{ font-weight: bold; font-size: 14pt; position: absolute; left: 0; top: 0; }}
        .solution-page {{ page-break-before: always; border-top: 3px double black; margin-top: 60px; padding-top: 40px; }}
        @media print {{ .no-print {{ display: none; }} .paper {{ border: none; width: 100%; }} }}
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-print" onclick="window.print()">📥 PDF 저장 / 인쇄</button></div>
    <div class="paper">
        <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h2>수학 영역 ({subject})</h2></div>
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

# 2. 고속 병렬 처리 로직 (문제와 해설을 명확히 구분하여 생성)
async def fetch_chunk(model, start_num, end_num, subject, difficulty):
    target_count = end_num - start_num + 1
    # AI에게 '반드시 지정된 개수의 문제를 생성하라'고 강력히 지시
    prompt = f"""
    인사말이나 서론 없이 오직 HTML 태그만 출력하시오. 
    수능 수학 {subject} 과목의 {start_num}번부터 {end_num}번까지 **총 {target_count}개의 문제**를 반드시 각각 생성하시오.
    난이도는 {difficulty} 수준으로 하시오. 

    [작성 양식]
    1. 각 문제는 반드시 <div class='question'><span class='q-num'>번호.</span> 문제내용... </div> 구조를 가질 것.
    2. 문제 생성이 모두 끝나면 [해설시작] 이라는 구분자를 넣고, 각 번호에 맞는 상세 풀이를 작성할 것.
    3. 수식은 반드시 $ 기호를 사용하여 LaTeX로 작성할 것.
    """
    
    try:
        response = await model.generate_content_async(prompt)
        text = response.text.replace('```html', '').replace('```', '').strip()
        text = text.replace('\\\\', '\\').replace('\\W', '\\') # 수식 깨짐 방지
        
        # 문제와 해설을 분리하여 리턴
        if "[해설시작]" in text:
            parts = text.split("[해설시작]")
            return parts[0].strip(), parts[1].strip()
        return text, ""
    except:
        return "", ""

async def generate_full_exam(model, subject, total_q, difficulty):
    # 비서 5명에게 분배 (예: 1~5번, 6~10번...)
    chunk_size = 5
    tasks = [fetch_chunk(model, i, min(i+chunk_size-1, total_q), subject, difficulty) 
             for i in range(1, total_q + 1, chunk_size)]
    results = await asyncio.gather(*tasks)
    
    all_questions = "".join([r[0] for r in results])
    all_solutions = "".join([r[1] for r in results])
    return all_questions, all_solutions

# 3. 메인 실행부
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('models/gemini-2.5-flash') # 사용 가능 최신 모델

    with st.sidebar:
        st.header("⚙️ 설정")
        subject_opt = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        num_q = st.radio("문항 수", [5, 10, 30])
        diff_opt = st.select_slider("난이도", options=["기초", "수능형", "킬러"])
        st.divider()
        st.info("💡 문항 수와 해설 분리가 강화된 버전입니다.")

    if st.sidebar.button("🚀 모의고사 발간"):
        with st.status(f"⏳ {num_q}개의 문항과 해설을 병렬로 제작 중입니다...") as status:
            try:
                q_html, s_html = asyncio.run(generate_full_exam(model, subject_opt, num_q, diff_opt))
                
                if q_html:
                    # [에러 해결] KeyError 방지용 변수명 일치
                    final_page = HTML_TEMPLATE.format(subject=subject_opt, questions=q_html, solutions=s_html)
                    st.success(f"✅ {num_q}문항 발간 완료!")
                    st.components.v1.html(final_page, height=1200, scrolling=True)
                else:
                    st.error("❌ 생성 실패. API 한도를 확인하거나 잠시 후 시도하세요.")
            except Exception as e:
                st.error(f"❌ 오류 발생: {e}")
            status.update(label="발간 완료", state="complete")
