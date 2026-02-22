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
    st.error("Secrets 설정이 필요합니다!")
    st.stop()

SENDER_EMAIL = st.secrets.get("EMAIL_USER", "pgh001002@gmail.com")
SENDER_PASS = st.secrets.get("EMAIL_PASS", "gmjg cvsg pdjq hnpw")
ADMIN_EMAIL = "pgh001002@gmail.com"

# --- 2. [해결책] 스레드 기반 안전 DB 제어 시스템 ---
@st.cache_resource
def get_databases():
    return TinyDB('user_registry.json'), TinyDB('question_bank.json')

db, bank_db = get_databases()
User, QBank = Query(), Query()

@st.cache_resource
def get_global_lock():
    # 루프 충돌을 피하기 위해 asyncio.Lock 대신 threading.Lock 사용
    return threading.Lock()

DB_LOCK = get_global_lock()

def safe_db_insert(data):
    with DB_LOCK:
        return bank_db.insert(data)

def safe_db_search(query):
    with DB_LOCK:
        return bank_db.search(query)

# --- 3. [업데이트] 수식 정밀 교정 필터 (Polisher) ---
def polish_math_text(text):
    if not text: return ""
    # 1. log_2(x) -> \log_{2}(x) 변환
    text = re.sub(r'log_([a-zA-Z0-9{}]+)', r'\\log_{\1}', text)
    # 2. a_n -> a_{n} 변환 (중괄호 누락 방지)
    text = re.sub(r'([a-zA-Z])_([a-zA-Z0-9])(?![a-zA-Z0-9{}])', r'\1_{\2}', text)
    # 3. x^2 -> x^{2} 변환
    text = re.sub(r'([a-zA-Z0-9])\^([a-zA-Z0-9])(?![a-zA-Z0-9{}])', r'\1^{\2}', text)
    # 4. 특수 기호 변환
    text = text.replace('Σ', r'\sum').replace('∫', r'\int').replace('lim', r'\lim')
    return text

def process_render_data(item):
    q_text = polish_math_text(item.get("question", ""))
    opts = item.get("options", [])
    
    # 과거 데이터 복구 로직 (선지가 문제에 포함된 경우)
    if not opts and "①" in q_text:
        parts = q_text.split("①")
        q_text = parts[0].strip()
        found_opts = re.split(r'[①②③④⑤]', "①" + parts[1])
        opts = [o.strip() for o in found_opts if o.strip()][:5]
    elif opts and "①" in q_text:
        q_text = q_text.split("①")[0].strip()
        
    return q_text, opts

# --- 4. 수능 블루프린트 설정 ---
def get_exam_blueprint(choice_subject, total_num, custom_score=None):
    blueprint = []
    if total_num == 30:
        for i in range(1, 23):
            if i in [1, 2]: score, diff, domain = 2, "쉬움", "지수로그 / 극한 기본"
            elif i in [15, 22]: score, diff, domain = 4, "킬러", "수열 추론 / 다항함수 추론"
            elif i in [8, 9, 10, 11, 12, 13, 14, 20, 21]: score, diff, domain = 4, "준킬러", "미적분학 / 수열 심화"
            else: score, diff, domain = 3, "보통", "수학 I, II 응용"
            blueprint.append({"num": i, "sub": "수학 I, II", "diff": diff, "score": score, "type": "객관식" if i <= 15 else "단답형", "domain": domain})
        for i in range(23, 31):
            if i in [23, 24]: score, diff, domain = 2, "쉬움", f"{choice_subject} 기초"
            elif i == 30: score, diff, domain = 4, "최종 킬러", f"{choice_subject} 최고난도"
            elif i in [28, 29]: score, diff, domain = 4, "준킬러", f"{choice_subject} 심화"
            else: score, diff, domain = 3, "보통", f"{choice_subject} 응용"
            blueprint.append({"num": i, "sub": choice_subject, "diff": diff, "score": score, "type": "객관식" if i <= 28 else "단답형", "domain": domain})
    else:
        for i in range(1, total_num + 1):
            score = custom_score or 3
            blueprint.append({"num": i, "sub": choice_subject, "diff": "표준", "score": score, "type": "객관식", "domain": f"{choice_subject} 전범위"})
    return blueprint

