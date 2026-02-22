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
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 1. 환경 설정 및 API 보안 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("PAID_API_KEY 설정이 필요합니다!")
    st.stop()

SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
]

ADMIN_EMAIL = "pgh001002@gmail.com"
SENDER_EMAIL = st.secrets.get("EMAIL_USER", "pgh001002@gmail.com")
SENDER_PASS = st.secrets.get("EMAIL_PASS", "gmjg cvsg pdjq hnpw")

# --- 2. DB 및 전역 락 (자가 치유) ---
@st.cache_resource
def get_databases():
    try:
        u_db = TinyDB('user_registry.json')
        q_db = TinyDB('question_bank.json')
        _ = len(q_db) 
        return u_db, q_db
    except Exception:
        if os.path.exists('question_bank.json'): os.remove('question_bank.json')
        if os.path.exists('user_registry.json'): os.remove('user_registry.json')
        return TinyDB('user_registry.json'), TinyDB('question_bank.json')

db, bank_db = get_databases()
User, QBank = Query(), Query()

@st.cache_resource
def get_global_lock():
    return threading.Lock()

DB_LOCK = get_global_lock()

# --- 3. 텍스트 정제 엔진 ---
def polish_output(text):
    if not text: return ""
    text = re.sub(r'^(과목|단원|배점|유형|난이도|수학\s?[I|II|1|2]|Step\s?\d):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^Step\s?\d:.*?\n', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?점\]\s*', '', text)
    math_tokens = ['vec', 'cdot', 'frac', 'theta', 'pi', 'sqrt', 'log', 'lim', 'to', 'infty', 'sin', 'cos', 'tan', 'sum', 'int', 'alpha', 'beta', 'mu', 'sigma']
    for token in math_tokens:
        text = re.sub(rf'(?<!\\)\b{token}\b', rf'\\{token}', text)
    text = text.replace('->', r'\to')
    return text.strip()

def clean_option(text):
    clean = re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)).strip()
    return polish_output(clean)

# --- 4. 무결점 검수 ---
def is_valid_question(q, expected_type):
    if not q.get('topic') or not str(q.get('topic')).strip(): return False
    if not q.get('question') or not str(q.get('question')).strip(): return False
    if not q.get('solution') or not str(q.get('solution')).strip(): return False
    opts = q.get('options', [])
    if expected_type == '객관식':
        if not isinstance(opts, list) or len(opts) != 5: return False
    else: 
        if opts and len(opts) > 0: return False
    return True

def safe_save_to_bank(batch, expected_type):
    def _bg_save():
        with DB_LOCK:
            for q in batch:
                if is_valid_question(q, expected_type):
                    try:
                        if not bank_db.search(QBank.question == q.get("question", "")):
                            bank_db.insert(q)
                    except: continue
    threading.Thread(target=_bg_save, daemon=True).start()

