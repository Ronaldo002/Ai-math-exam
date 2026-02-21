import streamlit as st
import google.generativeai as genai
import asyncio
import itertools

st.set_page_config(page_title="2026 수능 수학 킬러 마스터", page_icon="🔥", layout="wide")
st.title("🔥 최종 킬러 마스터: 멀티 키 자동 순환 시스템")

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
        .question {{ margin-bottom: 250px; position: relative; padding-left: 30px; page-break-inside: avoid; word-break: keep-all; }}
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

# API 키 순환자 설정
if "API_KEYS" in st.secrets:
    key_cycle = itertools.cycle(st.secrets["API_KEYS"])
else:
    st.error("Secrets에 API_KEYS 리스트를 설정해주세요.")
    st.stop()

# 2. 멀티 키 로테이션 기반 병렬 생성 함수
async def fetch_with_rotation(start, end, subject, diff):
    current_key = next(key_cycle)
    genai.configure(api_key=current_key)
    model = genai.GenerativeModel('models/gemini-2.5-flash') #
    
    target_count = end - start + 1
    prompt = f"""인사말 없이 HTML만 출력. 수능 수학 {subject} {start}~{end}번 문항({target_count}개) 제작. 난이도: {diff}. 
    문제: <div class='question'> 구조, 해설: [해설시작] 뒤 <div class='sol-card'> 구조. 수식은 $ 사용. 자바스크립트 금지."""
    
    try:
        await asyncio.sleep(0.5) # 서버 부하 분산
        response = await model.generate_content_async(prompt)
        text = response.text.replace('```html', '').replace('```', '').strip()
        text = text.replace('\\\\', '\\').replace('\\W', '\\') #
        
        if "[해설시작]" in text:
            return text.split("[해설시작]", 1)
        return text, ""
    except Exception as e:
        return f"", ""

async def generate_auto_rotation(subject, total, diff):
    chunk_size = 2 if diff == "킬러" else 5
    tasks = [fetch_with_rotation(i, min(i+chunk_size-1, total), subject, diff) 
             for i in range(1, total + 1, chunk_size)]
    results = await asyncio.gather(*tasks)
    return "".join([r[0] for r in results]), "".join([r[1] for r in results])

# 3. UI 및 메인 실행
with st.sidebar:
    st.header("⚙️ 스마트 멀티 키 엔진")
    sub_opt = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
    num_opt = st.radio("문항 수", [5, 10, 30], index=1)
    diff_opt = st.select_slider("난이도", options=["기초", "표준", "킬러"], value="킬러")
    st.info(f"🔑 등록된 키 개수: {len(st.secrets['API_KEYS'])}개")

if st.sidebar.button("🚀 자동 로테이션 발간"):
    with st.status("⏳ 여러 개의 키를 사용하여 고속 제작 중...") as status:
        qs, sols = asyncio.run(generate_auto_rotation(sub_opt, num_opt, diff_opt))
        if qs:
            final_html = HTML_TEMPLATE.format(subject=sub_opt, questions=qs, solutions=sols)
            st.components.v1.html(final_html, height=1200, scrolling=True)
        else:
            st.error("모든 키의 한도가 초과되었습니다.")
        status.update(label="발간 완료", state="complete")

