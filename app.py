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

# --- 2. DB 및 전역 락 (ID 충돌 방지) ---
@st.cache_resource
def get_databases():
    return TinyDB('user_registry.json'), TinyDB('question_bank.json')

db, bank_db = get_databases()
User, QBank = Query(), Query()

@st.cache_resource
def get_global_lock():
    return threading.Lock()

DB_LOCK = get_global_lock()

# --- 3. [업데이트] 수식 및 텍스트 정밀 세척 엔진 ---
def polish_output(text):
    if not text: return ""
    # 1. 쓸데없는 메타데이터 문구 제거
    text = re.sub(r'^(과목|단원|배점|유형|난이도):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    # 2. 수식 깨짐(image_125785) 보정: frac -> \frac 등 누락된 백슬래시 자동 복구
    for word in ['frac', 'theta', 'pi', 'sqrt', 'log', 'lim', 'to', 'infty', 'sin', 'cos', 'tan']:
        text = re.sub(rf'(?<!\\){word}', rf'\\{word}', text)
    # 3. 중복 배점 표시 제거
    text = re.sub(r'\[.*?점\]$', '', text.strip())
    return text.strip()

def clean_option(text):
    # 선지 번호 기호 제거
    clean = re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)).strip()
    return polish_output(clean)

def safe_save_to_bank(batch):
    def _bg_save():
        with DB_LOCK:
            for q in batch:
                try:
                    if not bank_db.search(QBank.question == q.get("question", "")):
                        bank_db.insert(q)
                except: continue
    threading.Thread(target=_bg_save, daemon=True).start()

# --- 4. [정밀 조절] 수능형 30문항 블루프린트 ---
def get_exam_blueprint(choice_sub, total_num, custom_score=None):
    blueprint = []
    if total_num == 30:
        # 공통과목 (수학 I, II): 1~22번
        for i in range(1, 23):
            if i in [1, 2]: score, diff = 2, "기초"
            elif i in [15, 22]: score, diff = 4, "최고난도 킬러"
            elif i in [9, 10, 11, 12, 13, 14, 20, 21]: score, diff = 4, "준킬러/킬러"
            else: score, diff = 3, "보통"
            blueprint.append({"num": i, "sub": "수학 I, II", "score": score, "diff": diff, "type": "객관식" if i <= 15 else "단답형"})
        
        # 선택과목: 23~30번
        for i in range(23, 31):
            if i == 23: score, diff = 2, "기초"
            elif i == 30: score, diff = 4, "최고난도 킬러"
            elif i in [28, 29]: score, diff = 4, "준킬러"
            else: score, diff = 3, "보통"
            blueprint.append({"num": i, "sub": choice_sub, "score": score, "diff": diff, "type": "객관식" if i <= 28 else "단답형"})
    else:
        for i in range(1, total_num + 1):
            blueprint.append({"num": i, "sub": choice_sub, "score": custom_score or 3, "diff": "보통", "type": "객관식"})
    return blueprint

