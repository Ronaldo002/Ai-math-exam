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

# --- 1. 환경 설정 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("PAID_API_KEY 설정이 필요합니다!")
    st.stop()

ADMIN_EMAIL = "pgh001002@gmail.com"
SENDER_EMAIL = st.secrets.get("EMAIL_USER", "pgh001002@gmail.com")
SENDER_PASS = st.secrets.get("EMAIL_PASS", "gmjg cvsg pdjq hnpw")

# --- 2. DB 및 전역 락 ---
@st.cache_resource
def get_databases():
    return TinyDB('user_registry.json'), TinyDB('question_bank.json')

db, bank_db = get_databases()
User, QBank = Query(), Query()

@st.cache_resource
def get_global_lock():
    return threading.Lock()

DB_LOCK = get_global_lock()

# --- 3. 유틸리티 함수 (에러 방지용 동기 처리) ---
def sync_save_to_db(new_questions):
    """비동기 생성이 모두 끝난 후 안전하게 DB에 일괄 저장 (ValueError 방지)"""
    with DB_LOCK:
        for q in new_questions:
            if not bank_db.search(QBank.question == q['question']):
                bank_db.insert(q)

def get_db_len():
    with DB_LOCK: return len(bank_db)

def polish_math(text):
    if not text: return ""
    # 불필요 문구(image_10833d) 필터링
    text = re.sub(r'^(과목|단원|배점|유형):.*?\n', '', text, flags=re.MULTILINE)
    # 수식 기호 정규화
    text = re.sub(r'log_([a-zA-Z0-9{}]+)', r'\\log_{\1}', text)
    text = re.sub(r'([a-zA-Z])_([a-zA-Z0-9])(?![a-zA-Z0-9{}])', r'\1_{\2}', text)
    text = re.sub(r'([a-zA-Z0-9])\^([a-zA-Z0-9])(?![a-zA-Z0-9{}])', r'\1^{\2}', text)
    return text.strip()

def clean_option(text):
    # 선지 번호 기호 제거 (image_1082c2 분수 보호)
    return re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)).strip()

# --- 4. 이메일 인증 로직 (복구) ---
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
    except: return False

def check_user_limit(email):
    if email == ADMIN_EMAIL: return True, "무제한"
    with DB_LOCK:
        user = db.table('users').get(User.email == email)
        if not user:
            db.table('users').insert({'email': email, 'count': 0})
            return True, 5
        remaining = 5 - user['count']
        return (remaining > 0), remaining

# --- 5. 수능 블루프린트 ---
def get_exam_blueprint(choice_sub, total_num, custom_score=None):
    blueprint = []
    if total_num == 30:
        for i in range(1, 23):
            if i in [1, 2]: score, diff, dom = 2, "쉬움", "기초 연산"
            elif i in [15, 21, 22]: score, diff, dom = 4, "킬러", "심화 추론"
            else: score, diff, dom = 4 if i > 8 else 3, "보통", "수학 I, II"
            blueprint.append({"num": i, "sub": "수학 I, II", "diff": diff, "score": score, "type": "객관식" if i <= 15 else "단답형", "domain": dom})
        for i in range(23, 31):
            if i in [23, 24]: score, diff, dom = 2, "쉬움", f"{choice_sub} 기초"
            elif i in [29, 30]: score, diff, dom = 4, "킬러", f"{choice_sub} 고난도"
            else: score, diff, dom = 3, "보통", f"{choice_sub} 응용"
            blueprint.append({"num": i, "sub": choice_sub, "diff": diff, "score": score, "type": "객관식" if i <= 28 else "단답형", "domain": dom})
    else:
        for i in range(1, total_num + 1):
            blueprint.append({"num": i, "sub": choice_sub, "diff": "보통", "score": custom_score or 3, "type": "객관식", "domain": f"{choice_sub} 전범위"})
    return blueprint

