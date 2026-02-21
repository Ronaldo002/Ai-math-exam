import streamlit as st
import google.generativeai as genai
import itertools
import time

st.set_page_config(page_title="2026 수능 수학 무한 생성기", page_icon="♾️", layout="wide")

# 1. 디자인 템플릿 (수식 보존 & 모바일 PDF 완벽 대응)
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
                filename: '2026_무한수능_모의고사.pdf',
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
        .btn-download {{ padding: 12px 25px; background: #28a745; color: white; border: none; cursor: pointer; border-radius: 8px; font-weight: bold; }}
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
    <div class="no-print"><button class="btn-download" onclick="downloadPDF()">📥 PDF 파일 직접 저장</button></div>
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

# 2. 지능형 키 관리 시스템 (Key Health Check)
if "API_KEYS" in st.secrets:
    all_keys = list(st.secrets["API_KEYS"])
    if "key_pool" not in st.session_state:
        # 모든 키를 '정상(True)'으로 초기화
        st.session_state.key_pool = {k: True for k in all_keys}
else:
    st.error("Secrets에 API_KEYS 리스트를 설정해주세요.")
    st.stop()

def get_next_healthy_key():
    # 현재 사용 가능한 키만 필터링
    healthy_keys = [k for k, v in st.session_state.key_pool.items() if v]
    if not healthy_keys:
        st.warning("🔄 모든 키의 한도가 초과되었습니다. 30초 후 전체 리셋합니다...")
        time.sleep(30)
        st.session_state.key_pool = {k: True for k in all_keys}
        return all_keys[0]
    return healthy_keys[0]

# 3. 안전 모드 생성 엔진 (에러 키 자동 격리)
def generate_unlimited_exam(subject, total, diff):
    all_qs = ""
    all_sols = ""
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    i = 1
    while i <= total:
        chunk_size = 2 if diff == "킬러" else 5
        start, end = i, min(i + chunk_size - 1, total)
        
        current_key = get_next_healthy_key()
        genai.configure(api_key=current_key)
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        
        status_text.text(f"⏳ {start}~{end}번 문항 제작 중... (배럭 {all_keys.index(current_key)+1}번 가동)")
        
        prompt = f"""인사말 없이 HTML만 출력. 수능 수학 {subject} {start}~{end}번 문항 제작. 난이도: {diff}. 
        수식은 $ 사용하되 백슬래시(\) 두 번씩 입력. 문제는 <div class='question'>, 해설은 [해설시작] 뒤 <div class='sol-card'> 구조."""
        
        try:
            response = model.generate_content(prompt)
            text = response.text.replace('```html', '').replace('```', '').strip()
            text = text.replace('\\\\', '\\').replace('\\W', '\\') #
            
            if "[해설시작]" in text:
                q, s = text.split("[해설시작]", 1)
                all_qs += q.strip()
                all_sols += s.strip()
            else:
                all_qs += text
            
            progress_bar.progress(end / total)
            i += chunk_size
            time.sleep(2) # 안정적인 로테이션을 위한 짧은 대기
            
        except Exception as e:
            if "429" in str(e):
                # 에러 난 키는 블랙리스트에 추가하고 다른 키로 즉시 재시도
                st.session_state.key_pool[current_key] = False
                status_text.warning(f"🚫 {all_keys.index(current_key)+1}번 배럭 한도 초과! 다음 배럭으로 전환합니다...")
                continue 
            else:
                st.error(f"오류 발생: {e}")
                break
                
    return all_qs, all_sols

# 4. 앱 UI
st.sidebar.title("♾️ 무한 킬러 시스템")
sub_opt = st.sidebar.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
num_opt = st.sidebar.radio("문항 수", [5, 10, 30], index=1)
diff_opt = st.sidebar.select_slider("난이도", options=["기초", "표준", "킬러"], value="킬러")
st.sidebar.divider()
active_count = sum(st.session_state.key_pool.values())
st.sidebar.info(f"✅ 가용 배럭: {active_count} / {len(all_keys)}")

if st.sidebar.button("🚀 무한 동력 발간"):
    with st.status("⚡ 지능형 키 로테이션 가동 중...") as status:
        qs, sols = generate_unlimited_exam(sub_opt, num_opt, diff_opt)
        
        if qs:
            final_html = HTML_TEMPLATE.format(subject=sub_opt, questions=qs, solutions=sols)
            st.components.v1.html(final_html, height=1200, scrolling=True)
            st.success("✅ 모든 에러를 우회하여 발간에 성공했습니다!")
        status.update(label="발간 완료", state="complete")
