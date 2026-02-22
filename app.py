import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
import asyncio
import smtplib
import random
import json
import time
import threading
import re
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 1. 환경 설정 및 API 보안 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("Secrets 설정(PAID_API_KEY, EMAIL_USER, EMAIL_PASS)이 필요합니다!")
    st.stop()

SENDER_EMAIL = st.secrets.get("EMAIL_USER", "pgh001002@gmail.com")
SENDER_PASS = st.secrets.get("EMAIL_PASS", "gmjg cvsg pdjq hnpw")
ADMIN_EMAIL = "pgh001002@gmail.com"

# --- 2. [핵심] DB 및 스레드 자물쇠 (충돌 방지 시스템) ---
@st.cache_resource
def get_databases():
    return TinyDB('user_registry.json'), TinyDB('question_bank.json')

db, bank_db = get_databases()
User = Query()
QBank = Query()

# 스트림릿이 재시작되어도 자물쇠가 유지되도록 캐싱
@st.cache_resource
def get_db_lock():
    return threading.Lock()

DB_LOCK = get_db_lock()

# DB 접근은 무조건 이 함수들을 통해서만 진행 (에러 완전 차단)
def insert_q(doc):
    with DB_LOCK:
        return bank_db.insert(doc)

def search_q(query):
    with DB_LOCK:
        return bank_db.search(query)

def get_db_len():
    with DB_LOCK:
        return len(bank_db)

# --- 3. 이메일 인증 로직 ---
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
    with DB_LOCK:
        user = db.table('users').get(User.email == email)
        if not user:
            db.table('users').insert({'email': email, 'count': 0})
            return True, 5
        remaining = 5 - user['count']
        return (remaining > 0), remaining

# --- 4. 수능 블루프린트 ---
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
            else: score = 3; diff = "보통"; domain = "수학 I, II 기본"
            q_type = "객관식" if i <= 15 else "단답형"
            blueprint.append({"num": i, "sub": "수학 I, II", "diff": diff, "score": score, "type": q_type, "domain": domain})
            
        for i in range(23, 31):
            if i in [23, 24]: score = 2; diff = "쉬움"; domain = f"{choice_subject} 기본 연산"
            elif i in [25, 26, 27]: score = 3; diff = "보통"; domain = f"{choice_subject} 기본 응용"
            elif i in [28, 29]: score = 4; diff = "준킬러(고난도)"; domain = f"{choice_subject} 심화 응용"
            elif i == 30: score = 4; diff = "초고난도(최종 킬러)"; domain = f"{choice_subject} 최고난도 융합 추론"
            else: score = 3; diff = "보통"; domain = f"{choice_subject} 종합"
            q_type = "객관식" if i <= 28 else "단답형"
            blueprint.append({"num": i, "sub": choice_subject, "diff": diff, "score": score, "type": q_type, "domain": domain})
    else:
        for i in range(1, total_num + 1):
            score = custom_score if custom_score else 3
            diff = "쉬움" if score == 2 else "보통" if score == 3 else "어려움(4점)"
            blueprint.append({"num": i, "sub": choice_subject, "diff": diff, "score": score, "type": "객관식", "domain": f"{choice_subject} 전범위"})
    return blueprint

