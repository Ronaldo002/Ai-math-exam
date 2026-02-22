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

# --- 3. 정제 엔진 (수식 및 텍스트) ---
def polish_output(text):
    if not text: return ""
    text = re.sub(r'^(과목|단원|배점|유형|난이도|수학):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    math_words = ['frac', 'theta', 'pi', 'sqrt', 'log', 'lim', 'to', 'infty', 'sin', 'cos', 'tan', 'sum', 'int']
    for word in math_words:
        text = re.sub(rf'(?<!\\){word}', rf'\\{word}', text)
    return text.strip()

def clean_option(text):
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

# --- 4. 수능형 문항 배치 로직 ---
def get_exam_blueprint(choice_sub, total_num, custom_score=None):
    blueprint = []
    if total_num == 30:
        for i in range(1, 16): # 공통 객관식
            score = 2 if i <= 3 else 4 if i in [9,10,11,12,13,14,15] else 3
            blueprint.append({"num": i, "sub": "수학 I, II", "score": score, "type": "객관식", "cat": "공통"})
        for i in range(16, 23): # 공통 주관식
            score = 4 if i in [21, 22] else 3
            blueprint.append({"num": i, "sub": "수학 I, II", "score": score, "type": "주관식", "cat": "공통"})
        for i in range(23, 29): # 선택 객관식
            score = 2 if i == 23 else 4 if i == 28 else 3
            blueprint.append({"num": i, "sub": choice_sub, "score": score, "type": "객관식", "cat": "선택"})
        for i in range(29, 31): # 선택 주관식
            blueprint.append({"num": i, "sub": choice_sub, "score": 4, "type": "주관식", "cat": "선택"})
    else:
        for i in range(1, total_num + 1):
            blueprint.append({"num": i, "sub": choice_sub, "score": custom_score or 3, "type": "객관식", "cat": "맞춤"})
    return blueprint

# --- 5. HTML/CSS 템플릿 (PDF 다운로드 + 수능 조판) ---
def get_html_template(p_html, s_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']], displayMath: [['$$', '$$']] }} }};</script>
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
            body {{ background: #f0f2f6; margin: 0; padding: 20px; color: #000; }}
            .no-print {{ text-align: center; margin-bottom: 20px; }}
            .btn-download {{ background: #2e7d32; color: white; padding: 12px 24px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; font-weight: bold; }}
            .paper-container {{ display: flex; flex-direction: column; align-items: center; }}
            .paper {{ background: white; width: 210mm; padding: 15mm 18mm; margin-bottom: 30px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); position: relative; page-break-after: always; }}
            .header {{ text-align: center; border-bottom: 2.5px solid #000; margin-bottom: 25px; padding-bottom: 10px; }}
            .cat-title {{ font-size: 14pt; font-weight: 800; border: 2px solid #000; display: inline-block; padding: 2px 15px; margin-bottom: 20px; }}
            .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 55px; min-height: 230mm; position: relative; }}
            .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: #ddd; }}
            .question-box {{ position: relative; line-height: 2.3; font-size: 11pt; padding-left: 30px; margin-bottom: 50px; text-align: justify; }}
            .q-num {{ position: absolute; left: 0; top: 0; font-weight: 800; font-size: 13pt; }}
            .options-container {{ margin-top: 25px; display: flex; flex-wrap: wrap; gap: 10px 5px; font-size: 10.5pt; }}
            .options-container span {{ flex: 1 1 18%; min-width: 135px; white-space: nowrap; }}
            .sol-item {{ margin-bottom: 35px; border-bottom: 1px dashed #eee; padding-bottom: 15px; }}
            @media print {{ .no-print {{ display: none; }} body {{ padding: 0; }} .paper {{ box-shadow: none; margin: 0; }} }}
        </style>
    </head>
    <body>
        <div class="no-print"><button class="btn-download" onclick="window.print()">🖨️ PDF 다운로드 / 인쇄</button></div>
        <div class="paper-container">{p_html}<div class="paper"><h2 style="text-align:center;">[정답 및 해설]</h2>{s_html}</div></div>
    </body>
    </html>
    """

# --- 6. 엔진 로직 ---
async def generate_batch_ai(q_info, size=3):
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"과목:{q_info['sub']} | 배점:{q_info['score']} | 난이도:수능형\n[필수] 수식 $ $ 사용. 5지선다는 options 배열에 5개. JSON 배열 {size}개 생성: [{{ \"question\": \"...\", \"options\": [...], \"solution\": \"...\" }}]"
    try:
        res = await model.generate_content_async(prompt, generation_config=genai.types.GenerationConfig(temperature=0.8, response_mime_type="application/json"))
        return [{**d, "batch_id": str(uuid.uuid4()), "sub": q_info['sub'], "score": q_info['score'], "type": q_info['type'], "cat": q_info.get('cat','공통')} for d in json.loads(res.text.strip())]
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
    return {"num": q_info['num'], "question": "생성 지연", "options": [], "solution": "오류"}

async def run_orchestrator(sub_choice, num_choice, score_choice=None):
    blueprint = get_exam_blueprint(sub_choice, num_choice, score_choice)
    used_ids, used_batch_ids = set(), set()
    results = []
    prog = st.progress(0); status = st.empty()
    chunk_size = 3
    for i in range(0, len(blueprint), chunk_size):
        chunk = blueprint[i : i + chunk_size]
        status.text(f"⏳ {i+1}번 ~ {min(i+chunk_size, 30)}번 문항 구성 중...")
        tasks = [get_safe_q(q, used_ids, used_batch_ids) for q in chunk]
        chunk_res = await asyncio.gather(*tasks)
        results.extend(chunk_res)
        all_new = [r['full_batch'] for r in chunk_res if r.get('source') == "AI" and "full_batch" in r]
        if all_new: safe_save_to_bank([item for sublist in all_new for item in sublist])
        prog.progress(min((i + chunk_size) / len(blueprint), 1.0))
    status.empty(); prog.empty()

    results.sort(key=lambda x: x.get('num', 999))
    p_html, s_html = "", ""
    
    # 영역별 렌더링 (공통/선택 분리)
    for cat_name in ["공통", "선택", "맞춤"]:
        cat_qs = [r for r in results if r.get('cat') == cat_name]
        if not cat_qs: continue
        
        cat_label = "공통과목 (수학 I, 수학 II)" if cat_name == "공통" else f"선택과목 ({sub_choice})" if cat_name == "선택" else "맞춤 문항"
        q_html_buffer = f"<div class='cat-title'>{cat_label}</div>"
        
        for item in cat_qs:
            q_text = polish_output(item.get("question", ""))
            opts = item.get("options", [])
            opt_html = ""
            if item.get('type') == '객관식' and opts:
                spans = "".join([f"<span>{chr(9312+j)} {clean_option(o)}</span>" for j, o in enumerate(opts[:5])])
                opt_html = f"<div class='options-container'>{spans}</div>"
            q_html_buffer += f"<div class='question-box'><span class='q-num'>{item.get('num')}</span> {q_text} <b>[{item.get('score',3)}점]</b>{opt_html}</div>"
            s_html += f"<div class='sol-item'><b>{item.get('num')}번:</b> {polish_output(item.get('solution',''))}</div>"
        
        # 페이지 단위 분할 (한 페이지당 약 8문항)
        q_list = q_html_buffer.split("<div class='question-box'>")
        header_text = q_list[0]
        q_items = q_list[1:]
        for j in range(0, len(q_items), 8):
            chunk = "".join([f"<div class='question-box'>{q}" for q in q_items[j:j+8]])
            p_html += f"<div class='paper'><div class='header'><h1>2026 수능 모의평가</h1></div>{header_text if j==0 else ''}<div class='question-grid'>{chunk}</div></div>"

    return p_html, s_html, sum(1 for r in results if r.get('source') == 'DB')

# --- 7. 인증 및 UI ---
def send_verification_email(receiver, code):
    try:
        msg = MIMEMultipart(); msg['From'] = SENDER_EMAIL; msg['To'] = receiver; msg['Subject'] = "[인증번호]"
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
                if c_in == st.session_state.auth_code: st.session_state.v = True; st.rerun()

    if st.session_state.v:
        st.divider()
        mode = st.radio("모드", ["30문항 풀세트", "맞춤 문항"])
        sub = st.selectbox("선택과목", ["미적분", "확률과 통계", "기하"])
        num = 30 if mode == "30문항 풀세트" else st.slider("문항 수", 2, 30, 4, step=2)
        score = int(st.selectbox("문항 난이도", ["2", "3", "4"])) if mode == "맞춤 문항" else None
        btn = st.button("🚀 발간 시작", use_container_width=True)
        with DB_LOCK: st.caption(f"🗄️ DB 축적량: {len(bank_db)}")

if st.session_state.v and btn:
    with st.spinner("수능 규격 조판 및 안정화 엔진 가동 중..."):
        p, s, hits = asyncio.run(run_orchestrator(sub, num, score))
        st.success(f"✅ 발간 완료! (DB 활용: {hits}개)")
        st.components.v1.html(get_html_template(p, s), height=1200, scrolling=True)

