import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
from datetime import datetime
import time

# --- 1. 환경 설정 및 보안 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("Streamlit Secrets에 PAID_API_KEY를 등록해주세요!")
    st.stop()

db = TinyDB('service_data.json')
User = Query()

# --- 2. 시험지 HTML/CSS 템플릿 (수식 및 PDF 최적화) ---
def get_html_template(subject, questions_html, solutions_html):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700&display=swap');
            body {{ font-family: 'Noto Serif KR', serif; background: #f0f2f6; padding: 20px; }}
            .paper {{ background: white; width: 210mm; margin: 0 auto; padding: 20mm; box-shadow: 0 0 10px rgba(0,0,0,0.1); min-height: 297mm; color: #000; }}
            .header {{ text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 30px; }}
            .question {{ margin-bottom: 40px; line-height: 1.8; font-size: 1.1em; text-align: left; }}
            .q-num {{ font-weight: bold; margin-right: 10px; font-size: 1.2em; }}
            .sol-section {{ page-break-before: always; border-top: 3px double #000; padding-top: 40px; margin-top: 50px; text-align: left; }}
            .btn-download {{ position: fixed; top: 20px; right: 20px; padding: 12px 24px; background: #ff4b4b; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; z-index: 1000; box-shadow: 0 4px 6px rgba(0,0,0,0.2); }}
        </style>
    </head>
    <body>
        <button class="btn-download" onclick="downloadPDF()">📥 PDF 시험지 다운로드</button>
        <div id="exam-paper" class="paper">
            <div class="header">
                <h1>2026학년도 대학수학능력시험 모의평가</h1>
                <h3>수학 영역 ({subject})</h3>
            </div>
            <div class="content">{questions_html}</div>
            <div class="sol-section">
                <h2 style="text-align:center;">[정답 및 해설]</h2>
                {solutions_html}
            </div>
        </div>
        <script>
            function downloadPDF() {{
                const element = document.getElementById('exam-paper');
                const opt = {{
                    margin: 10,
                    filename: '2026_수능_수학_모의고사.pdf',
                    image: {{ type: 'jpeg', quality: 0.98 }},
                    html2canvas: {{ scale: 2, useCORS: true }},
                    jsPDF: {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
                }};
                html2pdf().set(opt).from(element).save();
            }}
            window.MathJax && MathJax.typesetPromise();
        </script>
    </body>
    </html>
    """

# --- 3. 핵심 로직 함수 ---
def check_user_access(email):
    today = datetime.now().strftime("%Y-%m-%d")
    user = db.table('users').get(User.email == email)
    if not user:
        db.table('users').insert({'email': email, 'count': 0, 'last_date': today})
        return True, 5
    if user['last_date'] != today:
        db.table('users').update({'count': 0, 'last_date': today}, User.email == email)
        return True, 5
    remaining = 5 - user['count']
    return (remaining > 0), remaining

def generate_exam(subject, difficulty, count, email):
    # [핵심수정] 진단 결과(image_f61d5e)에서 확인된 가용 모델 중 최신형인 2.5 flash를 사용합니다.
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    
    q_html_list, s_html_list = [], []
    
    # 진행률 UI 설정
    progress_bar = st.progress(0)
    percent_text = st.empty()
    status_text = st.empty()
    
    for i in range(1, count + 1):
        percent_val = int((i / count) * 100)
        status_text.markdown(f"✍️ **{i}번 문항** 생성 및 검수 중...")
        percent_text.markdown(f"📊 **진행률: {percent_val}%**")
        
        prompt = f"""
        수능 수학 {subject} {difficulty} 난이도 {i}번 문항을 출제하세요.
        반드시 [문항] ... ---SPLIT--- [해설] ... 형식을 지키고 인사말은 생략하세요.
        수식은 반드시 $ 기호를 사용한 LaTeX로 작성하세요.
        """
        
        try:
            response = model.generate_content(prompt)
            raw_text = response.text.replace("```html", "").replace("```", "").strip()
            
            if "---SPLIT---" in raw_text:
                parts = raw_text.split("---SPLIT---")
                q_html_list.append(parts[0].replace("[문항]", "").strip())
                s_html_list.append(parts[1].replace("[해설]", "").strip())
            else:
                q_html_list.append(f"<div class='question'><span class='q-num'>{i}.</span>{raw_text}</div>")
            
            progress_bar.progress(i / count)
            time.sleep(0.5)
            
        except Exception as e:
            st.error(f"{i}번 생성 에러: {e}")
            continue
            
    status_text.success(f"✅ {count}문항 발간이 완료되었습니다!")
    percent_text.empty()
    
    user_data = db.table('users').get(User.email == email)
    db.table('users').update({'count': user_data['count'] + 1}, User.email == email)
    
    return get_html_template(subject, "".join(q_html_list), "".join(s_html_list))

# --- 4. UI 구성 ---
st.set_page_config(page_title="Premium 수능 수학 생성기", layout="wide")

with st.sidebar:
    st.title("🎓 Premium 모드")
    email = st.text_input("사용자 이메일 주소", placeholder="user@example.com")
    st.divider()
    num = st.slider("발간 문항 수", 1, 30, 5)
    sub = st.selectbox("과목 선택", ["수학 I, II", "미적분", "확률과 통계"])
    diff = st.select_slider("난이도 설정", options=["표준", "준킬러", "킬러"])
    st.info("유료 엔진 최적화 및 진행률 표시 기능이 활성화되었습니다.")

if email:
    is_active, left = check_user_access(email)
    if is_active:
        st.write(f"✅ 인증 성공! (오늘 남은 횟수: {left}회)")
        if st.button("🚀 프리미엄 시험지 발간"):
            final_html = generate_exam(sub, diff, num, email)
            st.components.v1.html(final_html, height=1200, scrolling=True)
    else:
        st.error("오늘의 생성 한도를 초과했습니다.")
else:
    st.info("사이드바에 이메일을 입력하면 프리미엄 엔진이 활성화됩니다.")