# --- 6. HTML 템플릿 (디자인 최적화) ---
def get_html_template(p_html, s_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']], displayMath: [['$$', '$$']] }} }};</script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
            * {{ font-family: 'Nanum Myeongjo', serif !important; }}
            body {{ background: #f0f2f6; margin: 0; color: #000; }}
            .paper-container {{ display: flex; flex-direction: column; align-items: center; padding: 20px 0; }}
            .paper {{ background: white; width: 210mm; padding: 15mm 18mm; margin-bottom: 30px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); position: relative; }}
            .header {{ text-align: center; border-bottom: 2.5px solid #000; margin-bottom: 35px; padding-bottom: 10px; }}
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 50px; min-height: 230mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #ddd; }}
            .question-box {{ position: relative; line-height: 2.1; font-size: 11pt; padding-left: 25px; margin-bottom: 45px; text-align: justify; }}
            /* 문항 네모 박스 제거 (image_108644 반영) */
            .q-num {{ position: absolute; left: 0; top: 0; font-weight: 800; font-size: 12pt; }}
            .options-container {{ margin-top: 25px; display: flex; justify-content: space-between; font-size: 10.5pt; }}
            .condition-box {{ border: 1.5px solid #000; padding: 12px; margin: 15px 0; background: #fafafa; font-weight: 700; }}
            .sol-item {{ margin-bottom: 35px; border-bottom: 1px dashed #eee; padding-bottom: 15px; }}
            mjx-container {{ font-size: 105% !important; }}
        </style>
    </head>
    <body><div class="paper-container">{p_html}<div class="paper"><h2 style="text-align:center;">[정답 및 해설]</h2>{s_html}</div></div></body>
    </html>
    """

# --- 7. 비동기 생성 엔진 ---
async def generate_batch_ai(q_info, size=5):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    batch_id = str(uuid.uuid4())
    prompt = f"""과목:{q_info['sub']} | 단원:{q_info['domain']} | 배점:{q_info['score']}
[규칙] 1. 수식 $ $ 필수. 분수는 $\\frac{{a}}{{b}}$. 2. 메타데이터(과목명 등) 문구 출력 금지.
오직 JSON 배열로 {size}개 생성: [{{ "question": "...", "options": ["..."], "solution": "..." }}]"""
    try:
        res = await model.generate_content_async(prompt, generation_config=genai.types.GenerationConfig(temperature=0.8, response_mime_type="application/json"))
        data = json.loads(res.text.strip())
        return [{**d, "batch_id": batch_id, "sub": q_info['sub'], "domain": q_info['domain'], "score": q_info['score'], "type": q_info['type']} for d in data]
    except: return []

async def get_safe_q(q_info, used_ids, used_batch_ids):
    with DB_LOCK:
        available = bank_db.search((QBank.sub == q_info['sub']) & (QBank.domain == q_info['domain']) & (QBank.score == q_info['score']))
    
    fresh = [q for q in available if str(q.doc_id) not in used_ids and q.get('batch_id') not in used_batch_ids]
    if fresh:
        sel = random.choice(fresh)
        used_ids.add(str(sel.doc_id)); used_batch_ids.add(sel.get('batch_id'))
        return {**sel, "num": q_info['num'], "source": "DB"}
    
    new_batch = await generate_batch_ai(q_info)
    if new_batch:
        return {**new_batch[0], "num": q_info['num'], "source": "AI", "full_batch": new_batch}
    return {"num": q_info['num'], "question": "지연 발생.. 재시도 해주세요.", "options": [], "solution": "오류", "source": "ERROR"}

async def run_orchestrator(choice_sub, num, score_val=None):
    blueprint = get_exam_blueprint(choice_sub, num, score_val)
    start_time = time.time()
    used_ids, used_batch_ids = set(), set()
    
    tasks = [get_safe_q(q, used_ids, used_batch_ids) for q in blueprint]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda x: x.get('num', 999))
    
    # AI로 생성된 문제들만 따로 모아서 안전하게 일괄 저장 (image_108e0a 에러 방지)
    to_save = []
    for r in results:
        if r.get('source') == "AI" and "full_batch" in r:
            to_save.extend(r['full_batch'])
    sync_save_to_db(to_save)
    
    p_html, s_html = "", ""
    for i in range(0, len(results), 2):
        pair = results[i:i+2]
        q_cont = ""
        for item in pair:
            q_text = polish_math(item.get("question", ""))
            opts = item.get("options", [])
            opt_html = ""
            if item.get('type') == '객관식' and opts:
                spans = "".join([f"<span>{chr(9312+j)} {clean_option(o)}</span>" for j, o in enumerate(opts[:5])])
                opt_html = f"<div class='options-container'>{spans}</div>"
            q_cont += f"<div class='question-box'><span class='q-num'>{item.get('num')}</span> {q_text} <b>[{item.get('score',3)}점]</b>{opt_html}</div>"
            s_html += f"<div class='sol-item'><b>{item.get('num')}번:</b> {polish_math(item.get('solution',''))}</div>"
        p_html += f"<div class='paper'><div class='header'><h1>2026 수능 모의평가</h1><h3>수학 영역 ({choice_sub})</h3></div><div class='question-grid'>{q_cont}</div></div>"
    
    return p_html, s_html, time.time()-start_time, sum(1 for r in results if r.get('source') == 'DB')

# --- 8. 백그라운드 DB 파밍 ---
def run_auto_farmer():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        try:
            if get_db_len() < 10000:
                sub = random.choice(["수학 I, II", "미적분", "확률과 통계", "기하"])
                q_info = {"sub": sub, "domain": f"{sub} 핵심 랜덤", "score": random.choice([2,3,4]), "type": "객관식"}
                batch = loop.run_until_complete(generate_batch_ai(q_info, size=10))
                sync_save_to_db(batch)
            time.sleep(60)
        except: time.sleep(60)

if 'farmer' not in st.session_state:
    threading.Thread(target=run_auto_farmer, daemon=True).start()
    st.session_state.farmer = True

# --- 9. UI 및 세션 관리 ---
st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")
if 'v' not in st.session_state: st.session_state.v = False
if 'auth_code' not in st.session_state: st.session_state.auth_code = None
if 'mail_sent' not in st.session_state: st.session_state.mail_sent = False

with st.sidebar:
    st.title("🎓 본부 인증")
    email_input = st.text_input("이메일", value=ADMIN_EMAIL if st.session_state.v else "")
    if email_input == ADMIN_EMAIL: st.session_state.v = True
    
    if not st.session_state.v:
        if st.button("인증번호 발송"):
            if email_input:
                code = str(random.randint(100000, 999999))
                if send_verification_email(email_input, code):
                    st.session_state.auth_code, st.session_state.mail_sent = code, True
                    st.success("발송 완료!")
        if st.session_state.mail_sent:
            c_input = st.text_input("6자리 입력")
            if st.button("확인"):
                if c_input == st.session_state.auth_code:
                    st.session_state.v = True
                    st.rerun()

    if st.session_state.v:
        st.divider()
        mode = st.radio("모드", ["맞춤 문항", "30문항 풀세트"])
        sub = st.selectbox("과목", ["미적분", "확률과 통계", "기하"])
        num = 30 if mode == "30문항 풀세트" else st.slider("문항 수", 2, 30, 4, step=2)
        score_v = int(st.selectbox("배점", ["2", "3", "4"])) if mode == "맞춤 문항" else None
        btn = st.button("🚀 발간 시작", use_container_width=True)
        st.caption(f"🗄️ DB 축적량: {get_db_len()} / 10000")

if st.session_state.v and 'btn' in locals() and btn:
    with st.spinner("DB 충돌 방어 엔진 가동 및 렌더링 중..."):
        p, s, elap, hits = asyncio.run(run_orchestrator(sub, num, score_v))
        st.success(f"✅ 완료! ({elap:.1f}초 | DB사용: {hits}개)")
        st.components.v1.html(get_html_template(p, s), height=1200, scrolling=True)
