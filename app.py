import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
import asyncio
import smtplib
import random
import json
import time
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 1. 환경 설정 및 API 보안 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("Secrets 설정(PAID_API_KEY, EMAIL_USER, EMAIL_PASS)이 필요합니다!")
    st.stop()

db = TinyDB('user_registry.json')
User = Query()
bank_db = TinyDB('question_bank.json')
QBank = Query()

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
        msg.attach(MIMEText(f"안녕하세요. 요청하신 인증번호는 [{code}] 입니다.", 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASS)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        return False

def check_user_limit(email):
    if email == ADMIN_EMAIL: return True, "무제한 (관리자)"
    user = db.table('users').get(User.email == email)
    if not user:
        db.table('users').insert({'email': email, 'count': 0})
        return True, 5
    remaining = 5 - user['count']
    return (remaining > 0), remaining

# --- 3. 수능 블루프린트 ---
def get_exam_blueprint(choice_subject, total_num, custom_score=None):
    blueprint = []
    if total_num == 30:
        for i in range(1, 23):
            if i in [1, 2]: score = 2; diff = "쉬움"; domain = "지수와 로그 / 함수의 극한"
            elif i in [3, 4, 5, 6, 7]: score = 3; diff = "보통"; domain = "삼각함수 / 미분 / 적분 기본"
            elif i in [8, 9, 10, 11, 12]: score = 4; diff = "준킬러"; domain = "다항함수의 미적분 / 수열"
            elif i in [13, 14]: score = 4; diff = "준킬러(복합)"; domain = "도함수의 활용 / 삼각함수 도형"
            elif i == 15: score = 4; diff = "킬러(고난도)"; domain = "수열의 귀납적 정의 (추론)"
            elif i in [16, 17, 18, 19]: score = 3; diff = "보통"; domain = "방정식 / 지수로그 연산"
            elif i in [20, 21]: score = 4; diff = "준킬러(고난도)"; domain = "정적분으로 정의된 함수 / 그래프 추론"
            elif i == 22: score = 4; diff = "초고난도(최종 킬러)"; domain = "다항함수의 추론과 미분"
            else: score = 3; diff = "보통"; domain = "수학 I, II"
            
            q_type = "객관식" if i <= 15 else "단답형"
            blueprint.append({"num": i, "sub": "수학 I, II", "diff": diff, "score": score, "type": q_type, "domain": domain})
            
        for i in range(23, 31):
            if i in [23, 24]: score = 2; diff = "쉬움"; domain = f"{choice_subject} 기본 연산"
            elif i in [25, 26, 27]: score = 3; diff = "보통"; domain = f"{choice_subject} 기본 응용"
            elif i in [28, 29]: score = 4; diff = "준킬러(고난도)"; domain = f"{choice_subject} 심화 응용"
            elif i == 30: score = 4; diff = "초고난도(최종 킬러)"; domain = f"{choice_subject} 최고난도 융합 추론"
            else: score = 3; diff = "보통"; domain = choice_subject
            
            q_type = "객관식" if i <= 28 else "단답형"
            blueprint.append({"num": i, "sub": choice_subject, "diff": diff, "score": score, "type": q_type, "domain": domain})
    else:
        for i in range(1, total_num + 1):
            score = custom_score if custom_score else 3
            diff = "쉬움" if score == 2 else "보통" if score == 3 else "어려움(4점)"
            blueprint.append({"num": i, "sub": choice_subject, "diff": diff, "score": score, "type": "객관식", "domain": f"{choice_subject} 전범위"})
    return blueprint

# --- 4. HTML/CSS 템플릿 (선지 분리 디자인 강화) ---
def get_html_template(subject, pages_html, solutions_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script>
            window.MathJax = {{ tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$']] }}, chtml: {{ scale: 0.98, matchFontHeight: true }} }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
            * {{ font-family: 'Nanum Myeongjo', serif !important; word-break: keep-all; letter-spacing: -0.5px; }}
            body {{ background: #f0f2f6; margin: 0; padding: 0; color: #000; }}
            .btn-download {{ position: fixed; top: 20px; right: 20px; padding: 12px 24px; background: #000; color: #fff; border: none; cursor: pointer; z-index: 1000; font-weight: bold; border-radius: 5px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); transition: background 0.2s; }}
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
            
            /* 객관식 선지 완벽 정렬 CSS */
            .options-container {{ 
                margin-top: 25px; /* 문제 텍스트와 분리 */
                display: flex; 
                justify-content: space-between; /* 5개 선지 좌우 균등 분할 */
                font-size: 10.5pt; 
                padding: 0 5px;
            }}
            .options-container span {{ display: inline-block; }}
            
            .condition-box {{ border: 1.5px solid #000; padding: 10px 15px; margin: 10px 0; font-weight: bold; background: #fafafa; }}
            .sol-section {{ border-top: 5px double #000; padding-top: 40px; }}
            .sol-item {{ margin-bottom: 35px; padding-bottom: 20px; border-bottom: 1px dashed #eee; line-height: 1.85; font-size: 10.5pt; }}
            .sol-step {{ margin-top: 8px; margin-bottom: 8px; padding-left: 10px; border-left: 3px solid #ccc; }}
            mjx-container:not([display="true"]) {{ margin: 0 2px !important; }}
            @media print {{ @page {{ size: A4; margin: 0; }} body {{ background: white; }} .btn-download {{ display: none !important; }} .paper-container {{ padding: 0; }} .paper {{ box-shadow: none; margin: 0; page-break-after: always; padding: 15mm; min-height: 297mm; }} }}
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

# --- 5. [AI 로직 & 무한 자동 축적 시스템] ---
sem = asyncio.Semaphore(6)

async def generate_single_ai_q(q_info, retry=4):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    
    if q_info['score'] == 4:
        diff_instruction = "수능 4점 심화 추론 문제. (가), (나) 조건 박스 <div class='condition-box'>(가) ...<br>(나) ...</div> 필수 포함."
        sol_instruction = "논리적 단계별(Step 1...)로 자세하게 <div class='sol-step'> 태그 사용해 해설."
    else:
        diff_instruction = "수능 2~3점 기본 응용. 계산 위주 명료하게 출제."
        sol_instruction = "수식 전개 위주로 가장 간결하게 작성."

    type_instruction = "5지선다 객관식이므로 'options' 배열에 5개의 선지 내용을 문자열로 넣을 것." if q_info['type'] == "객관식" else "단답형이므로 'options'는 빈 배열 [] 로 둘 것."

    # JSON 구조 강제 (선지를 배열로 분리)
    prompt = f"""
    단원: {q_info['domain']} | 배점: {q_info['score']}점 | 유형: {q_info['type']}
    [규칙] 1. 100% 한국어. 정답은 해설 끝에. 2. {diff_instruction} 3. {sol_instruction} 4. {type_instruction} 5. 수식은 $ $ 
    
    오직 아래 JSON 형식만 반환 (절대 마크다운 쓰지 말 것):
    {{
        "question": "(문제 텍스트만)",
        "options": ["답1", "답2", "답3", "답4", "답5"],
        "solution": "(해설 및 정답)"
    }}
    """

    for attempt in range(retry):
        await asyncio.sleep(random.uniform(0.1, 1.0))
        async with sem:
            try:
                res = await model.generate_content_async(
                    prompt, 
                    generation_config=genai.types.GenerationConfig(temperature=0.7, response_mime_type="application/json")
                )
                text = res.text.strip()
                if text.startswith("```json"): text = text[7:]
                if text.startswith("```"): text = text[3:]
                if text.endswith("```"): text = text[:-3]
                
                data = json.loads(text.strip())
                return {
                    "num": q_info.get('num', 0), "sub": q_info['sub'], "diff": q_info['diff'], 
                    "score": q_info['score'], "type": q_info['type'], "domain": q_info['domain'],
                    "question": data.get("question", "오류"), 
                    "options": data.get("options", []),
                    "solution": data.get("solution", "오류").replace("The final answer is", "정답은")
                }
            except Exception as e:
                if attempt == retry - 1: return None
                await asyncio.sleep(2 ** attempt)

async def get_or_generate_question(q_info, used_ids):
    available_qs = bank_db.search((QBank.domain == q_info['domain']) & (QBank.type == q_info['type']) & (QBank.score == q_info['score']))
    fresh_qs = [q for q in available_qs if q.doc_id not in used_ids]
    
    if fresh_qs:
        selected = random.choice(fresh_qs)
        used_ids.add(selected.doc_id)
        return {
            "num": q_info['num'], "score": q_info['score'],
            "question": selected['question'], "options": selected.get('options', []),
            "solution": selected['solution'], "source": "DB"
        }
    
    new_q = await generate_single_ai_q(q_info)
    if new_q:
        new_q['num'] = q_info['num']
        return {**new_q, "source": "AI", "raw_data": new_q}
    else:
        return {"num": q_info['num'], "score": q_info['score'], "question": "API 과부하 오류", "options": [], "solution": "오류", "source": "ERROR"}

async def generate_exam_orchestrator(choice_subject, total_num, custom_score=None):
    blueprint = get_exam_blueprint(choice_subject, total_num, custom_score)
    start_time = time.time()
    used_ids = set()
    
    tasks = [get_or_generate_question(q, used_ids) for q in blueprint]
    results = await asyncio.gather(*tasks)
    
    for res in results:
        if res.get("source") == "AI" and "raw_data" in res:
            bank_db.insert(res["raw_data"])
            
    results.sort(key=lambda x: x['num'])
    
    pages_html, sol_html = "", ""
    for i in range(0, len(results), 2):
        pair = results[i:i+2]
        q_content = ""
        for item in pair:
            # 파이썬 로직에서 객관식 선지 HTML 조립 (띄어쓰기 완벽 보장)
            opts = item.get('options', [])
            if opts and len(opts) >= 5:
                opt_html = f"<div class='options-container'><span>① {opts[0]}</span><span>② {opts[1]}</span><span>③ {opts[2]}</span><span>④ {opts[3]}</span><span>⑤ {opts[4]}</span></div>"
            else:
                opt_html = ""
            
            q_content += f"<div class='question-box'><span class='q-num'>{item['num']}</span> {item['question']} <span class='q-score'>[{item['score']}점]</span>{opt_html}</div>"
            sol_html += f"<div class='sol-item'><b>{item['num']}번 해설:</b> {item['solution']}</div>"
        
        pages_html += f"<div class='paper'><div class='header'><h1>2026학년도 대학수학능력시험 모의평가</h1><h3>수학 영역 ({choice_subject})</h3></div><div class='question-grid'>{q_content}</div></div>"
    
    db_hits = sum(1 for r in results if r.get('source') == 'DB')
    return pages_html, sol_html, time.time() - start_time, db_hits

# --- 백그라운드 DB 10,000제 무한 생성 스레드 (Auto-Farming) ---
def run_auto_farmer():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(auto_farm_loop())

async def auto_farm_loop():
    while True:
        try:
            if len(bank_db) < 10000:
                sub = random.choice(["수학 I, II", "미적분", "확률과 통계", "기하"])
                score = random.choice([2, 3, 4])
                diff = "쉬움" if score == 2 else "보통" if score == 3 else "어려움"
                q_type = random.choice(["객관식", "단답형"]) if score > 2 else "객관식"
                
                q_info = {"num": 0, "sub": sub, "diff": diff, "score": score, "type": q_type, "domain": f"{sub} 랜덤"}
                res = await generate_single_ai_q(q_info, retry=1)
                if res:
                    bank_db.insert(res)
            await asyncio.sleep(12) # 12초마다 1문제씩 서버 몰래 조용히 적립 (과부하 X)
        except Exception:
            await asyncio.sleep(12)

# 앱 실행 시 딱 한 번만 백그라운드 스레드 가동
if 'auto_farmer_started' not in st.session_state:
    t = threading.Thread(target=run_auto_farmer, daemon=True)
    t.start()
    st.session_state.auto_farmer_started = True

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
    
    if not st.session_state.verified:
        if st.button("인증번호 발송"):
            if email_input:
                code = str(random.randint(100000, 999999))
                if send_verification_email(email_input, code):
                    st.session_state.auth_code = code
                    st.session_state.mail_sent = True
                    st.success("인증 메일 발송 완료!")
            else: st.warning("이메일을 입력하세요.")
        
        if st.session_state.mail_sent:
            code_input = st.text_input("인증번호 6자리")
            if st.button("인증 확인"):
                if code_input == st.session_state.auth_code:
                    st.session_state.verified = True
                    st.session_state.mail_sent = False
                    st.rerun()
                else: st.error("인증번호 불일치")

    if st.session_state.verified:
        st.divider()
        mode = st.radio("발간 모드", ["맞춤 문항 발간", "30문항 풀세트 발간"])
        choice_sub = st.selectbox("선택과목", ["미적분", "확률과 통계", "기하"])
        
        custom_score_val = None
        if mode == "맞춤 문항 발간":
            num = st.slider("문항 수", 2, 10, 4, step=2)
            score_option = st.selectbox("문항 난이도 (배점)", ["2점 (쉬움)", "3점 (보통)", "4점 (어려움)"])
            custom_score_val = int(score_option[0])
        else:
            num = 30
        
        generate_btn = st.button("🚀 지능형 자동 발간", use_container_width=True)
        
        st.divider()
        st.caption(f"🗄️ 백그라운드 DB 축적량: {len(bank_db)} / 10000 개")
        st.caption("(앱을 켜두시면 12초마다 자동으로 1문제씩 알아서 채워집니다.)")

# 메인 화면 영역
if st.session_state.verified:
    can_use, remain = check_user_limit(email_input)
    if can_use:
        diff_info = f"{custom_score_val}점 맞춤" if custom_score_val else "수능 표준"
        st.info(f"📊 남은 횟수: {remain} | 과목: {choice_sub} | 난이도: {diff_info}")
        
        if 'generate_btn' in locals() and generate_btn:
            with st.spinner(f"DB 검색 및 AI 렌더링을 안전하게 동시 진행 중입니다..."):
                p, s, elapsed, db_hits = asyncio.run(generate_exam_orchestrator(choice_sub, num, custom_score_val))
                
                st.success(f"✅ 발간 완료! (소요 시간: {elapsed:.1f}초 | DB 사용: {db_hits}개, 신규 안전 생성: {num - db_hits}개)")
                st.components.v1.html(get_html_template(choice_sub, p, s), height=1400, scrolling=True)
                
                if email_input != ADMIN_EMAIL:
                    user_data = db.table('users').get(User.email == email_input)
                    db.table('users').update({'count': user_data['count'] + 1}, User.email == email_input)
    else:
        st.error("🚫 이용 한도(계정당 5회)를 모두 소진했습니다.")
else:
    st.info("💡 좌측 사이드바에서 이메일 인증을 완료하면 시스템이 활성화됩니다.")
