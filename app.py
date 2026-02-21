import streamlit as st
import google.generativeai as genai
import itertools
import time

# 1. 최신 모델 및 페이지 설정
# 구글 AI Studio의 최신 정식 명칭인 'gemini-2.0-flash'를 사용합니다.
MODEL_NAME = 'gemini-2.0-flash'

st.set_page_config(page_title="2026 수능 수학 2.5 킬러 마스터", page_icon="🧠", layout="wide")

# 2. 디자인 템플릿 (250px 여백 + 모바일 반응형 + PDF 강제 다운로드)
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
            .question {{ margin-bottom: 60px; padding-left: 20px; }}
            .MathJax {{ overflow-x: auto; display: block !important; }}
        }}
    </style>
</head>
<body>
    <div class="no-print"><button class="btn-download" onclick="downloadPDF()">📥 PDF 파일 직접 저장 (모바일 지원)</button></div>
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

# 3. 하이브리드 키 관리 로직
if "API_KEYS" in st.secrets:
    admin_keys = list(st.secrets["API_KEYS"])
    if "key_pool" not in st.session_state:
        # 모든 공용 배럭을 '사용 가능' 상태로 초기화
        st.session_state.key_pool = {k: True for k in admin_keys}
else:
    st.error("Secrets에 API_KEYS가 등록되지 않았습니다.")
    st.stop()

def get_best_key(user_key):
    # 1순위: 사용자가 직접 입력한 개인 키
    if user_key and len(user_key) > 20:
        return user_key, "개인 전용"
    # 2순위: 관리자의 건강한 공용 키
    healthy_keys = [k for k, v in st.session_state.key_pool.items() if v]
    if healthy_keys:
        return healthy_keys[0], "공용 배럭"
    return None, None

# 4. Gemini 2.5 기반 지능형 생성 엔진
def generate_killer_exam(subject, total, diff, user_key):
    all_qs = ""
    all_sols = ""
    progress_bar = st.progress(0)
    status_msg = st.empty()
    
    i = 1
    while i <= total:
        current_key, key_type = get_best_key(user_key)
        if not current_key:
            st.error("🚨 모든 API 배럭이 전사했습니다. 개인 키를 입력하시면 즉시 가동됩니다!")
            break
            
        genai.configure(api_key=current_key)
        
        try:
            model = genai.GenerativeModel(MODEL_NAME)
            start = i
            status_msg.info(f"⏳ {start}번 킬러 문항 정밀 분석 중... (배럭 타입: {key_type})")
            
            prompt = f"""
            수능 수학 {subject} {start}번 킬러 문항을 제작하라. 난이도: {diff}.
            조건 (가), (나) 등을 활용한 수능 특유의 사고력 문제를 HTML 형식으로 출력하라.
            인사말 없이 <div class='question'> 문제와 [해설시작] 뒤 <div class='sol-card'> 해설만 작성하라.
            수식은 반드시 $ 기호를 사용하고, 백슬래시는 2개(\\\\)씩 입력하라.
            """
            
            response = model.generate_content(prompt)
            text = response.text.replace('```html', '').replace('```', '').strip()
            text = text.replace('\\\\', '\\').replace('\\W', '\\')
            
            if "[해설시작]" in text:
                q, s = text.split("[해설시작]", 1)
                all_qs += q.strip()
                all_sols += s.strip()
                i += 1
                progress_bar.progress(min((i-1)/total, 1.0))
                # 2.5 엔진은 고성능이므로 요청 간 지연시간을 2초로 최적화
                time.sleep(2)
            else:
                continue # 형식 오류 시 해당 번호 재시도
                
        except Exception as e:
            err_str = str(e)
            if "429" in err_str:
                if key_type == "개인 전용":
                    st.warning("⚠️ 개인 키 한도 도달! 공용 배럭으로 전환을 시도합니다.")
                    user_key = None 
                else:
                    st.session_state.key_pool[current_key] = False
                continue
            elif "404" in err_str:
                st.error(f"🚫 모델 '{MODEL_NAME}'을 찾을 수 없습니다. 모델명을 확인하거나 1.5로 낮추세요.")
                break
            else:
                st.error(f"알 수 없는 오류 발생: {e}")
                break
                
    return all_qs, all_sols

# 5. 사이드바 UI 및 실행부
with st.sidebar:
    st.title("🚀 2.5 킬러 마스터")
    st.markdown("---")
    st.subheader("🔑 개인 배럭 가동")
    st.caption("한도 초과 없이 무제한으로 사용하려면 개인 키를 입력하세요.")
    user_api_input = st.text_input("Gemini API Key", type="password")
    st.link_button("👉 10초만에 무료 키 발급", "https://aistudio.google.com/app/apikey")
    st.divider()
    
    sub_opt = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
    num_opt = st.radio("문항 수", [5, 10, 30], index=0)
    diff_opt = st.select_slider("난이도", options=["표준", "준킬러", "킬러"], value="킬러")

if st.sidebar.button("🔥 지능형 모의고사 발간"):
    with st.status("🔮 Gemini 2.5 엔진 분석 중...") as status:
        qs, sols = generate_killer_exam(sub_opt, num_opt, diff_opt, user_api_input)
        if qs:
            final_html = HTML_TEMPLATE.format(subject=sub_opt, questions=qs, solutions=sols)
            st.components.v1.html(final_html, height=1200, scrolling=True)
            st.success("✅ 발간 성공!")
        status.update(label="작업 완료", state="complete")
