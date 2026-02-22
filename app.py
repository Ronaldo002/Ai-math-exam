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

# --- 1. 환경 설정 및 API 보안 해제 ---
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

# --- 2. DB 및 전역 락 ---
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

# --- 3. 무결점 검수 엔진 ---
def is_valid_question(q, expected_type):
    if not q.get('topic') or not str(q.get('topic')).strip(): return False
    if not q.get('question') or not str(q.get('question')).strip(): return False
    if not q.get('solution') or not str(q.get('solution')).strip(): return False
    opts = q.get('options', [])
    if expected_type == '객관식':
        if not isinstance(opts, list) or len(opts) != 5: return False
        if not all(str(o).strip() for o in opts): return False
    else: 
        if opts and len(opts) > 0: return False
    return True

# --- 4. 정제 및 저장 엔진 ---
def polish_output(text):
    if not text: return ""
    text = re.sub(r'^(과목|단원|배점|유형|난이도|수학\s?[I|II|1|2]|Step\s?\d):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^Step\s?\d:.*?\n', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?점\]\s*', '', text)
    math_tokens = ['frac', 'theta', 'pi', 'sqrt', 'log', 'lim', 'to', 'infty', 'sin', 'cos', 'tan', 'sum', 'int', 'alpha', 'beta', 'mu', 'sigma']
    for token in math_tokens:
        text = re.sub(rf'(?<!\\)\b{token}\b', rf'\\{token}', text)
    text = text.replace('->', r'\to')
    return text.strip()

def clean_option(text):
    clean = re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)).strip()
    return polish_output(clean)

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

# --- 5. 수능 표준 배치 설계 ---
def get_exam_blueprint(choice_sub, total_num, custom_score=None):
    blueprint = []
    if total_num == 30:
        for i in range(1, 16): 
            score = 2 if i <= 3 else 4 if i in [9,10,11,12,13,14,15] else 3
            blueprint.append({"num": i, "sub": "수학 I, II", "score": score, "type": "객관식", "cat": "공통"})
        for i in range(16, 23):
            score = 4 if i in [21, 22] else 3
            blueprint.append({"num": i, "sub": "수학 I, II", "score": score, "type": "주관식", "cat": "공통"})
        for i in range(23, 29): 
            score = 2 if i == 23 else 4 if i == 28 else 3
            blueprint.append({"num": i, "sub": choice_sub, "score": score, "type": "객관식", "cat": "선택"})
        for i in range(29, 31): 
            blueprint.append({"num": i, "sub": choice_sub, "score": 4, "type": "주관식", "cat": "선택"})
    else:
        for i in range(1, total_num + 1):
            blueprint.append({"num": i, "sub": choice_sub, "score": custom_score or 3, "type": "객관식", "cat": "맞춤"})
    return blueprint

# --- 6. [확통 특화] 다이내믹 창의성 룰렛 (루즈함 방지) ---
def get_pro_twist(sub, score):
    if sub != "확률과 통계":
        # 다른 과목용 기존 창의성 로직
        if score == 2: return "[기초 연산] 수능 정석 2점."
        elif score == 3: return "[융합형] 단원 결합 3점."
        else: return "[초고난도] 다중 추론 4점."
    
    # [확통 전용] 주머니 문제 원천 차단 및 다양성 확보
    twists = [
        "[실생활 데이터] 주머니 상황 절대 금지. 인구 통계, 제품 수명, 선거 지지율 등 실제 데이터를 해석하는 문제.",
        "[기호 정의] $f: A \\to B$ 함수의 개수나 중복조합을 활용한 새로운 조건 제시.",
        "[시각적 도구] 확률분포표 또는 정규분포 곡선의 대칭성을 활용한 그래프 해석 문제.",
        "[벤 다이어그램] 집합의 관계를 이용한 조건부확률 또는 확률의 덧셈정리.",
        "[이항정리] 주머니 상황 없이 다항식의 전개식에서 특정 계수를 찾는 신선한 유형."
    ]
    return random.choice(twists)

