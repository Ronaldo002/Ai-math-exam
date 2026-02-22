import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
import concurrent.futures
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

# --- 1. 환경 설정 및 API 보안 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("Secrets 설정(PAID_API_KEY, EMAIL_USER, EMAIL_PASS)이 필요합니다!")
    st.stop()

db = TinyDB('user_registry.json')
User = Query()

SENDER_EMAIL = st.secrets.get("EMAIL_USER", "pgh001002@gmail.com")
SENDER_PASS = st.secrets.get("EMAIL_PASS", "gmjg cvsg pdjq hnpw")
ADMIN_EMAIL = "pgh001002@gmail.com"

# --- 2. 이메일 인증 및 권한 로직 ---
def send_verification_email(receiver_email, code):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = receiver_email
        msg['Subject'] = "[Premium 수능수학] 인증번호 발송"
        msg.attach(MIMEText(f"안녕하세요. 요청하신 인증번호는 [{code}] 입니다.\n화면에 번호를 입력하여 인증을 완료해 주세요.", 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASS)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"메일 발송 에러: {e}")
        return False

def check_user_limit(email):
    if email == ADMIN_EMAIL:
        return True, "무제한 (관리자)"
    user = db.table('users').get(User.email == email)
    if not user:
        db.table('users').insert({'email': email, 'count': 0})
        return True, 5
    remaining = 5 - user['count']
    return (remaining > 0), remaining

# --- 3. [업데이트] 배점 선택이 추가된 수능 블루프린트 ---
def get_exam_blueprint(choice_subject, total_num, custom_score=None):
    blueprint = []
    if total_num == 30:
        # 30문항 풀세트 (수능 표준 배점)
        for i in range(1, 23):
            if i <= 2: score = 2; diff = "쉬움"
            elif i <= 8: score = 3; diff = "보통"
            elif i in [15, 21, 22]: score = 4; diff = "킬러(고난도)"
            else: score = 4; diff = "준킬러"
            q_type = "객관식" if i <= 15 else "단답형(주관식)"
            blueprint.append({"num": i, "sub": "수학 I, II", "diff": diff, "score": score, "type": q_type})
            
        for i in range(23, 31):
            if i <= 24: score = 2; diff = "쉬움"
            elif i <= 27: score = 3; diff = "보통"
            elif i == 30: score = 4; diff = "최종 킬러"
            else: score = 4; diff = "준킬러"
            q_type = "객관식" if i <= 28 else "단답형(주관식)"
            blueprint.append({"num": i, "sub": choice_subject, "diff": diff, "score": score, "type": q_type})
    else:
        # 맞춤 문항 발간 (선택한 난이도/배점 반영)
        for i in range(1, total_num + 1):
            score = custom_score if custom_score else 3
            diff = "쉬움" if score == 2 else "보통" if score == 3 else "어려움(4점)"
            blueprint.append({"num": i, "sub": choice_subject, "diff": diff, "score": score, "type": "객관식"})
    return blueprint