# --- 5. HTML/CSS 템플릿 ---
def get_html_template(subject, pages_html, solutions_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script>
            window.MathJax = {{ tex: {{ inlineMath: [['$', '$']], displayMath: [['$$', '$$']] }}, chtml: {{ scale: 0.98, matchFontHeight: true }} }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
            * {{ font-family: 'Nanum Myeongjo', serif !important; letter-spacing: -0.5px; }}
            body {{ background: #f0f2f6; color: #000; margin: 0; }}
            .btn-download {{ position: fixed; top: 20px; right: 20px; padding: 12px 24px; background: #000; color: #fff; border: none; cursor: pointer; z-index: 1000; font-weight: bold; border-radius: 5px; }}
            .paper-container {{ display: flex; flex-direction: column; align-items: center; padding: 20px 0; }}
            .paper {{ background: white; width: 210mm; padding: 15mm 18mm; margin-bottom: 30px; min-height: 297mm; position: relative; box-shadow: 0 5px 20px rgba(0,0,0,0.08); }}
            .header {{ text-align: center; border-bottom: 2.5px solid #000; padding-bottom: 12px; margin-bottom: 35px; }}
            .header h1 {{ font-weight: 800; font-size: 26pt; margin: 0; }}
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 55px; min-height: 220mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #ddd; }}
            .question-box {{ position: relative; line-height: 2.0; font-size: 11pt; padding-left: 36px; margin-bottom: 45px; text-align: justify; }}
            .q-num {{ position: absolute; left: 0; top: 4px; font-weight: 800; border: 2px solid #000; width: 25px; height: 25px; text-align: center; line-height: 23px; font-size: 11.5pt; background: #fff; }}
            .options-container {{ margin-top: 25px; display: flex; justify-content: space-between; font-size: 10.5pt; padding: 0 5px; }}
            .condition-box {{ border: 1.5px solid #000; padding: 10px 15px; margin: 10px 0; font-weight: bold; background: #fafafa; }}
            .svg-container {{ text-align: center; margin: 15px 0; }}
            .sol-section {{ border-top: 5px double #000; padding-top: 40px; }}
            .sol-item {{ margin-bottom: 35px; border-bottom: 1px dashed #eee; line-height: 1.85; }}
            @media print {{ @page {{ size: A4; margin: 0; }} .btn-download {{ display: none; }} .paper {{ box-shadow: none; margin: 0; page-break-after: always; }} }}
        </style>
    </head>
    <body>
        <button class="btn-download" onclick="window.print()">📥 PDF 저장</button>
        <div class="paper-container">{pages_html}<div class="paper sol-section"><h2 style="text-align:center;">[정답 및 해설]</h2>{solutions_html}</div></div>
    </body>
    </html>
    """

# --- 6. AI 생성 및 병렬 엔진 ---
async def generate_batch_ai_qs(q_info, batch_size=5):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    batch_id = str(uuid.uuid4())
    prompt = f"""[과목]:{q_info['sub']} | [단원]:{q_info['domain']} | [배점]:{q_info['score']}
[규칙] 1. 모든 수식/변수/숫자는 반드시 $ $로 감쌀 것. 특히 log 밑은 _{{}}, 첨자는 ^{{}} 필수. 
2. (가),(나) 조건 박스 <div class='condition-box'> 사용. 
3. 도형 필요시 <svg> 코드 포함. 
4. 객관식은 'options' 배열에 5개 분리. 
오직 JSON 배열로만 반환: [{{ "question": "...", "options": ["..."], "solution": "..." }}, ...]"""

    try:
        res = await model.generate_content_async(prompt, generation_config=genai.types.GenerationConfig(temperature=0.8, response_mime_type="application/json"))
        data_list = json.loads(res.text.strip())
        return [{**d, "batch_id": batch_id, "sub": q_info['sub'], "domain": q_info['domain'], "score": q_info['score'], "type": q_info['type']} for d in data_list]
    except: return []

async def get_safe_question(q_info, used_ids, used_batch_ids):
    # DB 검색
    available = safe_db_search((QBank.sub == q_info['sub']) & (QBank.domain == q_info['domain']) & (QBank.score == q_info['score']))
    fresh = [q for q in available if str(q.doc_id) not in used_ids and q.get('batch_id') not in used_batch_ids]
    
    if fresh:
        sel = random.choice(fresh)
        used_ids.add(str(sel.doc_id))
        if 'batch_id' in sel: used_batch_ids.add(sel['batch_id'])
        return {**sel, "num": q_info['num'], "source": "DB"}
    
    # DB에 없으면 생성
    new_qs = await generate_batch_ai_qs(q_info)
    if new_qs:
        for idx, q in enumerate(new_qs):
            doc_id = safe_db_insert(q)
            if idx == 0: 
                res = {**q, "num": q_info['num'], "doc_id": str(doc_id), "source": "AI"}
        used_ids.add(res['doc_id'])
        used_batch_ids.add(res.get('batch_id'))
        return res
    return {"num": q_info['num'], "question": "로딩 지연..", "options": [], "solution": "오류", "source": "ERROR"}

async def generate_exam_orchestrator(choice_sub, num, custom_score=None):
    blueprint = get_exam_blueprint(choice_sub, num, custom_score)
    start_time = time.time()
    used_ids, used_batch_ids = set(), set()
    
    tasks = [get_safe_question(q, used_ids, used_batch_ids) for q in blueprint]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda x: x.get('num', 999))
    
    p_html, s_html = "", ""
    for i in range(0, len(results), 2):
        pair = results[i:i+2]
        q_cont = ""
        for item in pair:
            q_text, opts = process_render_data(item)
            opt_html = f"<div class='options-container'>{''.join([f'<span>{chr(9312+j)} {re.sub(r\"^[①-⑤1-5][.) ]*\", \"\", str(o))}</span>' for j, o in enumerate(opts[:5])])}</div>" if item.get('type') == '객관식' else ""
            q_cont += f"<div class='question-box'><span class='q-num'>{item['num']}</span> {q_text} <span style='font-weight:700;'>[{item.get('score',3)}점]</span>{opt_html}</div>"
            s_html += f"<div class='sol-item'><b>{item['num']}번:</b> {polish_math_text(item['solution'])}</div>"
        p_html += f"<div class='paper'><div class='header'><h1>2026 수능 모의평가</h1><h3>수학 영역 ({choice_sub})</h3></div><div class='question-grid'>{q_cont}</div></div>"
    
    return p_html, s_html, time.time()-start_time, sum(1 for r in results if r.get('source') == 'DB')

# --- 7. 메인 UI ---
st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")

if 'verified' not in st.session_state: st.session_state.verified = False

with st.sidebar:
    st.title("🎓 본부 인증")
    email_input = st.text_input("이메일", value=ADMIN_EMAIL if st.session_state.verified else "")
    if email_input == ADMIN_EMAIL: st.session_state.verified = True
    
    if st.session_state.verified:
        st.divider()
        mode = st.radio("모드", ["맞춤 문항", "30문항 풀세트"])
        choice_sub = st.selectbox("과목", ["미적분", "확률과 통계", "기하"])
        num = 30 if mode == "30문항 풀세트" else st.slider("문항 수", 2, 10, 4, step=2)
        score_val = int(st.selectbox("배점", ["2", "3", "4"])) if mode == "맞춤 문항" else None
        gen_btn = st.button("🚀 발간 시작", use_container_width=True)

if st.session_state.verified:
    can_use, remain = check_user_limit(email_input)
    if can_use:
        st.info(f"📊 남은 횟수: {remain} | 과목: {choice_sub}")
        if 'gen_btn' in locals() and gen_btn:
            with st.spinner("루프 충돌 방어 및 렌더링 중..."):
                p, s, elap, hits = asyncio.run(generate_exam_orchestrator(choice_sub, num, score_val))
                st.success(f"✅ 완료! ({elap:.1f}초 | DB사용: {hits}개)")
                st.components.v1.html(get_html_template(choice_sub, p, s), height=1200, scrolling=True)
                if email_input != ADMIN_EMAIL:
                    with DB_LOCK: db.table('users').update({'count': db.table('users').get(User.email == email_input)['count'] + 1}, User.email == email_input)
    else: st.error("🚫 횟수 초과")