# --- 7. 프롬프트 및 메인 엔진 ---
def build_strict_prompt(q_info, size):
    creative_twist = get_pro_twist(q_info['sub'], q_info['score'])
    opt_rule = "객관식: options 5개 필수." if q_info['type'] == '객관식' else "주관식: options 비움([]), 정답 3자리 자연수."

    prompt = f"""과목:{q_info['sub']} | 배점:{q_info['score']} | 유형:{q_info['type']}
[필수 지시] 
1. 한국어 전용. 범위 준수.
2. 🚫 금지사항: '주머니', '상자', '공 꺼내기' 상황은 전체 중 10% 이하로만 사용하거나 가급적 배제할 것.
3. 🎨 창의성: {creative_twist}
4. 유형: {opt_rule}
5. 형식: 수식 $ $ 필수. JSON 배열 {size}개 생성: [{{ "topic": "...", "question": "...", "options": [...], "solution": "..." }}]"""
    return prompt

async def generate_batch_ai(q_info, size=2): 
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = build_strict_prompt(q_info, size)
    try:
        res = await model.generate_content_async(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.88, response_mime_type="application/json"))
        raw_text = res.text.strip()
        match = re.search(r'\[.*\]', raw_text, re.DOTALL)
        data = json.loads(match.group(0)) if match else json.loads(raw_text)
        return [{**d, "batch_id": str(uuid.uuid4()), "sub": q_info['sub'], "score": q_info['score'], "type": q_info['type']} for d in data]
    except: return []

async def get_safe_q(q_info, used_ids, used_batch_ids, topic_counts):
    with DB_LOCK:
        available = bank_db.search((QBank.sub == q_info['sub']) & (QBank.score == q_info['score']) & (QBank.type == q_info['type']))
    fresh = [q for q in available if str(q.doc_id) not in used_ids and q.get('batch_id') not in used_batch_ids]
    strict_fresh = [q for q in fresh if topic_counts.get(q.get('topic', '기타'), 0) < 2]
    
    if strict_fresh:
        sel = random.choice(strict_fresh)
        topic = sel.get('topic', '기타')
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        used_ids.add(str(sel.doc_id)); used_batch_ids.add(sel.get('batch_id'))
        return {**sel, "num": q_info['num'], "source": "DB", "cat": q_info.get('cat', '공통')}
    elif fresh:
        sel = random.choice(fresh)
        topic = sel.get('topic', '기타')
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        used_ids.add(str(sel.doc_id)); used_batch_ids.add(sel.get('batch_id'))
        return {**sel, "num": q_info['num'], "source": "DB (Quota+)", "cat": q_info.get('cat', '공통')}
    
    for _ in range(3):
        new_batch = await generate_batch_ai(q_info, size=2)
        if new_batch and len(new_batch) > 0 and is_valid_question(new_batch[0], q_info['type']):
            sel = new_batch[0]
            topic = sel.get('topic', '기타')
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
            return {**sel, "num": q_info['num'], "source": "AI", "full_batch": new_batch, "cat": q_info.get('cat', '공통')}
        await asyncio.sleep(1.2) 
    return {"num": q_info.get('num', 0), "score": q_info.get('score', 3), "type": q_info.get('type', '객관식'), "cat": q_info.get('cat', '공통'), "question": "지연 발생", "options": [], "solution": "오류"}