# --- 5. HTML/CSS 템플릿 ---
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
            .options-container {{ margin-top: 25px; display: flex; justify-content: space-between; font-size: 10.5pt; padding: 0 5px; }}
            .options-container span {{ display: inline-block; }}
            .condition-box {{ border: 1.5px solid #000; padding: 10px 15px; margin: 10px 0; font-weight: bold; background: #fafafa; }}
            .svg-container {{ text-align: center; margin: 15px 0; }}
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

# --- 6. 수식 자동 교정 & 데이터 정제 ---
def polish_math(text):
    if not text: return ""
    text = text.replace('Σ', r'\sum').replace('∫', r'\int')
    return text

def process_question_data(item):
    q_text = polish_math(item.get("question", ""))
    opts = item.get("options", [])
    
    if not opts and "①" in q_text:
        parts = q_text.split("①")
        q_text = parts[0].strip()
        raw_opts = "①" + parts[1]
        found_opts = re.split(r'[①②③④⑤]', raw_opts)
        opts = [opt.strip() for opt in found_opts if opt.strip()][:5]
    elif opts and "①" in q_text:
        q_text = q_text.split("①")[0].strip()
        
    return q_text, opts

# --- 7. AI 생성 로직 ---
sem = asyncio.Semaphore(6)

async def generate_batch_ai_qs(q_info, batch_size=5, retry=3):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    batch_id = str(uuid.uuid4())
    
    if q_info['score'] == 4:
        diff_instruction = "수능 4점 고난도. (가), (나) 조건 박스 <div class='condition-box'>(가) ...<br>(나) ...</div> 필수 삽입."
        sol_instruction = "단계별(Step 1...)로 <div class='sol-step'> 태그 사용해 아주 자세하게 해설."
    else:
        diff_instruction = "수능 2~3점 기본/응용. 조건 박스 없이 명료하게 출제."
        sol_instruction = "수식 위주로 간결하게 해설."

    type_instruction = "5지선다. 'question' 문자열엔 절대 선지 번호 쓰지 말고 오직 'options' 배열에 5개 분리할 것." if q_info['type'] == "객관식" else "단답형이므로 'options'는 []."

    prompt = f"""
    [과목 엄수]: {q_info['sub']} | 단원: {q_info['domain']} | 배점: {q_info['score']}점 | 유형: {q_info['type']}
    
    [🚨 초강력 필수 규칙 - 위반 시 에러]
    1. 100% 한국어 작성. {q_info['sub']} 과목의 지식만 사용할 것!
    2. [수식 100% 강제]: 모든 숫자, 변수(x, y), 수식은 조건 박스 안팎을 막론하고 무조건 $ $ 로 감쌀 것!
       - 로그는 $\\log_{{a}}{{x}}$ 정식 LaTeX 사용 (일반 텍스트 log_2 금지).
    3. [SVG 도형 그림]: 단원 특성상 기하, 함수 그래프, 도형 추론이 필요한 경우 반드시 <div class='svg-container'><svg viewBox="0 0 200 200" width="200" height="200"> ... </svg></div> 삽입.
    4. {diff_instruction}
    5. {sol_instruction}
    6. [선지 분리 강제]: {type_instruction}
    
    숫자나 조건만 바꾼 기본 변형부터 창의적 변형까지 섞어서 {batch_size}개의 독립적 문항을 만들 것.
    오직 JSON 배열(Array) 형식만 반환:
    [{{ "question": "...", "options": ["답1","답2","답3","답4","답5"], "solution": "..." }}, ...]
    """

    for attempt in range(retry):
        await asyncio.sleep(random.uniform(0.1, 1.0))
        async with sem:
            try:
                res = await model.generate_content_async(
                    prompt, 
                    generation_config=genai.types.GenerationConfig(temperature=0.8, response_mime_type="application/json")
                )
                text = res.text.strip()
                if text.startswith("```json"): text = text[7:]
                if text.startswith("```"): text = text[3:]
                if text.endswith("```"): text = text[:-3]
                
                data_list = json.loads(text.strip())
                parsed_questions = []
                for data in data_list:
                    parsed_questions.append({
                        "batch_id": batch_id,
                        "sub": q_info['sub'], "diff": q_info['diff'], 
                        "score": q_info['score'], "type": q_info['type'], "domain": q_info['domain'],
                        "question": data.get("question", "오류"), 
                        "options": data.get("options", []),
                        "solution": data.get("solution", "오류").replace("The final answer is", "정답은")
                    })
                return parsed_questions
            except Exception as e:
                if attempt == retry - 1: return []
                await asyncio.sleep(2 ** attempt)

# --- 8. [충돌 방지 로직 적용] Orchestrator ---
@st.cache_resource
def get_domain_locks():
    return {}

domain_locks = get_domain_locks()

async def safe_get_or_generate(q_info, used_ids, used_batch_ids):
    domain = q_info['domain']
    if domain not in domain_locks:
        domain_locks[domain] = asyncio.Lock()
        
    async with domain_locks[domain]:
        # Lock 통제를 받으며 DB 안전 검색
        available_qs = search_q((QBank.sub == q_info['sub']) & (QBank.domain == q_info['domain']) & (QBank.type == q_info['type']) & (QBank.score == q_info['score']))
        
        fresh_qs = []
        for db_q in available_qs:
            if str(db_q.doc_id) in used_ids: continue
            if db_q.get('batch_id') and db_q.get('batch_id') in used_batch_ids: continue
            fresh_qs.append(db_q)
            
        if fresh_qs:
            selected = random.choice(fresh_qs)
            used_ids.add(str(selected.doc_id))
            if 'batch_id' in selected: used_batch_ids.add(selected['batch_id'])
            return {**selected, "num": q_info['num'], "source": "DB"}
        
        # DB에 문제가 없으면 AI 생성 (1번에 5개 묶음)
        new_qs = await generate_batch_ai_qs(q_info, batch_size=5)
        
        if new_qs:
            first_q = None
            for idx, q in enumerate(new_qs):
                # Lock 통제를 받으며 DB 안전 삽입
                doc_id = insert_q(q)
                if idx == 0:
                    first_q = q.copy()
                    first_q['doc_id'] = str(doc_id)
            
            if first_q:
                used_ids.add(first_q['doc_id'])
                if 'batch_id' in first_q: used_batch_ids.add(first_q['batch_id'])
                first_q['num'] = q_info['num']
                first_q['source'] = "AI"
                return first_q
                
        return {"num": q_info['num'], "score": q_info['score'], "type": q_info['type'], "question": "API 로딩 지연", "options": [], "solution": "오류", "source": "ERROR"}

async def generate_exam_orchestrator(choice_subject, total_num, custom_score=None):
    blueprint = get_exam_blueprint(choice_subject, total_num, custom_score)
    start_time = time.time()
    
    used_ids = set()
    used_batch_ids = set()
    
    tasks = [safe_get_or_generate(q, used_ids, used_batch_ids) for q in blueprint]
    results = await asyncio.gather(*tasks)
    
    results.sort(key=lambda x: x.get('num', 999))
    
    pages_html, sol_html = "", ""
    for i in range(0, len(results), 2):
        pair = results[i:i+2]
        q_content = ""
        for item in pair:
            q_text, opts = process_question_data(item)
            
            if item.get('type') == '객관식':
                if opts and len(opts) >= 1:
                    spans = []
                    for idx, opt in enumerate(opts[:5]):
                        clean_opt = re.sub(r'^([①②③④⑤]|[1-5][\.\)])\s*', '', str(opt)).strip()
                        spans.append(f"<span>{chr(9312+idx)} {clean_opt}</span>")
                    opt_html = f"<div class='options-container'>{''.join(spans)}</div>"
                else:
                    opt_html = "<div class='options-container'><span>선지 오류</span></div>"
            else:
                opt_html = ""
            
            q_content += f"<div class='question-box'><span class='q-num'>{item['num']}</span> {q_text} <span class='q-score'>[{item['score']}점]</span>{opt_html}</div>"
            sol_html += f"<div class='sol-item'><b>{item['num']}번 해설:</b> {polish_math(item['solution'])}</div>"
        
        pages_html += f"<div class='paper'><div class='header'><h1>2026학년도 대학수학능력시험 모의평가</h1><h3>수학 영역 ({choice_subject})</h3></div><div class='question-grid'>{q_content}</div></div>"
    
    db_hits = sum(1 for r in results if r.get('source') == 'DB')
    return pages_html, sol_html, time.time() - start_time, db_hits

# --- 9. 백그라운드 DB 1만제 무한 파밍 스레드 ---
def run_auto_farmer():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(auto_farm_loop())

async def auto_farm_loop():
    while True:
        try:
            if get_db_len() < 10000:
                sub = random.choice(["수학 I, II", "미적분", "확률과 통계", "기하"])
                score = random.choice([2, 3, 4])
                diff = "쉬움" if score == 2 else "보통" if score == 3 else "어려움"
                q_type = random.choice(["객관식", "단답형"]) if score > 2 else "객관식"
                
                q_info = {"sub": sub, "diff": diff, "score": score, "type": q_type, "domain": f"{sub} 핵심 랜덤"}
                batch_qs = await generate_batch_ai_qs(q_info, batch_size=5, retry=1)
                for q in batch_qs: 
                    insert_q(q) # Lock 보호 받음
            await asyncio.sleep(20) 
        except Exception:
            await asyncio.sleep(20)

if 'auto_farmer_started' not in st.session_state:
    t = threading.Thread(target=run_auto_farmer, daemon=True)
    t.start()
    st.session_state.auto_farmer_started = True

# --- 10. UI 및 세션 관리 ---
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
        
        generate_btn = st.button("🚀 무결점 자동 발간", use_container_width=True)
        
        if email_input == ADMIN_EMAIL:
            st.divider()
            st.caption(f"🗄️ 백그라운드 DB: {get_db_len()} / 10000 개")
            if st.button("🤖 50문제 수동 충전"):
                with st.spinner("DB에 스펙트럼 문항을 비축 중입니다..."):
                    async def stock_db():
                        q_info = {"sub": choice_sub, "diff": "어려움", "score": 4, "type": "객관식", "domain": f"{choice_sub} 핵심"}
                        tasks = [generate_batch_ai_qs(q_info, batch_size=5) for _ in range(10)]
                        res = await asyncio.gather(*tasks)
                        for batch in res:
                            for q in batch: 
                                insert_q(q) # Lock 보호 받음
                    asyncio.run(stock_db())
                    st.success("충전 완료!")
                    st.rerun()

# 메인 화면 영역
if st.session_state.verified:
    can_use, remain = check_user_limit(email_input)
    if can_use:
        diff_info = f"{custom_score_val}점 맞춤" if custom_score_val else "수능 표준"
        st.info(f"📊 남은 횟수: {remain} | 과목: {choice_sub} | 난이도: {diff_info}")
        
        if 'generate_btn' in locals() and generate_btn:
            with st.spinner(f"DB 충돌 방어 및 완벽 렌더링을 진행 중입니다..."):
                p, s, elapsed, db_hits = asyncio.run(generate_exam_orchestrator(choice_sub, num, custom_score_val))
                
                st.success(f"✅ 발간 완료! (소요 시간: {elapsed:.1f}초 | DB 사용: {db_hits}개, 신규 생성: {num - db_hits}개)")
                st.components.v1.html(get_html_template(choice_sub, p, s), height=1400, scrolling=True)
                
                if email_input != ADMIN_EMAIL:
                    with DB_LOCK:
                        user_data = db.table('users').get(User.email == email_input)
                        db.table('users').update({'count': user_data['count'] + 1}, User.email == email_input)
    else:
        st.error("🚫 이용 한도(계정당 5회)를 모두 소진했습니다.")
else:
    st.info("💡 좌측 사이드바에서 이메일 인증을 완료하면 시스템이 활성화됩니다.")
