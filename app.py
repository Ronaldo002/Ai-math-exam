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
    st.error("Secrets 설정(PAID_API_KEY)이 필요합니다!")
    st.stop()

SENDER_EMAIL = st.secrets.get("EMAIL_USER", "pgh001002@gmail.com")
SENDER_PASS = st.secrets.get("EMAIL_PASS", "gmjg cvsg pdjq hnpw")
ADMIN_EMAIL = "pgh001002@gmail.com"

# --- 2. DB 및 전역 락 설정 (충돌 및 루프 에러 방지) ---
@st.cache_resource
def get_databases():
    return TinyDB('user_registry.json'), TinyDB('question_bank.json')

db, bank_db = get_databases()
User, QBank = Query(), Query()

@st.cache_resource
def get_global_lock():
    return threading.Lock()

DB_LOCK = get_global_lock()

def safe_db_insert(data):
    with DB_LOCK: return bank_db.insert(data)

def safe_db_search(query):
    with DB_LOCK: return bank_db.search(query)

# --- 3. 수식 정밀 교정기 (Polisher) ---
def polish_math(text):
    if not text: return ""
    # log_2 -> \log_{2} 등 수식 기호 정규화
    text = re.sub(r'log_([a-zA-Z0-9{}]+)', r'\\log_{\1}', text)
    text = re.sub(r'([a-zA-Z])_([a-zA-Z0-9])(?![a-zA-Z0-9{}])', r'\1_{\2}', text)
    text = re.sub(r'([a-zA-Z0-9])\^([a-zA-Z0-9])(?![a-zA-Z0-9{}])', r'\1^{\2}', text)
    text = text.replace('Σ', r'\sum').replace('∫', r'\int').replace('lim', r'\lim')
    return text

def clean_option_text(text):
    # 선지 앞의 번호 찌꺼기 제거 (195 -> 95 버그 수정 버전)
    return re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)).strip()

# --- 4. 수능 블루프린트 ---
def get_exam_blueprint(choice_sub, total_num, custom_score=None):
    blueprint = []
    if total_num == 30:
        for i in range(1, 23):
            if i in [1, 2]: score, diff, domain = 2, "쉬움", "기초 연산"
            elif i in [15, 21, 22]: score, diff, domain = 4, "킬러", "심화 추론"
            else: score, diff, domain = 4 if i > 8 else 3, "보통", "수학 I, II"
            blueprint.append({"num": i, "sub": "수학 I, II", "diff": diff, "score": score, "type": "객관식" if i <= 15 else "단답형", "domain": domain})
        for i in range(23, 31):
            if i in [23, 24]: score, diff, domain = 2, "쉬움", f"{choice_sub} 기초"
            elif i in [29, 30]: score, diff, domain = 4, "최종 킬러", f"{choice_sub} 최고난도"
            else: score, diff, domain = 3, "보통", f"{choice_sub} 핵심"
            blueprint.append({"num": i, "sub": choice_sub, "diff": diff, "score": score, "type": "객관식" if i <= 28 else "단답형", "domain": domain})
    else:
        for i in range(1, total_num + 1):
            blueprint.append({"num": i, "sub": choice_sub, "diff": "보통", "score": custom_score or 3, "type": "객관식", "domain": f"{choice_sub} 랜덤"})
    return blueprint

