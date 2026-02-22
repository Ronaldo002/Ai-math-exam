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

# --- 2. DB 및 자물쇠 ---
@st.cache_resource
def get_databases():
    return TinyDB('user_registry.json'), TinyDB('question_bank.json')

db, bank_db = get_databases()
User, QBank = Query(), Query()

@st.cache_resource
def get_global_lock():
    return threading.Lock()

DB_LOCK = get_global_lock()

# --- 3. [혁신] 초간단 텍스트 정제 (에러 원인 정규식 모두 삭제) ---
def polish_math(text):
    if not text: return ""
    # 메타데이터만 삭제 (에러 방지를 위해 수식은 건드리지 않음)
    text = re.sub(r'^(과목|단원|배점|유형):.*?\n', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[.*?점\]$', '', text.strip())
    return text.strip()

def clean_option(text):
    return re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)).strip()

def safe_save_to_bank(batch):
    def _bg_save():
        with DB_LOCK:
            for q in batch:
                try:
                    if not bank_db.search(QBank.question == q.get("question", "")):
                        bank_db.insert(q)
                except: continue
    threading.Thread(target=_bg_save, daemon=True).start()

# --- 4. [핵심] HTML 템플릿 (자바스크립트 자동 교정 엔진 탑재) ---
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
                    displayMath: [['$$', '$$']]
                }},
                options: {{
                    processHtmlClass: 'mathjax-process'
                }}
            }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
        <script>
            // 브라우저에서 실행되는 수식 교정 엔진 (파이썬 에러 0%)
            document.addEventListener("DOMContentLoaded", function() {{
                const content = document.body.innerHTML;
                let fixed = content
                    // 1. 모든 lim를 수직 정렬 규격으로 강제 변환
                    .replace(/\\\\lim/g, "\\\\displaystyle \\\\lim")
                    .replace(/lim /g, "\\\\displaystyle \\\\lim ")
                    // 2. 화살표 보정
                    .replace(/->/g, "\\\\to")
                    // 3. 첨자 중괄호 보정
                    .replace(/([a-zA-Z])_([a-zA-Z0-9])/g, "$1_{{$2}}")
                    .replace(/([a-zA-Z0-9])\\^([a-zA-Z0-9])/g, "$1^{{$2}}");
                
                document.body.innerHTML = fixed;
            }});
        </script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
            * {{ font-family: 'Nanum Myeongjo', serif !important; }}
            body {{ background: #f0f2f6; margin: 0; color: #000; }}
            .paper-container {{ display: flex; flex-direction: column; align-items: center; padding: 20px 0; }}
            .paper {{ background: white; width: 210mm; padding: 15mm 18mm; margin-bottom: 30px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); position: relative; }}
            .header {{ text-align: center; border-bottom: 2.5px solid #000; margin-bottom: 35px; padding-bottom: 10px; }}
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 55px; min-height: 230mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #ddd; }}
            .question-box {{ position: relative; line-height: 2.8; font-size: 11pt; padding-left: 25px; margin-bottom: 60px; text-align: justify; }}
            .q-num {{ position: absolute; left: 0; top: 0; font-weight: 800; font-size: 12pt; }}
            .options-container {{ margin-top: 35px; display: flex; flex-wrap: wrap; gap: 15px 5px; font-size: 10.5pt; }}
            .options-container span {{ flex: 1 1 18%; min-width: 130px; white-space: nowrap; }}
            .condition-box {{ border: 1.5px solid #000; padding: 12px; margin: 15px 0; background: #fafafa; font-weight: 700; }}
            .sol-item {{ margin-bottom: 35px; border-bottom: 1px dashed #eee; padding-bottom: 15px; }}
            mjx-container[display="true"] {{ margin: 15px 0 !important; display: block; }}
        </style>
    </head>
    <body class="mathjax-process"><div class="paper-container">{p_html}<div class="paper"><h2 style="text-align:center;">[정답 및 해설]</h2>{s_html}</div></div></body>
    </html>
    """

# --- 5. 생성 및 오케스트레이터 ---
def get_exam_blueprint(choice_sub, total_num, custom_score=None):
    blueprint = []
    if total_num == 30:
        for i in range(1, 23):
            score = 2 if i in [1, 2] else 4 if i in [15, 21, 22] else 3
            blueprint.append({"num": i, "sub": "수학 I, II", "score": score, "type": "객관식" if i <= 15 else "단답형", "domain": "수학 I, II"})
        for i in range(23, 31):
            score = 2 if i in [23, 24] else 4 if i in [29, 30] else 3
            blueprint.append({"num": i, "sub": choice_sub, "score": score, "type": "객관식" if i <= 28 else "단답형", "domain": choice_sub})
    else:
        for i in range(1, total_num + 1):
            blueprint.append({"num": i, "sub": choice_sub, "score": custom_score or 3, "type": "객관식", "domain": choice_sub})
    return blueprint

async def generate_batch_ai(q_info, size=5):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    batch_id = str(uuid.uuid4())
    prompt = f"""과목:{q_info['sub']} | 배점:{q_info['score']}
[규칙] 1. 수식 $ $ 필수. 2. 극한은 lim x->0 형태로만 작성(교정은 엔진이 수행). 3. JSON 배열 {size}개: [{{ "question": "...", "options": ["..."], "solution": "..." }}]"""
    try:
        res = await model.generate_content_async(prompt, generation_config=genai.types.GenerationConfig(temperature=0.8, response_mime_type="application/json"))
        return [{**d, "batch_id": batch_id, "sub": q_info['sub'], "score": q_info['score'], "type": q_info['type']} for d in json.loads(res.text.strip())]
    except: return []

async def get_safe_q(q_info, used_ids, used_batch_ids):
    with DB_LOCK:
        available = bank_db.search((QBank.sub == q_info['sub']) & (QBank.score == q_info['score']))
    fresh = [q for q in available if str(q.doc_id) not in used_ids and q.get('batch_id') not in used_batch_ids]
    if fresh:
        sel = random.choice(fresh)
        used_ids.add(str(sel.doc_id)); used_batch_ids.add(sel.get('batch_id'))
        return {**sel, "num": q_info['num'], "source": "DB"}
    new_batch = await generate_batch_ai(q_info)
    if new_batch: return {**new_batch[0], "num": q_info['num'], "source": "AI", "full_batch": new_batch}
    return {"num": q_info['num'], "question": "서버 로딩 중..", "options": [], "solution": "오류"}

async def run_orchestrator(sub, num, score_v=None):
    blueprint = get_exam_blueprint(sub, num, score_v)
    start_time = time.time()
    used_ids, used_batch_ids = set(), set()
    tasks = [get_safe_q(q, used_ids, used_batch_ids) for q in blueprint]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda x: x.get('num', 999))
    
    all_new = [r['full_batch'] for r in results if r.get('source') == "AI" and "full_batch" in r]
    if all_new: safe_save_to_bank([item for sublist in all_new for item in sublist])
    
    p_html, s_html = "", ""
    for i in range(0, len(results), 2):
        pair = results[i:i+2]
        q_cont = ""
        for item in pair:
            q_text = polish_math(item.get("question", ""))
            opts = item.get("options", [])
            opt_html = f"<div class='options-container'>{''.join([f'<span>{chr(9312+j)} {clean_option(o)}</span>' for j, o in enumerate(opts[:5])])}</div>" if item.get('type') == '객관식' else ""
            q_cont += f"<div class='question-box'><span class='q-num'>{item.get('num')}</span> {q_text} <b>[{item.get('score',3)}점]</b>{opt_html}</div>"
            s_html += f"<div class='sol-item'><b>{item.get('num')}번:</b> {polish_math(item.get('solution',''))}</div>"
        p_html += f"<div class='paper'><div class='header'><h1>2026 수능 모의평가</h1><h3>수학 영역 ({sub})</h3></div><div class='question-grid'>{q_cont}</div></div>"
    return p_html, s_html, time.time()-start_time, sum(1 for r in results if r.get('source') == 'DB')

# --- 6. UI ---
def send_verification_email(receiver, code):
    try:
        msg = MIMEMultipart(); msg['From'] = SENDER_EMAIL; msg['To'] = receiver; msg['Subject'] = "[인증번호]"
        msg.attach(MIMEText(f"번호: [{code}]", 'plain'))
        s = smtplib.SMTP('smtp.gmail.com', 587); s.starttls(); s.login(SENDER_EMAIL, SENDER_PASS); s.send_message(msg); s.quit()
        return True
    except: return False

st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")
if 'v' not in st.session_state: st.session_state.v = False

with st.sidebar:
    st.title("🎓 본부 인증")
    email_in = st.text_input("이메일", value=ADMIN_EMAIL if st.session_state.v else "")
    if email_in == ADMIN_EMAIL: st.session_state.v = True
    if not st.session_state.v:
        if st.button("인증번호 발송"):
            code = str(random.randint(100000, 999999))
            if send_verification_email(email_in, code):
                st.session_state.auth_code, st.session_state.mail_sent = code, True
                st.success("발송 완료!")
        if st.session_state.get('mail_sent'):
            c_in = st.text_input("6자리 입력")
            if st.button("확인"):
                if c_in == st.session_state.auth_code: st.session_state.v = True; st.rerun()

    if st.session_state.v:
        st.divider()
        mode = st.radio("모드", ["맞춤 문항", "30문항 풀세트"])
        sub = st.selectbox("과목", ["미적분", "확률과 통계", "기하"])
        num = 30 if mode == "30문항 풀세트" else st.slider("문항 수", 2, 30, 4, step=2)
        btn = st.button("🚀 발간 시작", use_container_width=True)
        with DB_LOCK: st.caption(f"🗄️ DB 축적량: {len(bank_db)}")

if st.session_state.v and btn:
    with st.spinner("수식 조판 최적화 중..."):
        p, s, elap, hits = asyncio.run(run_orchestrator(sub, num))
        st.success(f"✅ 완료! ({elap:.1f}초)")
        st.components.v1.html(get_html_template(p, s), height=1200, scrolling=True)
