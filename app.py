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

# --- 1. 환경 설정 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("PAID_API_KEY 설정이 필요합니다!")
    st.stop()

SAFETY_SETTINGS = [{"category": f"HARM_CATEGORY_{c}", "threshold": "BLOCK_NONE"} for c in ["HARASSMENT", "HATE_SPEECH", "SEXUALLY_EXPLICIT", "DANGEROUS_CONTENT"]]
ADMIN_EMAIL = "pgh001002@gmail.com"
SENDER_EMAIL = st.secrets.get("EMAIL_USER", "pgh001002@gmail.com")
SENDER_PASS = st.secrets.get("EMAIL_PASS", "gmjg cvsg pdjq hnpw")

# --- 2. DB 로직 (자가 치유) ---
@st.cache_resource
def get_databases():
    try:
        q_db = TinyDB('question_bank.json')
        _ = len(q_db) 
        return TinyDB('user_registry.json'), q_db
    except:
        for f in ['question_bank.json', 'user_registry.json']:
            if os.path.exists(f): os.remove(f)
        return TinyDB('user_registry.json'), TinyDB('question_bank.json')

db, bank_db = get_databases()
User, QBank = Query(), Query()
DB_LOCK = threading.Lock()

# --- 3. 텍스트 및 수식 정제 (보강) ---
def polish_output(text):
    if not text: return ""
    # 불필요한 태그 및 레이블 소거
    text = re.sub(r'^(과목|단원|배점|유형|난이도|수학\s?[I|II|1|2]|Step\s?\d):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'\[.*?점\]\s*', '', text)
    
    # LaTeX 주요 토큰 강제 보정 (깨짐 방지)
    math_tokens = ['sin', 'cos', 'tan', 'log', 'ln', 'lim', 'exp', 'sqrt', 'vec', 'cdot', 'frac', 'theta', 'pi', 'infty', 'to', 'sum', 'int', 'alpha', 'beta', 'mu', 'sigma', 'lambda']
    for token in math_tokens:
        text = re.sub(rf'(?<!\\)\b{token}\b', rf'\\{token}', text)
    
    return text.replace('->', r'\to').strip()

def clean_option(text):
    return polish_output(re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)))

# --- 4. 무결점 검수 ---
def is_valid_question(q, expected_type):
    if not q.get('topic') or not q.get('question') or not q.get('solution'): return False
    opts = q.get('options', [])
    if expected_type == '객관식' and (not isinstance(opts, list) or len(opts) != 5): return False
    return True

def safe_save_to_bank(batch, expected_type):
    def _bg_save():
        with DB_LOCK:
            for q in batch:
                if is_valid_question(q, expected_type) and not bank_db.search(QBank.question == q.get("question", "")):
                    bank_db.insert(q)
    threading.Thread(target=_bg_save, daemon=True).start()