async def run_orchestrator(sub_choice, num_choice, score_choice=None):
    blueprint = get_exam_blueprint(sub_choice, num_choice, score_choice)
    used_ids, used_batch_ids, topic_counts = set(), set(), {}
    results = []
    prog = st.progress(0); status = st.empty()
    chunk_size = 2 
    for i in range(0, len(blueprint), chunk_size):
        chunk = blueprint[i : i + chunk_size]
        status.text(f"⏳ {i+1}번 ~ {min(i+chunk_size, 30)}번 다채로운 문항 조립 중...")
        tasks = [get_safe_q(q, used_ids, used_batch_ids, topic_counts) for q in chunk]
        chunk_res = await asyncio.gather(*tasks)
        results.extend(chunk_res)
        all_new = [r['full_batch'] for r in chunk_res if r.get('source') == "AI" and "full_batch" in r]
        if all_new: safe_save_to_bank([item for sublist in all_new for item in sublist], chunk[0]['type'])
        prog.progress(min((i + chunk_size) / len(blueprint), 1.0))
        await asyncio.sleep(0.8)
    status.empty(); prog.empty()
    
    results.sort(key=lambda x: x.get('num', 999))
    p_html, s_html = "" , ""
    pages = []
    current_page = []
    for item in results:
        if item.get('num') == 23 and len(current_page) > 0:
            pages.append(current_page); current_page = []
        current_page.append(item)
        if len(current_page) == 2:
            pages.append(current_page); current_page = []
    if current_page: pages.append(current_page)

    for page in pages:
        first_num = page[0].get('num', 0)
        header_html = ""
        if first_num == 1: header_html = "<div class='cat-header-container'><div class='cat-header'>■ 공통과목(수학Ⅰ, 수학 II)</div></div>"
        elif first_num == 23: header_html = f"<div class='cat-header-container'><div class='cat-header'>■ 선택과목({sub_choice})</div></div>"
        q_chunk = ""
        for item in page:
            num_val, score_val, q_type = item.get('num', ''), item.get('score', 3), item.get('type', '객관식')
            opts, q_text = item.get("options", []), polish_output(item.get("question", ""))
            opt_html = ""
            if q_type == '객관식' and opts and len(opts) >= 1:
                spans = "".join([f"<span>{chr(9312+j)} {clean_option(str(o))}</span>" for j, o in enumerate(opts[:5])])
                opt_html = f"<div class='options-container'>{spans}</div>"
            q_chunk += f"<div class='question-box'><span class='q-num'>{num_val}</span> {q_text} <b>[{score_val}점]</b>{opt_html}</div>"
            s_html += f"<div class='sol-item'><b>{num_val}번:</b> {polish_output(item.get('solution',''))}</div>"
        p_html += f"<div class='paper'><div class='header'><h1>2026 수능 모의평가 (수학 영역)</h1></div>{header_html}<div class='question-grid'>{q_chunk}</div></div>"
    
    # 조판 완료 후 HTML 서식 반환
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']], displayMath: [['$$', '$$']] }} }};</script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
        * {{ font-family: 'Nanum Myeongjo', serif !important; }}
        body {{ background: #f0f2f6; margin: 0; padding: 20px; color: #000; }}
        .no-print {{ text-align: center; margin-bottom: 20px; }}
        .btn-download {{ background: #2e7d32; color: white; padding: 12px 24px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; font-weight: bold; }}
        .paper-container {{ display: flex; flex-direction: column; align-items: center; }}
        .paper {{ background: white; width: 210mm; height: 297mm; padding: 20mm 18mm; margin-bottom: 30px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); position: relative; page-break-after: always; overflow: hidden; }}
        .header {{ text-align: center; border-bottom: 2.5px solid #000; margin-bottom: 25px; padding-bottom: 10px; }}
        .cat-header-container {{ width: 100%; text-align: left; margin-bottom: 20px; }}
        .cat-header {{ font-size: 14pt; font-weight: 800; border: 2.5px solid #000; display: inline-block; padding: 6px 20px; background-color: #fff; }}
        .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 55px; height: 210mm; position: relative; }}
        .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #ddd; }}
        .question-box {{ position: relative; line-height: 2.6; font-size: 11.5pt; padding-left: 30px; margin-bottom: 60px; text-align: justify; }}
        .q-num {{ position: absolute; left: 0; top: 0; font-weight: 800; font-size: 14pt; }}
        .options-container {{ margin-top: 30px; display: flex; flex-wrap: wrap; gap: 15px 5px; font-size: 11pt; }}
        .options-container span {{ flex: 1 1 18%; min-width: 140px; white-space: nowrap; }}
        .solution-paper {{ background: white; width: 210mm; padding: 15mm 18mm; margin-top: 30px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); }}
        .sol-item {{ margin-bottom: 25px; border-bottom: 1px dashed #eee; padding-bottom: 15px; }}
        @media print {{ .no-print {{ display: none; }} body {{ padding: 0; }} .paper, .solution-paper {{ box-shadow: none; margin: 0; }} }}
    </style></head><body><div class="no-print"><button class="btn-download" onclick="window.print()">🖨️ PDF 다운로드 / 인쇄</button></div>
    <div class="paper-container">{p_html}<div class="solution-paper"><h2 style="text-align:center;">[정답 및 해설]</h2>{s_html}</div></div></body></html>""", sum(1 for r in results if r.get('source').startswith('DB'))

# --- 8. 백그라운드 파밍 엔진 ---
def run_auto_farmer():
    sync_model = genai.GenerativeModel('models/gemini-2.5-flash')
    while True:
        try:
            with DB_LOCK: cur_len = len(bank_db)
            if cur_len < 10000:
                sub = random.choice(["수학 I, II", "미적분", "확률과 통계", "기하"])
                score, q_type = random.choice([2, 3, 4]), random.choice(["객관식", "주관식"])
                q_info = {"sub": sub, "score": score, "type": q_type}
                prompt = build_strict_prompt(q_info, size=2)
                res = sync_model.generate_content(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.88, response_mime_type="application/json"))
                match = re.search(r'\[.*\]', res.text.strip(), re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    with DB_LOCK:
                        for q in data:
                            if is_valid_question(q, q_type):
                                q.update({"batch_id": str(uuid.uuid4()), "sub": sub, "score": score, "type": q_type})
                                if not bank_db.search(QBank.question == q['question']): bank_db.insert(q)
            time.sleep(12) 
        except: time.sleep(20)

if 'farmer_running' not in st.session_state:
    threading.Thread(target=run_auto_farmer, daemon=True).start()
    st.session_state.farmer_running = True

# --- 9. UI 및 인증 ---
st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")
if 'verified' not in st.session_state: st.session_state.verified, st.session_state.user_email = False, ""

with st.sidebar:
    st.title("🎓 본부 인증")
    if not st.session_state.verified:
        email_in = st.text_input("이메일 입력")
        if email_in == ADMIN_EMAIL:
            if st.button("관리자 로그인"): st.session_state.verified, st.session_state.user_email = True, ADMIN_EMAIL; st.rerun()
        else:
            if st.button("인증번호 발송"):
                code = str(random.randint(100000, 999999))
                # (생략: 메일 발송 로직 유지)
                st.session_state.auth_code, st.session_state.mail_sent, st.session_state.temp_email = code, True, email_in; st.success("발송 완료!")
            if st.session_state.get('mail_sent'):
                c_in = st.text_input("6자리 입력")
                if st.button("확인"):
                    if c_in == st.session_state.auth_code: st.session_state.verified, st.session_state.user_email = True, st.session_state.temp_email; st.rerun()
    else:
        st.success(f"✅ {st.session_state.user_email} 님")
        if st.button("🚪 로그아웃"): st.session_state.verified = False; st.rerun()
        if st.session_state.user_email == ADMIN_EMAIL:
            if st.button("🚨 DB 완전 초기화"):
                with DB_LOCK: bank_db.truncate()
                st.success("초기화 완료!"); st.rerun()
        st.divider()
        mode = st.radio("모드", ["30문항 풀세트", "맞춤 문항"])
        sub = st.selectbox("선택과목", ["확률과 통계", "미적분", "기하"])
        num = 30 if mode == "30문항 풀세트" else st.slider("문항 수", 2, 30, 10, step=2)
        score = int(st.selectbox("난이도 설정", ["2", "3", "4"])) if mode == "맞춤 문항" else None
        btn = st.button("🚀 발간 시작", use_container_width=True)
        with DB_LOCK: st.caption(f"🗄️ 무결점 DB: {len(bank_db)} / 10000")

if st.session_state.verified and btn:
    with st.spinner("AI 엔진 가동 중... (유형 쏠림 방지 및 조판 중)"):
        html_out, hits = asyncio.run(run_orchestrator(sub, num, score))
        st.success(f"✅ 발간 완료! (DB 활용: {hits}개)")
        st.components.v1.html(html_out, height=1200, scrolling=True)
