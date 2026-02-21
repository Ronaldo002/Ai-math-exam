import streamlit as st
import google.generativeai as genai
import asyncio
import itertools

st.set_page_config(page_title="2026 수능 수학 킬러 마스터", page_icon="🔥", layout="wide")

# 1. 디자인 템플릿 (KeyError 방지를 위해 {questions}, {solutions}로 이름 통일)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script>
        window.MathJax = {{
            tex: {{
                inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
                displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
                processEscapes: true
            }}
        }};
    </script>
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
        @page {{ size: A4; margin: 10mm; }}
        body {{ font-family: 'Batang', serif; line-height: 1.6; color: black; background: #f4f4f4; padding: 20px; }}
        .no-print {{ text-align: right; max-width: 210mm; margin: 0 auto 20px; }}
        .btn-download {{ padding: 12px 25px; background: #007bff; color: white; border: none; cursor: pointer; border-radius: 8px; font-weight: bold; }}
        .paper {{ max-width: 210mm; margin: 0 auto; background: white; padding: 15mm; min-height: 297mm; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; border-bottom: 2.5px solid black; padding-bottom: 10px; margin-bottom: 25px; }}
        .twocolumn {{ column-count: 2; column-gap: 45px; column-rule: 0.8px solid black; }}
        .question {{ margin-bottom: 250px; position: relative; padding-left: 30px; page-break-inside: avoid; word-break: keep-all; }}
        .q-num {{ font-weight: bold; font-size: 14pt; position: absolute; left: 0; top: 0; }}
        .solution-page {{ page-break-before: always; border-top: 3px double black; margin-top: 60px; padding-top: 40px; }}
        .sol-card {{ border: 1.5px solid #000; padding: 15px; margin-bottom: 25px; background: #fafafa; }}
        
        @media (max-width: 768px) {{
            body {{ padding: 0; }}
            .paper {{ padding: 10px; width: 100%; box-shadow: none; }}
            .twocolumn {{ column-count: 1; }}
            .question {{ margin-bottom: 60px; }}
            .MathJax {{ overflow-x: auto; display: block !important; }}
        }}
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-download" onclick="downloadPDF()">📥 PDF 파일 저장 (모바일 지원)</button></div>
    <div class="paper">
        <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h2>수학 영역 ({subject})</h2></div>
        <div class="twocolumn">{questions}</div>
        <div class="solution-page">
            <h2 style="text-align:center; border: 2px solid black; display: inline-block; padding: 5px 30px; margin-bottom: 30px;">정답 및 상세 해설</h2>
            <div>{solutions}</div>
        </div>
    </div>
</body>
</html>
"""

# 2. 멀티 키 설정
if "API_KEYS" in st.secrets:
    key_cycle = itertools.cycle(st.secrets["API_KEYS"])
else:
    st.error("API_KEYS를 설정해주세요.")
    st.stop()

async def fetch_chunk(start, end, subject, diff):
    current_key = next(key_cycle)
    genai.configure(api_key=current_key)
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    
    prompt = f"""
    인사말 없이 HTML만 출력. 수능 수학 {subject} {start}~{end}번 문항({end-start+1}개) 제작. 난이도: {diff}.
    수식은 반드시 $ 기호를 사용하되, 백슬래시(\)가 두 번씩 들어가게 작성해 (예: \\\\frac).
    문제는 <div class='question'>, 해설은 [해설시작] 뒤 <div class='sol-card'> 구조로 작성해.
    """
    
    try:
        await asyncio.sleep(0.5)
        response = await model.generate_content_async(prompt)
        text = response.text.replace('```html', '').replace('```', '').strip()
        text = text.replace('\\\\', '\\').replace('\\W', '\\') # 수식 깨짐 방지
        
        if "[해설시작]" in text:
            q, s = text.split("[해설시작]", 1)
            return q.strip(), s.strip()
        return text, ""
    except:
        return "", ""

# 3. 메인 로직
st.sidebar.title("🔥 최종 킬러 마스터")
sub_opt = st.sidebar.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
num_opt = st.sidebar.radio("문항 수", [5, 10, 30], index=1)
diff_opt = st.sidebar.select_slider("난이도", options=["기초", "표준", "킬러"], value="킬러")

if st.sidebar.button("🚀 초고속 발간"):
    with st.status("⏳ 병렬 엔진 가동 및 수식 최적화 중...") as status:
        chunk_size = 2 if diff_opt == "킬러" else 5
        tasks = [fetch_chunk(i, min(i+chunk_size-1, num_opt), sub_opt, diff_opt) for i in range(1, num_opt + 1, chunk_size)]
        
        try:
            results = asyncio.run(asyncio.gather(*tasks))
            qs = "".join([r[0] for r in results])
            sols = "".join([r[1] for r in results])
            
            if qs:
                # [수정 완료] 템플릿의 변수명 {questions}, {solutions}와 일치시켰습니다.
                final_html = HTML_TEMPLATE.format(subject=sub_opt, questions=qs, solutions=sols)
                st.components.v1.html(final_html, height=1200, scrolling=True)
                st.success("✅ 발간 성공!")
            else:
                st.error("생성된 내용이 없습니다.")
        except Exception as e:
            st.error(f"오류 발생: {e}")
        status.update(label="발간 완료", state="complete")