# --- 5. 수능 표준 블루프린트 (2026 규격) ---
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
            topic = m1_topics[(i//2)%3] if sub == "수학 I" else m2_topics[(i//2)%3]
            score = 2 if i <= 3 else 4 if i in [9,10,11,12,13,14,15] else 3
            blueprint.append({"num": i, "sub": sub, "topic": topic, "score": score, "type": "객관식"})
        for i in range(16, 23):
            sub = "수학 II" if i % 2 == 0 else "수학 I"
            topic = m2_topics[i%3] if sub == "수학 II" else m1_topics[i%3]
            score = 4 if i in [21, 22] else 3
            blueprint.append({"num": i, "sub": sub, "topic": topic, "score": score, "type": "주관식"})
        for i in range(23, 31):
            topic = choice_map[choice_sub][(i-23)%3]
            score = 2 if i == 23 else 4 if i in [28, 29, 30] else 3
            blueprint.append({"num": i, "sub": choice_sub, "topic": topic, "score": score, "type": "객관식" if i <= 28 else "주관식"})
    else:
        topics = choice_map.get(choice_sub, ["공통 개념"])
        for i in range(1, total_num + 1):
            blueprint.append({"num": i, "sub": choice_sub, "topic": topics[(i-1)%len(topics)], "score": custom_score or 3, "type": "객관식"})
    return blueprint

# --- 6. HTML/CSS (그림 박스 및 정렬 강화) ---
def get_html_template(p_html, s_html):
    return f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']], displayMath: [['$$', '$$']] }} }};</script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
        * {{ font-family: 'Nanum Myeongjo', serif !important; }}
        body {{ background: #f0f2f6; padding: 20px; color: #000; }}
        .paper {{ background: white; width: 210mm; min-height: 297mm; padding: 20mm 18mm; margin: 0 auto 30px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); position: relative; }}
        .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 50px; position: relative; }}
        .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: #eee; }}
        .question-box {{ position: relative; line-height: 2.4; font-size: 11.5pt; padding-left: 28px; margin-bottom: 45px; text-align: justify; }}
        .q-num {{ position: absolute; left: 0; top: 0; font-weight: 800; font-size: 14pt; }}
        .diagram-box {{ border: 1px solid #999; margin: 15px 0; padding: 10px; text-align: center; font-size: 10pt; background: #fafafa; border-radius: 4px; }}
        .options-container {{ margin-top: 20px; display: flex; flex-wrap: wrap; gap: 10px 5px; }}
        .options-container span {{ flex: 0 0 18%; min-width: 140px; white-space: nowrap; }}
        @media print {{ .no-print {{ display: none; }} body {{ padding: 0; }} .paper {{ box-shadow: none; margin: 0; }} }}
    </style></head>
    <body>
        <div class="no-print" style="text-align:center; margin-bottom:20px;"><button style="background:#2e7d32; color:white; padding:12px 24px; border:none; border-radius:5px; cursor:pointer; font-weight:bold;" onclick="window.print()">🖨️ PDF 다운로드 / 인쇄</button></div>
        <div class="paper-container">{p_html}<div class="paper"><h2 style="text-align:center;">[정답 및 해설]</h2>{s_html}</div></div>
    </body></html>
    """

# --- 7. 다이내믹 창의성 & 난이도 룰렛 (4점 강화) ---
def get_dynamic_twist(sub, score):
    if score == 4:
        return random.choice([
            "🔥 [초고난도] (가), (나) 형태의 복합 조건을 제시하고, 두 가지 이상의 개념을 융합하여 고도의 추론이 필요한 문항.",
            "🔥 [준킬러] 겉보기엔 단순하나 케이스 분류(Case Work)를 3가지 이상 해야만 풀리는 함정형 문항.",
            "🔥 [신유형] 기존 기출에서 보지 못한 새로운 기호나 함수 정의를 포함한 문항."
        ])
    if sub == "기하" or sub == "미적분":
        return "📐 [도형/그림 필수] 문제 상황을 설명하는 그림이나 그래프 묘사가 포함된 문항 (diagram 필드 활용)."
    return "[수능 표준] 개념의 본질을 묻는 깔끔한 응용 문항."

# --- 8. 생성 엔진 ---
def build_strict_prompt(q_info, size):
    twist = get_dynamic_twist(q_info['sub'], q_info['score'])
    opt_rule = "객관식: 5개 선지 필수." if q_info['type'] == '객관식' else "주관식: options 비움, 정답 자연수."
    
    prompt = f"""과목:{q_info['sub']} | 단원:{q_info['topic']} | 배점:{q_info['score']} | 유형:{q_info['type']}
[지시] 1.한국어 2.난이도:{twist} 3.형식:수식 $ $ 필수 4.그림필요시 diagram 필드에 묘사 5.JSON {size}개 생성:
[{{ "topic": "{q_info['topic']}", "question": "...", "diagram": "그림에 대한 상세 묘사(없으면 null)", "options": [...], "solution": "..." }}]"""
    return prompt

async def generate_batch_ai(q_info, size=2):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    try:
        res = await model.generate_content_async(build_strict_prompt(q_info, size), safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.9, response_mime_type="application/json"))
        data = json.loads(re.search(r'\[.*\]', res.text.strip(), re.DOTALL).group(0))
        return [{**d, "batch_id": str(uuid.uuid4()), "sub": q_info['sub'], "score": q_info['score'], "type": q_info['type']} for d in data]
    except: return []

async def get_safe_q(q_info, used_ids, used_batch_ids, topic_counts, total_num):
    with DB_LOCK:
        available = bank_db.search((QBank.sub == q_info['sub']) & (QBank.topic == q_info['topic']) & (QBank.score == q_info['score']) & (QBank.type == q_info['type']))
    
    fresh = [q for q in available if str(q.doc_id) not in used_ids and q.get('batch_id') not in used_batch_ids]
    quota = max(2, (total_num // 4) + 1)
    strict = [q for q in fresh if topic_counts.get(q.get('topic'), 0) < quota]
    
    if strict:
        sel = random.choice(strict)
        topic_counts[sel.get('topic')] = topic_counts.get(sel.get('topic'), 0) + 1
        used_ids.add(str(sel.doc_id)); used_batch_ids.add(sel.get('batch_id'))
        return {**sel, "num": q_info['num'], "source": "DB"}
    
    for _ in range(2): # 재시도 보강
        new_batch = await generate_batch_ai(q_info, size=2)
        if new_batch:
            sel = new_batch[0]
            topic_counts[sel.get('topic')] = topic_counts.get(sel.get('topic'), 0) + 1
            return {**sel, "num": q_info['num'], "source": "AI", "full_batch": new_batch}
    return {"num": q_info['num'], "score": q_info['score'], "type": q_info['type'], "question": "생성 지연 (재시도 필요)", "options": ["-"]*5, "solution": "N/A", "source": "ERROR", "topic": "N/A"}

async def run_orchestrator(sub_choice, num_choice, score_choice=None):
    blueprint = get_exam_blueprint(sub_choice, num_choice, score_choice)
    used_ids, used_batch_ids, topic_counts, results = set(), set(), {}, []
    prog, status = st.progress(0), st.empty()
    
    for i in range(0, len(blueprint), 2):
        chunk = blueprint[i : i + 2]
        status.text(f"⏳ {i+1}번 ~ {min(i+2, num_choice)}번 프리미엄 조판 중...")
        tasks = [get_safe_q(q, used_ids, used_batch_ids, topic_counts, num_choice) for q in chunk]
        chunk_res = await asyncio.gather(*tasks)
        results.extend(chunk_res)
        all_new = [r['full_batch'] for r in chunk_res if r.get('source') == "AI" and "full_batch" in r]
        if all_new: safe_save_to_bank([item for sublist in all_new for item in sublist], chunk[0]['type'])
        prog.progress(min((i+2)/len(blueprint), 1.0))
        await asyncio.sleep(0.6)
    
    results.sort(key=lambda x: x.get('num', 999))
    p_html, s_html = "", ""
    pages, current_page = [], []
    for item in results:
        if item.get('num') == 23 and current_page: pages.append(current_page); current_page = []
        current_page.append(item)
        if len(current_page) == 2: pages.append(current_page); current_page = []
    if current_page: pages.append(current_page)

    for page in pages:
        first_num = page[0].get('num', 0)
        header = f"<div class='cat-header-container'><div class='cat-header'>■ {'공통과목' if first_num < 23 else '선택과목 ('+sub_choice+')'}</div></div>"
        q_chunk = ""
        for item in page:
            num, score, q_type = item.get('num', ''), item.get('score', 3), item.get('type', '객관식')
            opts, q_text = item.get("options", []), polish_output(item.get("question", ""))
            
            # [그림 박스 추가 로직]
            diag_html = f"<div class='diagram-box'>[그림] {item.get('diagram')}</div>" if item.get('diagram') else ""
            
            opt_html = f"<div class='options-container'>{''.join([f'<span>{chr(9312+j)} {clean_option(str(o))}</span>' for j, o in enumerate(opts[:5])])}</div>" if q_type == '객관식' else ""
            q_chunk += f"<div class='question-box'><span class='q-num'>{num}</span> {q_text} <b>[{score}점]</b>{diag_html}{opt_html}</div>"
            s_html += f"<div style='margin-bottom:15px;'><b>{num}번:</b> {polish_output(item.get('solution',''))}</div>"
        p_html += f"<div class='paper'><div class='header'><h1>2026 수능 모의평가</h1></div>{header}<div class='question-grid'>{q_chunk}</div></div>"
    
    db_hits = sum(1 for r in results if r.get('source') and r.get('source').startswith('DB'))
    return get_html_template(p_html, s_html), db_hits

# --- 9. UI ---
st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")
if 'verified' not in st.session_state: st.session_state.verified, st.session_state.user_email = False, ""

with st.sidebar:
    st.title("🎓 본부 인증")
    if not st.session_state.verified:
        email_in = st.text_input("이메일 입력")
        if email_in == ADMIN_EMAIL and st.button("관리자 로그인"): 
            st.session_state.verified, st.session_state.user_email = True, ADMIN_EMAIL; st.rerun()
    else:
        st.success(f"✅ {st.session_state.user_email}")
        if st.button("🚪 로그아웃"): st.session_state.verified = False; st.rerun()
        if st.session_state.user_email == ADMIN_EMAIL and st.button("🚨 전체 DB 초기화"):
             with DB_LOCK: bank_db.truncate(); st.rerun()
        st.divider()
        mode = st.radio("모드", ["30문항 풀세트", "맞춤 문항"])
        sub = st.selectbox("과목", ["미적분", "확률과 통계", "기하"])
        num = 30 if mode == "30문항 풀세트" else st.slider("문항 수", 2, 30, 10, step=2)
        
        # [복구] 난이도 설정 슬롯 (맞춤 문항 모드 전용)
        score_val = int(st.selectbox("난이도 (배점)", ["2", "3", "4"])) if mode == "맞춤 문항" else None
        
        btn = st.button("🚀 발간 시작", use_container_width=True)
        with DB_LOCK: st.caption(f"🗄️ 무결점 DB: {len(bank_db)}")

if st.session_state.verified and btn:
    with st.spinner("최고 난이도 및 수식 검토 중..."):
        try:
            html_out, hits = asyncio.run(run_orchestrator(sub, num, score_val))
            st.success(f"✅ 발간 완료! (DB 활용: {hits}개)")
            st.components.v1.html(html_out, height=1200, scrolling=True)
        except Exception as e: st.error(f"❌ 오류 발생: {e}")

