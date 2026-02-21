import streamlit as st
import google.generativeai as genai
import itertools
import time

# 1. 페이지 설정 및 모델 명칭 최적화
# 'models/' 접두사를 제거하여 404 에러를 원천 방지합니다.
MODEL_NAME = 'gemini-2.0-flash'

st.set_page_config(page_title="2026 수능 수학 무한 생성기", page_icon="♾️", layout="wide")

# 2. 디자인 템플릿 (수식 보존 및 PDF 완벽 대응)
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
                filename: '2026_무한수능_수학.pdf',
                image: {{ type: 'jpeg', quality: 0.98 }},
                html2canvas: {{ scale: 2, useCORS: true }},
                jsPDF: {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
            }};
            html2pdf().set(opt).from(element).save();
        }}
    </script>
    <style>
        body {{ font-family: 'Batang', serif; line-height: 1.6; background: #f4f4f4; padding: 20px; }}
        .paper {{ max-width: 210mm; margin: 0 auto; background: white; padding: 15mm; min-height: 297mm; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; border-bottom: 2.5px solid black; padding-bottom: 10px; margin-bottom: 25px; }}
        .twocolumn {{ column-count: 2; column-gap: 45px; column-rule: 0.8px solid black; }}
        .question {{ margin-bottom: 250px; position: relative; padding-left: 30px; page-break-inside: avoid; }}
        .q-num {{ font-weight: bold; font-size: 14pt; position: absolute; left: 0; top: 0; }}
        @media (max-width: 768px) {{ .twocolumn {{ column-count: 1; }} .question {{ margin-bottom: 60px; }} }}
    </style>
</head>
<body>
    <div style="text-align:right; max-width:210mm; margin: 0 auto 10px;">
        <button onclick="downloadPDF()" style="padding:10px 20px; background:#28a745; color:white; border:none; border-radius:5px; cursor:pointer;">📥 PDF 저장</button>
    </div>
    <div class="paper">
        <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h2>수학 영역 ({subject})</h2></div>
        <div class="twocolumn">{questions}</div>
        <div style="page-break-before: always; border-top: 3px double black; padding-top: 40px;">
            <h2 style="text-align:center;">정답 및 상세 해설</h2>
            {solutions}
        </div>
    </div>
</body>
</html>
"""

# 3. 배럭 상태 관리 (성능 보장 로직)
if "API_KEYS" in st.secrets:
    all_keys = list(st.secrets["API_KEYS"])
    if "key_pool" not in st.session_state:
        st.session_state.key_pool = {k: True for k in all_keys}
else:
    st.error("Secrets에 API_KEYS 리스트를 등록해주세요.")
    st.stop()

def get_healthy_key(user_key):
    if user_key: return user_key, "개인 전용"
    healthy = [k for k, v in st.session_state.key_pool.items() if v]
    if not healthy:
        st.session_state.key_pool = {k: True for k in all_keys} # 강제 리셋
        return all_keys[0], "공용 리셋"
    return healthy[0], "공용 배럭"

# 4. 무한 루프 방지 및 안전 생성 엔진
def generate_safe_exam(subject, total, diff, user_key):
    all_qs, all_sols = "", ""
    progress_bar = st.progress(0)
    i = 1
    
    while i <= total:
        current_key, k_type = get_healthy_key(user_key)
        genai.configure(api_key=current_key)
        
        try:
            model = genai.GenerativeModel(MODEL_NAME)
            prompt = f"수능 수학 {subject} {i}번 킬러 문항 제작. 난이도: {diff}. HTML <div class='question'>과 [해설시작] 뒤 <div class='sol-card'> 형식으로 출력. 수식은 $ 사용."
            
            response = model.generate_content(prompt)
            text = response.text.replace('```html', '').replace('```', '').strip()
            
            if "[해설시작]" in text:
                q, s = text.split("[해설시작]", 1)
                all_qs += q.strip()
                all_sols += s.strip()
                i += 1
                progress_bar.progress(min((i-1)/total, 1.0))
                time.sleep(2) # RPM 보호
            else: continue
            
        except Exception as e:
            if "429" in str(e):
                if k_type == "개인 전용": user_key = None
                else: st.session_state.key_pool[current_key] = False
                continue
            elif "404" in str(e):
                st.error("🚫 모델명을 확인해주세요. 'models/' 접두사를 제거해야 합니다.")
                break
            else:
                st.error(f"오류: {e}")
                break
    return all_qs, all_sols

# 5. UI 구성
with st.sidebar:
    st.title("♾️ 무한 킬러 시스템")
    user_api = st.text_input("🔑 개인 API Key (한도 초과 시 입력)", type="password")
    st.link_button("🌐 무료 키 발급받기", "https://aistudio.google.com/app/apikey")
    st.divider()
    sub_opt = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
    num_opt = st.radio("문항 수", [5, 10, 30], index=0)
    diff_opt = st.select_slider("난이도", options=["기초", "표준", "킬러"], value="킬러")

if st.sidebar.button("🚀 무한 동력 발간"):
    with st.status("🔮 10배럭 시스템 가동 중...") as status:
        qs, sols = generate_safe_exam(sub_opt, num_opt, diff_opt, user_api)
        if qs:
            final_html = HTML_TEMPLATE.format(subject=sub_opt, questions=qs, solutions=sols)
            st.components.v1.html(final_html, height=1000, scrolling=True)
            status.update(label="발간 완료!", state="complete")