# --- 5. HTML 렌더링 템플릿 ---
def get_html_template(p_html, s_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']] }} }};</script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
            * {{ font-family: 'Nanum Myeongjo', serif; }}
            body {{ background: #f0f2f6; margin: 0; }}
            .paper-container {{ display: flex; flex-direction: column; align-items: center; padding: 20px 0; }}
            .paper {{ background: white; width: 210mm; padding: 15mm 18mm; margin-bottom: 30px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); position: relative; }}
            .header {{ text-align: center; border-bottom: 2.5px solid #000; margin-bottom: 35px; }}
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 50px; min-height: 230mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: #ddd; }}
            .question-box {{ position: relative; line-height: 2.0; font-size: 11pt; padding-left: 35px; margin-bottom: 40px; }}
            .q-num {{ position: absolute; left: 0; top: 3px; font-weight: 800; border: 2px solid #000; width: 24px; text-align: center; }}
            .options-container {{ margin-top: 25px; display: flex; justify-content: space-between; font-size: 10.5pt; }}
            .condition-box {{ border: 1.5px solid #000; padding: 10px; margin: 10px 0; background: #fafafa; font-weight: 700; }}
            .svg-container {{ text-align: center; margin: 15px 0; }}
            .sol-item {{ margin-bottom: 30px; border-bottom: 1px dashed #eee; padding-bottom: 15px; }}
        </style>
    </head>
    <body><div class="paper-container">{p_html}<div class="paper"><h2>[정답 및 해설]</h2>{s_html}</div></div></body>
    </html>
    """

# --- 6. AI 생성 엔진 ---
async def generate_batch_ai(q_info):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    batch_id = str(uuid.uuid4())
    prompt = f"""[과목]:{q_info['sub']} [단원]:{q_info['domain']} [배점]:{q_info['score']}
[규칙] 1. 수식은 무조건 $ $ 사용. 2. (가),(나) 조건은 <div class='condition-box'> 사용. 3. 도형 필요시 <svg> 사용. 4. 객관식 선지는 'options' 배열에 5개 분리.
오직 JSON 배열로 응답: [{{ "question": "...", "options": ["..."], "solution": "..." }}]"""
    try:
        res = await model.generate_content_async(prompt, generation_config=genai.types.GenerationConfig(temperature=0.8, response_mime_type="application/json"))
        return [{**d, "batch_id": batch_id, "sub": q_info['sub'], "domain": q_info['domain'], "score": q_info['score'], "type": q_info['type']} for d in json.loads(res.text.strip())]
    except: return []

async def get_safe_q(q_info, used_ids, used_batch_ids):
    # DB 검색
    available = safe_db_search((QBank.sub == q_info['sub']) & (QBank.domain == q_info['domain']) & (QBank.score == q_info['score']))
    fresh = [q for q in available if str(q.doc_id) not in used_ids and q.get('batch_id') not in used_batch_ids]
    if fresh:
        sel = random.choice(fresh)
        used_ids.add(str(sel.doc_id))
        if 'batch_id' in sel: used_batch_ids.add(sel['batch_id'])
        return {**sel, "num": q_info['num'], "source": "DB"}
    # 신규 생성
    new_batch = await generate_batch_ai(q_info)
    if new_batch:
        for idx, q in enumerate(new_batch):
            doc_id = safe_db_insert(q)
            if idx == 0: res = {**q, "num": q_info['num'], "doc_id": str(doc_id), "source": "AI"}
        used_ids.add(res['doc_id'])
        if 'batch_id' in res: used_batch_ids.add(res['batch_id'])
        return res
    return {"num": q_info['num'], "question": "지연 발생..", "options": [], "solution": "오류"}

async def run_orchestrator(choice_sub, num, score_val=None):
    blueprint = get_exam_blueprint(choice_sub, num, score_val)
    start_time = time.time()
    used_ids, used_batch_ids = set(), set()
    tasks = [get_safe_q(q, used_ids, used_batch_ids) for q in blueprint]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda x: x.get('num', 999))
    
    p_html, s_html = "", ""
    for i in range(0, len(results), 2):
        pair = results[i:i+2]
        q_cont = ""
        for item in pair:
            # 선지 렌더링 코드 (에러 수정됨)
            opt_html = ""
            if item.get('type') == '객관식' and item.get('options'):
                spans = []
                for j, o in enumerate(item['options'][:5]):
                    clean_o = clean_option_text(o)
                    spans.append(f"<span>{chr(9312+j)} {clean_o}</span>")
                opt_html = f"<div class='options-container'>{''.join(spans)}</div>"
            
            q_cont += f"<div class='question-box'><span class='q-num'>{item['num']}</span> {polish_math(item['question'])} <b>[{item.get('score',3)}점]</b>{opt_html}</div>"
            s_html += f"<div class='sol-item'><b>{item['num']}번:</b> {polish_math(item['solution'])}</div>"
        p_html += f"<div class='paper'><div class='header'><h1>2026 수능 모의평가</h1><h3>수학 영역 ({choice_sub})</h3></div><div class='question-grid'>{q_cont}</div></div>"
    
    return p_html, s_html, time.time()-start_time, sum(1 for r in results if r.get('source') == 'DB')

# --- 7. 메인 UI ---
st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")
if 'v' not in st.session_state: st.session_state.v = False

with st.sidebar:
    st.title("🎓 본부 인증")
    email = st.text_input("이메일", value=ADMIN_EMAIL if st.session_state.v else "")
    if email == ADMIN_EMAIL: st.session_state.v = True
    if st.session_state.v:
        st.divider()
        mode = st.radio("모드", ["맞춤 문항", "30문항 풀세트"])
        sub = st.selectbox("과목", ["미적분", "확률과 통계", "기하"])
        num = 30 if mode == "30문항 풀세트" else st.slider("문항 수", 2, 10, 4, step=2)
        score = int(st.selectbox("배점", ["2", "3", "4"])) if mode == "맞춤 문항" else None
        btn = st.button("🚀 발간 시작", use_container_width=True)

if st.session_state.v:
    if 'btn' in locals() and btn:
        with st.spinner("최종 안정화 엔진 가동 중..."):
            p, s, elap, hits = asyncio.run(run_orchestrator(sub, num, score))
            st.success(f"✅ 완료! ({elap:.1f}초 | DB사용: {hits}개)")
            st.components.v1.html(get_html_template(p, s), height=1200, scrolling=True)