# --- 5. 2026 수능 비율형 블루프린트 설계 ---
def get_exam_blueprint(choice_sub, total_num, custom_score=None):
    blueprint = []
    m1_topics = ["지수함수와 로그함수", "삼각함수", "수열"]
    m2_topics = ["함수의 극한과 연속", "다항함수의 미분법", "다항함수의 적분법"]
    choice_map = {
        "미적분": ["수열의 극한", "미분법", "적분법"],
        "확률과 통계": ["경우의 수", "확률", "통계"],
        "기하": ["이차곡선", "평면벡터", "공간도형과 공간좌표"]
    }
    
    if total_num == 30:
        for i in range(1, 16):
            sub = "수학 I" if i % 2 != 0 else "수학 II"
            topic = m1_topics[(i//2) % 3] if sub == "수학 I" else m2_topics[(i//2) % 3]
            score = 2 if i <= 3 else 4 if i in [9,10,11,12,13,14,15] else 3
            blueprint.append({"num": i, "sub": sub, "topic": topic, "score": score, "type": "객관식"})
        for i in range(16, 23):
            sub = "수학 II" if i % 2 == 0 else "수학 I"
            topic = m2_topics[i % 3] if sub == "수학 II" else m1_topics[i % 3]
            score = 4 if i in [21, 22] else 3
            blueprint.append({"num": i, "sub": sub, "topic": topic, "score": score, "type": "주관식"})
        for i in range(23, 31):
            topics = choice_map[choice_sub]
            topic = topics[(i-23) % 3]
            score = 2 if i == 23 else 4 if i in [28, 29, 30] else 3
            q_type = "객관식" if i <= 28 else "주관식"
            blueprint.append({"num": i, "sub": choice_sub, "topic": topic, "score": score, "type": q_type})
    else:
        topics = choice_map.get(choice_sub, ["수학 I", "수학 II"])
        for i in range(1, total_num + 1):
            topic = topics[(i-1) % len(topics)]
            blueprint.append({"num": i, "sub": choice_sub, "topic": topic, "score": custom_score or 3, "type": "객관식"})
    return blueprint

# --- 6. HTML 템플릿 ---
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
            body {{ background: #f0f2f6; margin: 0; padding: 20px; color: #000; }}
            .paper-container {{ display: flex; flex-direction: column; align-items: center; }}
            .paper {{ background: white; width: 210mm; height: 297mm; padding: 20mm 18mm; margin-bottom: 30px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); position: relative; page-break-after: always; overflow: hidden; }}
            .header {{ text-align: center; border-bottom: 2.5px solid #000; margin-bottom: 25px; padding-bottom: 10px; }}
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 55px; height: 210mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #ddd; }}
            .question-box {{ position: relative; line-height: 2.6; font-size: 11.5pt; padding-left: 30px; margin-bottom: 60px; text-align: justify; }}
            .q-num {{ position: absolute; left: 0; top: 0; font-weight: 800; font-size: 14pt; }}
            .options-container {{ margin-top: 30px; display: flex; flex-wrap: wrap; gap: 15px 5px; font-size: 11pt; }}
            .options-container span {{ flex: 1 1 18%; min-width: 140px; white-space: nowrap; }}
            .solution-paper {{ background: white; width: 210mm; padding: 15mm 18mm; margin-top: 30px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); }}
            @media print {{ .no-print {{ display: none; }} body {{ padding: 0; }} .paper, .solution-paper {{ box-shadow: none; margin: 0; }} }}
        </style>
    </head>
    <body>
        <div class="no-print" style="text-align:center; margin-bottom:20px;">
            <button style="background:#2e7d32; color:white; padding:12px 24px; border:none; border-radius:5px; cursor:pointer; font-weight:bold;" onclick="window.print()">🖨️ PDF 다운로드 / 인쇄</button>
        </div>
        <div class="paper-container">{p_html}<div class="solution-paper"><h2 style="text-align:center;">[정답 및 해설]</h2>{s_html}</div></div>
    </body>
    </html>
    """

# --- 7. 창의성 룰렛 ---
def get_universal_twist(sub, score):
    if sub == "확률과 통계": return random.choice(["🚫 주머니 금지", "📊 실생활 통계", "🧩 조건 추론"])
    elif sub == "미적분": return random.choice(["📈 초월함수 그래프 추론", "📐 급수 기하 활용", "🔄 치환/부분적분 응용"])
    elif sub == "수학 I" or sub == "수학 II": return random.choice(["🔢 수열 귀납적 추론", "🔍 함수의 연속성 심화"])
    elif sub == "기하": return random.choice(["📐 벡터 내적 기하 의미", "🔄 이차곡선 정의 활용"])
    return "[기초/응용] 표준 유형 융합."

# --- 8. 생성 엔진 ---
def build_strict_prompt(q_info, size):
    creative_twist = get_universal_twist(q_info['sub'], q_info['score'])
    prompt = f"""과목:{q_info['sub']} | 단원:{q_info['topic']} | 배점:{q_info['score']} | 유형:{q_info['type']}
[지시] 1.한국어 2.다양성: {creative_twist} 3.JSON {size}개 생성: [{{ "topic": "{q_info['topic']}", "question": "...", "options": [...], "solution": "..." }}]"""
    return prompt

async def generate_batch_ai(q_info, size=2): 
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    try:
        res = await model.generate_content_async(build_strict_prompt(q_info, size), safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.88, response_mime_type="application/json"))
        data = json.loads(re.search(r'\[.*\]', res.text.strip(), re.DOTALL).group(0))
        return [{**d, "batch_id": str(uuid.uuid4()), "sub": q_info['sub'], "score": q_info['score'], "type": q_info['type']} for d in data]
    except: return []

async def get_safe_q(q_info, used_ids, used_batch_ids, topic_counts, total_num):
    with DB_LOCK:
        available = bank_db.search((QBank.sub == q_info['sub']) & (QBank.topic == q_info['topic']) & (QBank.score == q_info['score']) & (QBank.type == q_info['type']))
    
    quota_limit = max(2, (total_num // 3) + 1)
    fresh = [q for q in available if str(q.doc_id) not in used_ids and q.get('batch_id') not in used_batch_ids]
    strict_fresh = [q for q in fresh if topic_counts.get(q.get('topic', '기타'), 0) < quota_limit]
    
    if strict_fresh:
        sel = random.choice(strict_fresh)
        topic_counts[sel.get('topic', '기타')] = topic_counts.get(sel.get('topic', '기타'), 0) + 1
        used_ids.add(str(sel.doc_id)); used_batch_ids.add(sel.get('batch_id'))
        return {**sel, "num": q_info['num'], "source": "DB"}
    
    new_batch = await generate_batch_ai(q_info, size=2)
    if new_batch:
        sel = new_batch[0]
        topic_counts[sel.get('topic', '기타')] = topic_counts.get(sel.get('topic', '기타'), 0) + 1
        return {**sel, "num": q_info['num'], "source": "AI", "full_batch": new_batch}
        
    # [수정 포인트] 에러 발생 시에도 source 키를 반드시 포함하여 반환
    return {"num": q_info.get('num', 0), "score": 3, "type": "객관식", "question": "지연 발생", "options": [], "solution": "오류", "source": "ERROR"}

async def run_orchestrator(sub_choice, num_choice, score_choice=None):
    blueprint = get_exam_blueprint(sub_choice, num_choice, score_choice)
    used_ids, used_batch_ids, topic_counts, results = set(), set(), {}, []
    prog, status = st.progress(0), st.empty()
    
    for i in range(0, len(blueprint), 2):
        chunk = blueprint[i : i + 2]
        status.text(f"⏳ {i+1}번 ~ {min(i+2, num_choice)}번 유형별 황금 비율 조판 중...")
        tasks = [get_safe_q(q, used_ids, used_batch_ids, topic_counts, num_choice) for q in chunk]
        chunk_res = await asyncio.gather(*tasks)
        results.extend(chunk_res)
        all_new = [r['full_batch'] for r in chunk_res if r.get('source') == "AI" and "full_batch" in r]
        if all_new: safe_save_to_bank([item for sublist in all_new for item in sublist], chunk[0]['type'])
        prog.progress(min((i + 2) / len(blueprint), 1.0))
        await asyncio.sleep(0.8)
    
    results.sort(key=lambda x: x.get('num', 999))
    p_html, s_html = "" , ""
    pages, current_page = [], []
    for item in results:
        if item.get('num') == 23 and current_page: pages.append(current_page); current_page = []
        current_page.append(item)
        if len(current_page) == 2: pages.append(current_page); current_page = []
    if current_page: pages.append(current_page)

    for page in pages:
        first_num = page[0].get('num', 0)
        header_html = ""
        if first_num == 1: header_html = "<div class='cat-header-container'><div class='cat-header'>■ 공통과목 (수학 I, II)</div></div>"
        elif first_num == 23: header_html = f"<div class='cat-header-container'><div class='cat-header'>■ 선택과목 ({sub_choice})</div></div>"
        q_chunk = ""
        for item in page:
            num, score, q_type = item.get('num', ''), item.get('score', 3), item.get('type', '객관식')
            opts, q_text = item.get("options", []), polish_output(item.get("question", ""))
            opt_html = ""
            if q_type == '객관식' and opts:
                spans = "".join([f"<span>{chr(9312+j)} {clean_option(str(o))}</span>" for j, o in enumerate(opts[:5])])
                opt_html = f"<div class='options-container'>{spans}</div>"
            q_chunk += f"<div class='question-box'><span class='q-num'>{num}</span> {q_text} <b>[{score}점]</b>{opt_html}</div>"
            s_html += f"<div class='sol-item'><b>{num}번:</b> {polish_output(item.get('solution',''))}</div>"
        p_html += f"<div class='paper'><div class='header'><h1>2026 수능 모의평가</h1></div>{header_html}<div class='question-grid'>{q_chunk}</div></div>"
    
    # [수정 포인트] r.get('source')가 None일 경우를 대비하여 안전하게 카운트
    db_hits = sum(1 for r in results if r.get('source') and r.get('source').startswith('DB'))
    return get_html_template(p_html, s_html), db_hits

# --- 9. 파밍 엔진 ---
def run_auto_farmer():
    sync_model = genai.GenerativeModel('models/gemini-2.5-flash')
    while True:
        try:
            with DB_LOCK: cur_len = len(bank_db)
            if cur_len < 10000:
                sub = random.choice(["수학 I", "수학 II", "미적분", "확률과 통계", "기하"])
                topics = {"수학 I": ["지수함수와 로그함수", "삼각함수", "수열"], "수학 II": ["함수의 극한과 연속", "다항함수의 미분법", "다항함수의 적분법"], "미적분": ["수열의 극한", "미분법", "적분법"], "확률과 통계": ["경우의 수", "확률", "통계"], "기하": ["이차곡선", "평면벡터", "공간도형과 공간좌표"]}[sub]
                score, q_type, topic = random.choice([2, 3, 4]), random.choice(["객관식", "주관식"]), random.choice(topics)
                res = sync_model.generate_content(build_strict_prompt({"sub": sub, "topic": topic, "score": score, "type": q_type}, size=4), safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.88, response_mime_type="application/json"))
                data = json.loads(re.search(r'\[.*\]', res.text.strip(), re.DOTALL).group(0))
                with DB_LOCK:
                    for q in data:
                        if is_valid_question(q, q_type):
                            q.update({"batch_id": str(uuid.uuid4()), "sub": sub, "score": score, "type": q_type})
                            if not bank_db.search(QBank.question == q['question']): bank_db.insert(q)
            time.sleep(15) 
        except: time.sleep(20)

if 'farmer_running' not in st.session_state:
    threading.Thread(target=run_auto_farmer, daemon=True).start()
    st.session_state.farmer_running = True

# --- 10. UI ---
st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")
if 'verified' not in st.session_state: st.session_state.verified, st.session_state.user_email = False, ""

with st.sidebar:
    st.title("🎓 본부 인증")
    if not st.session_state.verified:
        email_in = st.text_input("이메일 입력")
        if email_in == ADMIN_EMAIL:
            if st.button("관리자 로그인"): st.session_state.verified, st.session_state.user_email = True, ADMIN_EMAIL; st.rerun()
    else:
        st.success(f"✅ {st.session_state.user_email}")
        if st.button("🚪 로그아웃"): st.session_state.verified = False; st.rerun()
        if st.session_state.user_email == ADMIN_EMAIL and st.button("🚨 전체 DB 초기화"):
             with DB_LOCK: bank_db.truncate(); st.rerun()
        st.divider()
        mode = st.radio("모드", ["30문항 풀세트", "맞춤 문항"])
        sub = st.selectbox("선택과목", ["확률과 통계", "미적분", "기하"])
        num = 30 if mode == "30문항 풀세트" else st.slider("문항 수", 2, 30, 10, step=2)
        score_val = int(st.selectbox("난이도 설정 (배점)", ["2", "3", "4"])) if mode == "맞춤 문항" else None
        btn = st.button("🚀 발간 시작", use_container_width=True)
        with DB_LOCK: st.caption(f"🗄️ 무결점 DB: {len(bank_db)}")

if st.session_state.verified and btn:
    with st.spinner("비율 최적화 조판 중..."):
        try:
            html_out, hits = asyncio.run(run_orchestrator(sub, num, score_val))
            st.success(f"✅ 발간 완료! (DB 활용: {hits}개)")
            st.components.v1.html(html_out, height=1200, scrolling=True)
        except Exception as e:
            st.error(f"❌ 발간 중 오류가 발생했습니다: {e}")
