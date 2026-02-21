import streamlit as st
import google.generativeai as genai
import asyncio
import itertools

st.set_page_config(page_title="2026 수능 수학 킬러 마스터", page_icon="🔥", layout="wide")

# 1. 디자인 템플릿 (250px 여백 + 모바일 반응형 + PDF 직접 다운로드)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
    <script>
        function downloadPDF() {{
            const element = document.querySelector('.paper');
            const opt = {{
                margin: [10, 10, 10, 10],
                filename: '2026_수능수학_모의고사.pdf',
                image: {{ type: 'jpeg', quality: 0.98 }},
                html2canvas: {{ scale: 2, useCORS: true }},
                jsPDF: {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
            }};
            html2pdf().set(opt).from(element).save();
        }}
    </script>
    <style>
        /* PC 기본 레이아웃 */
        @page {{ size: A4; margin: 10mm; }}
        body {{ font-family: 'Batang', serif; line-height: 1.6; color: black; background: #f4f4f4; padding: 20px; }}
        .no-print {{ text-align: right; max-width: 210mm; margin: 0 auto 20px; }}
        .btn-download {{ 
            padding: 15px 30px; background: #007bff; color: white; border: none; 
            cursor: pointer; font-weight: bold; border-radius: 8px; font-size: 1.1rem;
        }}
        .paper {{ max-width: 210mm; margin: 0 auto; background: white; padding: 15mm; min-height: 297mm; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; border-bottom: 2.5px solid black; padding-bottom: 10px; margin-bottom: 25px; }}
        .twocolumn {{ column-count: 2; column-gap: 45px; column-rule: 0.8px solid black; }}
        .question {{ margin-bottom: 250px; position: relative; padding-left: 30px; page-break-inside: avoid; word-break: keep-all; }}
        .q-num {{ font-weight: bold; font-size: 14pt; position: absolute; left: 0; top: 0; }}
        
        /* 해설지 스타일 */
        .solution-page {{ page-break-before: always; border-top: 3px double black; margin-top: 60px; padding-top: 40px; }}
        .sol-card {{ border: 1.5px solid #000; padding: 15px; margin-bottom: 25px; background: #fafafa; }}
        .sol-header {{ font-weight: bold; font-size: 1.1em; border-bottom: 1px solid #000; padding-bottom: 5px; margin-bottom: 10px; }}
        .sol-step {{ margin-bottom: 8px; padding-left: 10px; border-left: 3px solid #666; }}

        /* 모바일 반응형 최적화 */
        @media (max-width: 768px) {{
            body {{ padding: 0; }}
            .no-print {{ width: 100%; padding: 10px; }}
            .btn-download {{ width: 100%; }}
            .paper {{ padding: 10px; width: 100%; box-shadow: none; }}
            .twocolumn {{ column-count: 1; }}
            .question {{ margin-bottom: 60px; padding-left: 20px; }}
            .MathJax {{ overflow-x: auto; display: block !important; }}
        }}
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-download" onclick="downloadPDF()">📥 PDF 파일 직접 다운로드</button></div>
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

# 2. 멀티 키 로테이션 설정
if "API_KEYS" in st.secrets:
    key_cycle = itertools.cycle(st.secrets["API_KEYS"])
else:
    st.error("Secrets에 API_KEYS 리스트를 설정해주세요.")
    st.stop()

# 3. 고속 병렬 처리 로직
async def fetch_killer_chunk(start, end, subject, diff):
    current_key = next(key_cycle)
    genai.configure(api_key=current_key)
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    
    target_count = end - start + 1
    prompt = f"""
    인사말 없이 HTML만 출력. 수능 수학 {subject} {start}~{end}번 문항({target_count}개) 제작. 난이도: {diff}.
    [구조 가이드]
    1. 문제: <div class='question'><span class='q-num'>{start}.</span> 문제내용... </div>
    2. 문제들 바로 다음에 반드시 [해설시작] 구분자를 넣으시오.
    3. 해설: <div class='sol-card'>
               <div class='sol-header'>[{start}번 정답 및 해설]</div>
               <div class='sol-step'><b>단계 1: 문제 해석</b> - ...</div>
               <div class='sol-step'><b>단계 2: 정답 도출</b> - ...</div>
             </div>
    4. 수식은 $ 사용. 자바스크립트 코드 출력 금지.
    """
    
    try:
        await asyncio.sleep(0.5) 
        response = await model.generate_content_async(prompt)
        text = response.text.replace('```html', '').replace('```', '').strip()
        text = text.replace('\\\\', '\\').replace('\\W', '\\')
        
        if "[해설시작]" in text:
            q_part, s_part = text.split("[해설시작]", 1)
            return q_part.strip(), s_part.strip()
        return text, ""
    except Exception as e:
        return f"", ""

async def generate_final_exam(subject, total, diff):
    # 킬러형은 2문제씩, 일반은 5문제씩 분할
    chunk_size = 2 if diff == "킬러" else 5
    tasks = [fetch_killer_chunk(i, min(i+chunk_size-1, total), subject, diff) 
             for i in range(1, total + 1, chunk_size)]
    results = await asyncio.gather(*tasks)
    return "".join([r[0] for r in results]), "".join([r[1] for r in results])

# 4. Streamlit UI
st.sidebar.title("🔥 스마트 출제 엔진")
sub_opt = st.sidebar.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
num_opt = st.sidebar.radio("문항 수", [5, 10, 30], index=1)
diff_opt = st.sidebar.select_slider("난이도", options=["기초", "표준", "킬러"], value="킬러")
st.sidebar.divider()
st.sidebar.info(f"🔑 활성화된 API 배럭: {len(st.secrets['API_KEYS'])}개")

if st.sidebar.button("🚀 초고속 모의고사 발간"):
    with st.status("⏳ 멀티 키 병렬 엔진 가동 중...") as status:
        qs, sols = asyncio.run(generate_final_exam(sub_opt, num_opt, diff_opt))
        if qs:
            final_html = HTML_TEMPLATE.format(subject=sub_opt, questions=qs, solutions=sols)
            st.components.v1.html(final_html, height=1200, scrolling=True)
            st.success("✅ 발간 완료!")
        else:
            st.error("API 할당량을 확인해주세요.")
        status.update(label="발간 완료", state="complete")