# --- 5. HTML 템플릿 (수식 렌더링 최적화) ---
def get_html_template(p_html, s_html, subject):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script>
            window.MathJax = {{ tex: {{ inlineMath: [['$', '$']], displayMath: [['$$', '$$']] }}, chmth: {{ scale: 1.05 }} }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
        <script>
            document.addEventListener("DOMContentLoaded", function() {{
                const content = document.body.innerHTML;
                document.body.innerHTML = content.replace(/\\\\lim/g, "\\\\displaystyle \\\\lim").replace(/->/g, "\\\\to");
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
            .question-box {{ position: relative; line-height: 2.1; font-size: 11pt; padding-left: 25px; margin-bottom: 45px; text-align: justify; }}
            .q-num {{ position: absolute; left: 0; top: 0; font-weight: 800; font-size: 12pt; }}
            .options-container {{ margin-top: 25px; display: flex; flex-wrap: wrap; gap: 10px 5px; font-size: 10.5pt; }}
            .options-container span {{ flex: 1 1 18%; min-width: 130px; white-space: nowrap; }}
            .condition-box {{ border: 1.5px solid #000; padding: 12px; margin: 15px 0; background: #fafafa; font-weight: 700; }}
            .sol-item {{ margin-bottom: 35px; border-bottom: 1px dashed #eee; padding-bottom: 15px; }}
        </style>
    </head>
    <body><div class="paper-container">{p_html}<div class="paper"><h2>[정답 및 해설]</h2>{s_html}</div></div></body>
    </html>
    """

# --- 6. AI 생성 및 오케스트레이터 ---
async def generate_batch_ai(q_info, size=5):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    batch_id = str(uuid.uuid4())
    # 4점 킬러 난이도 강화 지시
    killer_prompt = "최고난도 문항은 여러 단원의 개념을 복합하고 고도의 추론 능력을 요구하도록 구성할 것." if "킬러" in q_info['diff'] else ""
    prompt = f"""과목:{q_info['sub']} | 난이도:{q_info['diff']} | 배점:{q_info['score']}
[필수 규칙]
1. 수식은 무조건 $ $ 사용. 분수는 \\frac{{a}}{{b}}, 기호는 \\theta, \\pi 처럼 백슬래시 필수.
2. 5지선다는 무조건 5개의 선지를 'options' 배열에 넣을 것.
3. 문제 지문에 쓸데없는 말(과목명, 난이도 등) 절대 포함 금지. 오직 문제만.
4. {killer_prompt}
JSON 배열 {size}개 생성: [{{ "question": "...", "options": ["...","...","...","...","..."], "solution": "..." }}]"""
    
    for _ in range(3): # 재시도로 지연 현상 방지
        try:
            res = await model.generate_content_async(prompt, generation_config=genai.types.GenerationConfig(temperature=0.8, response_mime_type="application/json"))
            data = json.loads(res.text.strip())
            return [{**d, "batch_id": batch_id, "sub": q_info['sub'], "score": q_info['score'], "type": q_info['type']} for d in data]
        except: await asyncio.sleep(1)
    return []

async def get_safe_q(q_info, used_ids, used_batch_ids):
    with DB_LOCK:
        available = bank_db.search((QBank.sub == q_info['sub']) & (QBank.score == q_info['score']))
    fresh = [q for q in available if str(q.doc_id) not in used_ids and q.get('batch_id') not in used_batch_ids]
    if fresh:
        sel = random.choice(fresh)
        used_ids.add(str(sel.doc_id)); used_batch_ids.add(sel.get('batch_id'))
        return {**sel, "num": q_info['num'], "source": "DB"}
    new_batch = await generate_batch_ai(q_info, size=5)
    if new_batch: return {**new_batch[0], "num": q_info['num'], "source": "AI", "full_batch": new_batch}
    return {"num": q_info['num'], "question": "문제 생성 중 지연 발생..", "options": [], "solution": "오류"}

async def run_orchestrator(choice_sub, num, score_v=None):
    blueprint = get_exam_blueprint(choice_sub, num, score_v)
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
            q_text = polish_output(item.get("question", ""))
            opts = item.get("options", [])
            opt_html = ""
            if item.get('type') == '객관식' and opts:
                # 5지선다 보장 렌더링
                spans = "".join([f"<span>{chr(9312+j)} {clean_option(o)}</span>" for j, o in enumerate(opts[:5])])
                opt_html = f"<div class='options-container'>{spans}</div>"
            q_cont += f"<div class='question-box'><span class='q-num'>{item.get('num')}</span> {q_text} <b>[{item.get('score',3)}점]</b>{opt_html}</div>"
            s_html += f"<div class='sol-item'><b>{item.get('num')}번:</b> {polish_output(item.get('solution',''))}</div>"
        p_html += f"<div class='paper'><div class='header'><h1>2026 수능 모의평가</h1><h3>수학 영역 ({choice_sub})</h3></div><div class='question-grid'>{q_cont}</div></div>"
    return p_html, s_html, time.time()-start_time, sum(1 for r in results if r.get('source') == 'DB')

# --- 7. UI 및 인증 ---
def send_verification_email(receiver, code):
    try:
        msg = MIMEMultipart(); msg['From'] = SENDER_EMAIL; msg['To'] = receiver; msg['Subject'] = "[Premium 수능수학] 인증번호"
        msg.attach(MIMEText(f"인증번호: [{code}]", 'plain'))
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
                if c_in == st.session_state.auth_code:
                    st.session_state.v = True; st.rerun()

    if st.session_state.v:
        st.divider()
        mode = st.radio("모드", ["30문항 풀세트", "맞춤 문항"])
        sub_choice = st.selectbox("선택과목", ["미적분", "확률과 통계", "기하"])
        num_choice = 30 if mode == "30문항 풀세트" else st.slider("문항 수", 2, 30, 4, step=2)
        score_choice = int(st.selectbox("문항 난이도 (배점)", ["2", "3", "4"])) if mode == "맞춤 문항" else None
        btn = st.button("🚀 발간 시작", use_container_width=True)
        with DB_LOCK: st.caption(f"🗄️ DB 축적량: {len(bank_db)}")

if st.session_state.v and btn:
    with st.spinner("수능 규격 엔진 가동 및 정밀 조판 중..."):
        p, s, elap, hits = asyncio.run(run_orchestrator(sub_choice, num_choice, score_choice))
        st.success(f"✅ 완료! ({elap:.1f}초 | DB사용: {hits}개)")
        st.components.v1.html(get_html_template(p, s, sub_choice), height=1200, scrolling=True)
