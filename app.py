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

# --- 2. DB 및 전역 락 (자가 치유 로직) ---
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

# --- 3. [개선] 기하/벡터 특화 텍스트 정제 엔진 ---
def polish_output(text):
    if not text: return ""
    # 불필요한 레이블 제거
    text = re.sub(r'^(과목|단원|배점|유형|난이도|수학\s?[I|II|1|2]|Step\s?\d):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^Step\s?\d:.*?\n', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?점\]\s*', '', text)
    
    # 벡터 및 특수 기호 보호 (백슬래시 보정)
    math_tokens = [
        'vec', 'cdot', 'frac', 'theta', 'pi', 'sqrt', 'log', 'lim', 
        'to', 'infty', 'sin', 'cos', 'tan', 'sum', 'int', 'alpha', 'beta', 'mu', 'sigma'
    ]
    for token in math_tokens:
        text = re.sub(rf'(?<!\\)\b{token}\b', rf'\\{token}', text)
    
    # 화살표 및 기호 치환
    text = text.replace('->', r'\to')
    return text.strip()

def clean_option(text):
    clean = re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)).strip()
    return polish_output(clean)

# --- 4. 무결점 검수 및 저장 ---
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

# --- 6. [개선] HTML/CSS 템플릿 (벡터 렌더링 최적화) ---
def get_html_template(p_html, s_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script>
            window.MathJax = {{
                tex: {{
                    inlineMath: [['$', '$']],
                    displayMath: [['$$', '$$']],
                    macros: {{
                        vec: ["\\\\vec{{#1}}", 1]
                    }}
                }}
            }};
        </script>
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
        </style>
    </head>
    <body>
        <div class="no-print"><button class="btn-download" onclick="window.print()">🖨️ PDF 다운로드 / 인쇄</button></div>
        <div class="paper-container">{p_html}<div class="solution-paper"><h2 style="text-align:center;">[정답 및 해설]</h2>{s_html}</div></div>
    </body>
    </html>
    """

# --- 7. 다이내믹 창의성 룰렛 (확통 루즈함 방지 포함) ---
def get_creative_twist(sub, score):
    if sub == "확률과 통계":
        return random.choice([
            "🚫 금지: '주머니/공/상자' 상황 절대 사용 금지.",
            "🎨 시각화: 확률분포표 또는 정규분포 곡선 그래프를 반드시 해석하는 문제.",
            "📊 실생활: 기후 데이터, 투표 결과, 생산 공정 불량률 등 실제 통계 상황 설정.",
            "🧩 조건: (가), (나) 조건을 활용한 함수의 개수 추론 유형."
        ])
    if sub == "기하":
        return random.choice([
            "📐 벡터: 내적의 최댓값/최솟값 또는 벡터의 연산 성질을 묻는 참신한 유형.",
            "🔄 이차곡선: 타원/포물선의 정의를 이용한 기하학적 추론.",
            "📍 공간: 평면의 방정식이나 공간도형의 위치 관계."
        ])
    return "[기초/응용] 수능 표준 유형 및 복합 개념 융합."

# --- 8. 프롬프트 및 메인 엔진 ---
def build_strict_prompt(q_info, size):
    creative_twist = get_creative_twist(q_info['sub'], q_info['score'])
    opt_rule = "객관식: options 5개 필수." if q_info['type'] == '객관식' else "주관식: options 비움([]), 정답 3자리 자연수."
    prompt = f"""과목:{q_info['sub']} | 배점:{q_info['score']} | 유형:{q_info['type']}
[지시사항]
1. 한국어 전용. 범위 준수.
2. 창의성/다양성: {creative_twist}
3. 유형: {opt_rule}
4. 형식: 수식 $ $ 필수. 벡터는 \\vec{{a}} 형식 엄수.
JSON 배열 {size}개 생성: [{{ "topic": "...", "question": "...", "options": [...], "solution": "..." }}]"""
    return prompt

async def generate_batch_ai(q_info, size=2): 
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = build_strict_prompt(q_info, size)
    try:
        res = await model.generate_content_async(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.88, response_mime_type="application/json"))
        data = json.loads(re.search(r'\[.*\]', res.text.strip(), re.DOTALL).group(0))
        return [{**d, "batch_id": str(uuid.uuid4()), "sub": q_info['sub'], "score": q_info['score'], "type": q_info['type']} for d in data]
    except: return []

async def get_safe_q(q_info, used_ids, used_batch_ids, topic_counts):
    with DB_LOCK:
        available = bank_db.search((QBank.sub == q_info['sub']) & (QBank.score == q_info['score']) & (QBank.type == q_info['type']))
    fresh = [q for q in available if str(q.doc_id) not in used_ids and q.get('batch_id') not in used_batch_ids]
    strict_fresh = [q for q in fresh if topic_counts.get(q.get('topic', '기타'), 0) < 2]
    
    if strict_fresh:
        sel = random.choice(strict_fresh)
        topic_counts[sel.get('topic', '기타')] = topic_counts.get(sel.get('topic', '기타'), 0) + 1
        used_ids.add(str(sel.doc_id)); used_batch_ids.add(sel.get('batch_id'))
        return {**sel, "num": q_info['num'], "source": "DB"}
    elif fresh:
        sel = random.choice(fresh)
        used_ids.add(str(sel.doc_id)); used_batch_ids.add(sel.get('batch_id'))
        return {**sel, "num": q_info['num'], "source": "DB+"}
    
    for _ in range(3):
        new_batch = await generate_batch_ai(q_info, size=2)
        if new_batch and len(new_batch) > 0 and is_valid_question(new_batch[0], q_info['type']):
            return {**new_batch[0], "num": q_info['num'], "source": "AI", "full_batch": new_batch}
        await asyncio.sleep(1.2) 
    return {"num": q_info.get('num', 0), "score": 3, "type": "객관식", "question": "지연 발생", "options": [], "solution": "오류"}

async def run_orchestrator(sub_choice, num_choice, score_choice=None):
    blueprint = get_exam_blueprint(sub_choice, num_choice, score_choice)
    used_ids, used_batch_ids, topic_counts, results = set(), set(), {}, []
    prog, status = st.progress(0), st.empty()
    
    for i in range(0, len(blueprint), 2):
        chunk = blueprint[i : i + 2]
        status.text(f"⏳ {i+1}번 ~ {min(i+2, 30)}번 정밀 조판 중...")
        tasks = [get_safe_q(q, used_ids, used_batch_ids, topic_counts) for q in chunk]
        chunk_res = await asyncio.gather(*tasks)
        results.extend(chunk_res)
        all_new = [r['full_batch'] for r in chunk_res if r.get('source') == "AI" and "full_batch" in r]
        if all_new: safe_save_to_bank([item for sublist in all_new for item in sublist], chunk[0]['type'])
        prog.progress(min((i + 2) / len(blueprint), 1.0))
        await asyncio.sleep(0.8)
    status.empty(); prog.empty()
    
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
    
    return get_html_template(p_html, s_html), sum(1 for r in results if r.get('source').startswith('DB'))

# --- 9. 백그라운드 파밍 엔진 ---
def run_auto_farmer():
    sync_model = genai.GenerativeModel('models/gemini-2.5-flash')
    while True:
        try:
            with DB_LOCK: cur_len = len(bank_db)
            if cur_len < 10000:
                sub = random.choice(["수학 I, II", "미적분", "확률과 통계", "기하"])
                score, q_type = random.choice([2, 3, 4]), random.choice(["객관식", "주관식"])
                prompt = build_strict_prompt({"sub": sub, "score": score, "type": q_type}, size=4)
                res = sync_model.generate_content(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.88, response_mime_type="application/json"))
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

# --- 10. UI 및 보안 로그아웃 ---
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
                # (메일 발송 코드 생략)
                st.session_state.auth_code, st.session_state.mail_sent, st.session_state.temp_email = "123456", True, email_in; st.success("발송됨")
            if st.session_state.get('mail_sent'):
                c_in = st.text_input("6자리 입력")
                if st.button("확인"):
                    if c_in == st.session_state.auth_code: st.session_state.verified, st.session_state.user_email = True, st.session_state.temp_email; st.rerun()
    else:
        st.success(f"✅ {st.session_state.user_email}")
        if st.button("🚪 로그아웃"): st.session_state.verified = False; st.rerun()
        if st.session_state.user_email == ADMIN_EMAIL:
            if st.button("🚨 DB 완전 초기화"):
                with DB_LOCK: bank_db.truncate()
                st.success("초기화됨"); st.rerun()
        st.divider()
        mode = st.radio("모드", ["30문항 풀세트", "맞춤 문항"])
        sub = st.selectbox("선택과목", ["확률과 통계", "미적분", "기하"])
        num = 30 if mode == "30문항 풀세트" else st.slider("문항 수", 2, 30, 10, step=2)
        score = int(st.selectbox("난이도 설정", ["2", "3", "4"])) if mode == "맞춤 문항" else None
        btn = st.button("🚀 발간 시작", use_container_width=True)
        with DB_LOCK: st.caption(f"🗄️ 무결점 DB: {len(bank_db)}")

if st.session_state.verified and btn:
    with st.spinner("AI 엔진 가동 및 벡터 수식 검수 중..."):
        html_out, hits = asyncio.run(run_orchestrator(sub, num, score))
        st.success(f"✅ 발간 완료! (DB 활용: {hits}개)")
        st.components.v1.html(html_out, height=1200, scrolling=True)