# --- 4. 가독성 최적화 & PDF 다운로드 템플릿 ---
def get_html_template(subject, pages_html, solutions_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script>
            window.MathJax = {{
                tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$']] }},
                chtml: {{ scale: 0.98, matchFontHeight: true }} 
            }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
            * {{ font-family: 'Nanum Myeongjo', serif !important; word-break: keep-all; letter-spacing: -0.5px; }}
            body {{ background: #f0f2f6; margin: 0; padding: 0; color: #000; }}
            
            .btn-download {{ 
                position: fixed; top: 20px; right: 20px; padding: 12px 24px; 
                background: #000; color: #fff; border: none; cursor: pointer; 
                z-index: 1000; font-weight: bold; border-radius: 5px; 
                box-shadow: 0 4px 6px rgba(0,0,0,0.3); transition: background 0.2s;
            }}
            .btn-download:hover {{ background: #333; }}

            .paper-container {{ display: flex; flex-direction: column; align-items: center; padding: 20px 0; }}
            .paper {{ background: white; width: 210mm; padding: 15mm 18mm; margin-bottom: 30px; min-height: 297mm; position: relative; box-shadow: 0 5px 20px rgba(0,0,0,0.08); }}
            .header {{ text-align: center; border-bottom: 2.5px solid #000; padding-bottom: 12px; margin-bottom: 35px; }}
            .header h1 {{ font-weight: 800; font-size: 26pt; margin: 0; letter-spacing: -1.5px; }}
            .header h3 {{ font-weight: 700; font-size: 14pt; margin-top: 10px; }}
            
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 55px; min-height: 220mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #ddd; }}
            
            .question-box {{ position: relative; line-height: 2.0; font-size: 11pt; padding-left: 36px; margin-bottom: 45px; text-align: justify; word-break: break-all; }}
            .q-num {{ position: absolute; left: 0; top: 4px; font-weight: 800; border: 2px solid #000; width: 25px; height: 25px; text-align: center; line-height: 23px; font-size: 11.5pt; background: #fff; }}
            .q-score {{ font-weight: 700; font-size: 10.5pt; margin-left: 5px; }}
            .options-container {{ margin-top: 15px; font-size: 10.5pt; }}
            
            .sol-section {{ border-top: 5px double #000; padding-top: 40px; }}
            .sol-item {{ margin-bottom: 35px; padding-bottom: 20px; border-bottom: 1px dashed #eee; line-height: 1.85; font-size: 10.5pt; }}
            
            /* 해설지 내 단계별 풀이 가독성 강화 */
            .sol-step {{ margin-top: 8px; margin-bottom: 8px; padding-left: 10px; border-left: 3px solid #ccc; }}
            
            mjx-container:not([display="true"]) {{ margin: 0 2px !important; }}

            @media print {{
                @page {{ size: A4; margin: 0; }}
                body {{ background: white; }}
                .btn-download {{ display: none !important; }}
                .paper-container {{ padding: 0; }}
                .paper {{ box-shadow: none; margin: 0; page-break-after: always; padding: 15mm; min-height: 297mm; }}
            }}
        </style>
    </head>
    <body>
        <button class="btn-download" onclick="window.print()">📥 PDF 저장</button>
        <div class="paper-container">
            {pages_html}
            <div class="paper sol-section"><h2 style="text-align:center;">[정답 및 해설]</h2>{solutions_html}</div>
        </div>
    </body>
    </html>
    """

# --- 5. [업데이트] 난이도 맞춤 해설 생성 로직 ---
def fetch_paged_question(q_info):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    
    type_instruction = "①~⑤ 기호로 5지선다 선지 포함." if q_info['type'] == "객관식" else "선지 없는 단답형(정답은 3자리 이하 자연수)."
    
    # 배점(난이도)에 따른 해설지 동적 스타일링
    if q_info['score'] <= 3:
        sol_instruction = "해설 작성 시: 주저리주저리 긴 서술형 문장을 빼고, 수식 전개 위주로 가장 간결하고 깔끔하게 정답 도출 과정만 보여주세요."
    else:
        sol_instruction = "해설 작성 시: 4점 고난도 문항이므로 학생들이 쉽게 이해할 수 있도록 풀이 과정을 논리적 단계별(Step 1, Step 2...)로 나누어 아주 자세하고 친절하게 설명해 주세요. 가독성을 위해 <div class='sol-step'> 태그를 활용해 단락을 구분하세요."

    prompt = f"""
    과목:{q_info['sub']} | 번호:{q_info['num']}번 | 난이도:{q_info['diff']} | 배점:{q_info['score']}점 | 유형:{q_info['type']}
    
    [필수 규칙 - 위반 시 에러]
    1. 100% 한국어로만 작성 (영어 설명 절대 금지). 정답은 "정답: 3" 형태로 명시.
    2. HTML 구조 보호: 임의로 문제 영역에 <br>, <div> 태그를 넣어 레이아웃을 깨지 말 것.
    3. 수식은 반드시 $ $ 로 감쌀 것.
    4. {type_instruction}
    5. {sol_instruction}
    
    [출력형식]
    [문항] <div class='question-box'><span class='q-num'>{q_info['num']}</span> (여기에 문제 내용) <span class='q-score'>[{q_info['score']}점]</span><div class='options-container'>(선지)</div></div> ---SPLIT--- [해설] <div class='sol-item'><b>{q_info['num']}번 해설:</b> (여기에 맞춤형 풀이 작성)</div>
    """
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.7)
        )
        raw_text = response.text.replace("```html", "").replace("```", "").strip()
        raw_text = raw_text.replace("The final answer is", "정답은")
        return raw_text

    except Exception as e: 
        return f"[문항] <div class='question-box'><span class='q-num'>{q_info['num']}</span> 생성 중 오류 발생</div> ---SPLIT--- [해설] <div class='sol-item'><b>{q_info['num']}번 해설:</b> 오류</div>"

def generate_exam(choice_subject, total_num, custom_score=None):
    blueprint = get_exam_blueprint(choice_subject, total_num, custom_score)
    start_time = time.time()
    
    # 100스레드 풀가동
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        results = list(executor.map(fetch_paged_question, blueprint))
    
    results.sort(key=lambda x: int(x.split('q-num\'>')[1].split('</span>')[0]) if 'q-num\'>' in x else 999)
    pages_html, sol_html = "", ""
    for i in range(0, len(results), 2):
        pair = results[i:i+2]
        q_content = ""
        for item in pair:
            if "---SPLIT---" in item:
                parts = item.split("---SPLIT---")
                q_content += parts[0].replace("[문항]", "")
                sol_html += parts[1].replace("[해설]", "")
            else:
                q_content += f"<div class='question-box'><span class='q-num'>!</span> 렌더링 오류 (SPLIT 누락)</div>"
        
        pages_html += f"""
        <div class="paper">
            <div class="header"><h1>2026학년도 대학수학능력시험 모의평가</h1><h3>수학 영역 ({choice_subject})</h3></div>
            <div class="question-grid">{q_content}</div>
        </div>
        """
    return pages_html, sol_html, time.time() - start_time

# --- 6. UI 및 세션 관리 ---
st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")

if 'verified' not in st.session_state: st.session_state.verified = False
if 'auth_code' not in st.session_state: st.session_state.auth_code = None
if 'mail_sent' not in st.session_state: st.session_state.mail_sent = False

with st.sidebar:
    st.title("🎓 본부 인증")
    email_input = st.text_input("이메일 입력", value=ADMIN_EMAIL if st.session_state.verified else "")
    
    if email_input == ADMIN_EMAIL:
        st.session_state.verified = True
        st.success("👑 관리자 자동 인증 완료")
    
    if not st.session_state.verified:
        if st.button("인증번호 발송"):
            if email_input:
                code = str(random.randint(100000, 999999))
                if send_verification_email(email_input, code):
                    st.session_state.auth_code = code
                    st.session_state.mail_sent = True
                    st.success("인증 메일 발송 완료!")
            else:
                st.warning("이메일을 입력하세요.")
        
        if st.session_state.mail_sent:
            code_input = st.text_input("인증번호 6자리 입력")
            if st.button("인증 확인"):
                if code_input == st.session_state.auth_code and st.session_state.auth_code:
                    st.session_state.verified = True
                    st.session_state.mail_sent = False
                    st.rerun()
                else:
                    st.error("인증번호가 일치하지 않습니다.")

    # [업데이트] 맞춤 문항 발간 시 난이도(배점) 선택 UI 추가
    if st.session_state.verified:
        st.divider()
        mode = st.radio("발간 모드", ["맞춤 문항 발간", "30문항 풀세트 발간"])
        choice_sub = st.selectbox("선택과목", ["미적분", "확률과 통계", "기하"])
        
        custom_score_val = None
        if mode == "맞춤 문항 발간":
            num = st.slider("문항 수", 2, 10, 4, step=2)
            # 배점 선택 드롭다운 추가
            score_option = st.selectbox("문항 난이도 (배점)", ["2점 (쉬움)", "3점 (보통)", "4점 (어려움)"])
            custom_score_val = int(score_option[0]) # '2', '3', '4' 파싱
        else:
            num = 30
        
        generate_btn = st.button("🚀 초고속 시험지 발간 시작", use_container_width=True)

# 메인 화면 영역
if st.session_state.verified:
    can_use, remain = check_user_limit(email_input)
    if can_use:
        diff_info = f"{custom_score_val}점 맞춤" if custom_score_val else "수능 표준"
        st.info(f"📊 남은 횟수: {remain} | 과목: {choice_sub} | 난이도: {diff_info}")
        
        if 'generate_btn' in locals() and generate_btn:
            with st.spinner(f"⚡ AI 코어 100개를 풀가동하여 문항을 렌더링 중입니다..."):
                # 커스텀 배점을 파라미터로 넘김
                p, s, elapsed = generate_exam(choice_sub, num, custom_score_val)
                
                st.success(f"✅ 발간 완료! (소요 시간: {elapsed:.1f}초)")
                st.components.v1.html(get_html_template(choice_sub, p, s), height=1400, scrolling=True)
                
                if email_input != ADMIN_EMAIL:
                    user_data = db.table('users').get(User.email == email_input)
                    db.table('users').update({'count': user_data['count'] + 1}, User.email == email_input)
    else:
        st.error("🚫 이용 한도(계정당 5회)를 모두 소진했습니다.")
else:
    st.info("💡 좌측 사이드바에서 이메일 인증을 완료하면 시스템이 활성화됩니다.")
