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

# --- 1. 환경 설정 및 안전 필터 해제 세팅 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("PAID_API_KEY 설정이 필요합니다!")
    st.stop()

# AI가 문제를 검열하지 못하도록 모든 안전 필터 해제
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
    return TinyDB('user_registry.json'), TinyDB('question_bank.json')

db, bank_db = get_databases()
User, QBank = Query(), Query()

@st.cache_resource
def get_global_lock():
    return threading.Lock()

DB_LOCK = get_global_lock()

# --- 3. 초정밀 텍스트 정제 엔진 ---
def polish_output(text):
    if not text: return ""
    text = re.sub(r'^(과목|단원|배점|유형|난이도|수학\s?[I|II|1|2]|Step\s?\d):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^Step\s?\d:.*?\n', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?점\]\s*', '', text)
    
    math_tokens = ['frac', 'theta', 'pi', 'sqrt', 'log', 'lim', 'to', 'infty', 'sin', 'cos', 'tan', 'sum', 'int', 'alpha', 'beta']
    for token in math_tokens:
        text = re.sub(rf'(?<!\\)\b{token}\b', rf'\\{token}', text)
        
    text = text.replace('->', r'\to')
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

# --- 4. 수능 표준 배치 설계 ---
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

# --- 5. HTML/CSS 템플릿 ---
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
        <script>
            document.addEventListener("DOMContentLoaded", function() {{
                const content = document.body.innerHTML;
                document.body.innerHTML = content.replace(/\\\\lim/g, "\\\\displaystyle \\\\lim").replace(/->/g, "\\\\to");
            }});
        </script>
    </body>
    </html>
    """

# --- 6. (UI용) AI 생성 엔진 (안전 필터 해제 및 강제 JSON 파싱) ---
async def generate_batch_ai(q_info, size=2): 
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    
    # [차단 원인 제거] '킬러' 단어 삭제 및 우회 표현 사용
    diff_guide = ""
    if q_info['score'] == 4:
        if q_info.get('num', 0) in [15, 22, 30]:
            diff_guide = "[초고난도 변별력 문항] (가), (나) 조건을 제시하고 복합 개념 융합 출제."
        else:
            diff_guide = "[고난도 4점] 복합 사고력 요구."
    elif q_info['score'] == 3:
        diff_guide = "[응용 3점] 수능 3점 수준."
    else:
        diff_guide = "[기초 2점] 수능 2점 수준 기초 연산."

    opt_rule = "반드시 options 배열에 5개의 선지를 채울 것." if q_info['type'] == '객관식' else "주관식(단답형)이므로 options 배열은 비워둘 것."

    prompt = f"""과목:{q_info['sub']} | 배점:{q_info['score']} | 유형:{q_info['type']}
[지시사항] 
1. {diff_guide}
2. {opt_rule}
3. 수식 $ $ 필수. 과목명 등 부가 텍스트 금지.
JSON 배열 {size}개 생성: [{{ "question": "...", "options": [...], "solution": "..." }}]"""
    
    try:
        # 안전 필터 전면 무력화
        res = await model.generate_content_async(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.85, response_mime_type="application/json"))
        
        raw_text = res.text.strip()
        # 좀 더 안전한 JSON 추출 로직
        match = re.search(r'\[.*\]', raw_text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            data = json.loads(raw_text)
            
        return [{**d, "batch_id": str(uuid.uuid4()), "sub": q_info['sub'], "score": q_info['score'], "type": q_info['type']} for d in data]
    except Exception as e:
        print(f"[AI 생성 에러] {e}") # 로그 확인용
        return []

async def get_safe_q(q_info, used_ids, used_batch_ids):
    with DB_LOCK:
        available = bank_db.search((QBank.sub == q_info['sub']) & (QBank.score == q_info['score']) & (QBank.type == q_info['type']))
    fresh = [q for q in available if str(q.doc_id) not in used_ids and q.get('batch_id') not in used_batch_ids]
    if fresh:
        sel = random.choice(fresh)
        used_ids.add(str(sel.doc_id)); used_batch_ids.add(sel.get('batch_id'))
        return {**sel, "num": q_info['num'], "source": "DB", "cat": q_info.get('cat', '공통')}
    
    for _ in range(3):
        new_batch = await generate_batch_ai(q_info, size=2)
        if new_batch: 
            return {**new_batch[0], "num": q_info['num'], "source": "AI", "full_batch": new_batch, "cat": q_info.get('cat', '공통')}
        await asyncio.sleep(1.5) 
        
    return {
        "num": q_info.get('num', 0), 
        "score": q_info.get('score', 3), 
        "type": q_info.get('type', '객관식'),
        "cat": q_info.get('cat', '공통'),
        "question": "서버 응답 지연으로 생성을 실패했습니다.", 
        "options": [], 
        "solution": "오류", 
        "source": "ERROR"
    }

async def run_orchestrator(sub_choice, num_choice, score_choice=None):
    blueprint = get_exam_blueprint(sub_choice, num_choice, score_choice)
    used_ids, used_batch_ids = set(), set()
    results = []
    prog = st.progress(0); status = st.empty()
    
    chunk_size = 2 
    for i in range(0, len(blueprint), chunk_size):
        chunk = blueprint[i : i + chunk_size]
        status.text(f"⏳ {i+1}번 ~ {min(i+chunk_size, 30)}번 생성 중... (안전망 가동 완료)")
        tasks = [get_safe_q(q, used_ids, used_batch_ids) for q in chunk]
        chunk_res = await asyncio.gather(*tasks)
        results.extend(chunk_res)
        
        all_new = [r['full_batch'] for r in chunk_res if r.get('source') == "AI" and "full_batch" in r]
        if all_new: safe_save_to_bank([item for sublist in all_new for item in sublist])
        prog.progress(min((i + chunk_size) / len(blueprint), 1.0))
        await asyncio.sleep(1.0)
    status.empty(); prog.empty()

    results.sort(key=lambda x: x.get('num', 999))
    p_html, s_html = "" , ""
    
    pages = []
    current_page = []
    for item in results:
        if item.get('num') == 23 and len(current_page) > 0:
            pages.append(current_page)
            current_page = []
        current_page.append(item)
        if len(current_page) == 2:
            pages.append(current_page)
            current_page = []
            
    if current_page:
        pages.append(current_page)

    for page in pages:
        first_num = page[0].get('num', 0)
        
        header_html = ""
        if first_num == 1:
            header_html = "<div class='cat-header-container'><div class='cat-header'>■ 공통과목 (수학 I, 수학 II)</div></div>"
        elif first_num == 23:
            header_html = f"<div class='cat-header-container'><div class='cat-header'>■ 선택과목 ({sub_choice})</div></div>"
            
        q_chunk = ""
        for item in page:
            num_val = item.get('num', '')
            score_val = item.get('score', 3)
            q_type = item.get('type', '객관식')
            opts = item.get("options", [])
            q_text = polish_output(item.get("question", ""))

            opt_html = ""
            if q_type == '객관식' and opts and isinstance(opts, list) and len(opts) >= 1:
                spans = "".join([f"<span>{chr(9312+j)} {clean_option(str(o))}</span>" for j, o in enumerate(opts[:5])])
                opt_html = f"<div class='options-container'>{spans}</div>"

            q_chunk += f"<div class='question-box'><span class='q-num'>{num_val}</span> {q_text} <b>[{score_val}점]</b>{opt_html}</div>"
            s_html += f"<div class='sol-item'><b>{num_val}번:</b> {polish_output(item.get('solution',''))}</div>"
        
        p_html += f"<div class='paper'><div class='header'><h1>2026 수능 모의평가 (수학 영역)</h1></div>{header_html}<div class='question-grid'>{q_chunk}</div></div>"

    return p_html, s_html, sum(1 for r in results if r.get('source') == 'DB')

# --- 7. [100% 동작] 동기형(Sync) DB 자동 축적 엔진 ---
def run_auto_farmer():
    """비동기 충돌을 막기 위해 철저히 동기(Synchronous) 방식으로 DB를 축적합니다."""
    # 동기식 모델 생성
    sync_model = genai.GenerativeModel('models/gemini-2.5-flash')
    
    while True:
        try:
            with DB_LOCK:
                cur_len = len(bank_db)
            if cur_len < 10000:
                sub = random.choice(["수학 I, II", "미적분", "확률과 통계", "기하"])
                score = random.choice([2, 3, 4])
                q_type = random.choice(["객관식", "주관식"])
                
                diff_guide = "[초고난도] 복합 개념 출제" if score == 4 else "[응용 3점]" if score == 3 else "[기초 2점]"
                opt_rule = "options 배열에 5개 필수." if q_type == '객관식' else "options 배열은 비워둘 것."
                
                prompt = f"""과목:{sub} | 배점:{score} | 유형:{q_type}\n[지시사항] 1.{diff_guide} 2.{opt_rule} 3.수식 $ $ 필수.\nJSON 배열 3개 생성: [{{ "question": "...", "options": [...], "solution": "..." }}]"""
                
                # 비동기가 아닌 동기식 호출로 스레드 충돌 완벽 방어
                res = sync_model.generate_content(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.85, response_mime_type="application/json"))
                
                match = re.search(r'\[.*\]', res.text.strip(), re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    with DB_LOCK:
                        for q in data:
                            q.update({"batch_id": str(uuid.uuid4()), "sub": sub, "score": score, "type": q_type})
                            if not bank_db.search(QBank.question == q['question']):
                                bank_db.insert(q)
            
            time.sleep(10) # 10초 휴식 후 반복
        except Exception as e:
            time.sleep(15) # 에러 시 15초 휴식 후 재시작

if 'farmer_running' not in st.session_state:
    threading.Thread(target=run_auto_farmer, daemon=True).start()
    st.session_state.farmer_running = True

# --- 8. UI 및 인증 ---
def send_verification_email(receiver, code):
    try:
        msg = MIMEMultipart(); msg['From'] = SENDER_EMAIL; msg['To'] = receiver; msg['Subject'] = "[인증번호]"
        msg.attach(MIMEText(f"인증번호: [{code}]", 'plain'))
        s = smtplib.SMTP('smtp.gmail.com', 587); s.starttls(); s.login(SENDER_EMAIL, SENDER_PASS); s.send_message(msg); s.quit()
        return True
    except: return False

st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")
if 'verified' not in st.session_state: st.session_state.verified = False

with st.sidebar:
    st.title("🎓 본부 인증")
    email_in = st.text_input("이메일", value=ADMIN_EMAIL if st.session_state.verified else "")
    
    if email_in == ADMIN_EMAIL: 
        st.session_state.verified = True
        st.success("👑 관리자 인증 완료")
        if st.button("🚨 DB 완전 초기화 (과거 오류 문항 삭제)"):
            with DB_LOCK:
                bank_db.truncate()
            st.success("DB가 완벽히 초기화되었습니다! 이제 정상적으로 문제가 채워집니다.")
            st.rerun()

    if not st.session_state.verified:
        if st.button("인증번호 발송"):
            code = str(random.randint(100000, 999999))
            if send_verification_email(email_in, code):
                st.session_state.auth_code, st.session_state.mail_sent = code, True
                st.success("발송 완료!")
        if st.session_state.get('mail_sent'):
            c_in = st.text_input("6자리 입력")
            if st.button("확인"):
                if c_in == st.session_state.auth_code: st.session_state.verified = True; st.rerun()

    if st.session_state.verified:
        st.divider()
        mode = st.radio("모드", ["30문항 풀세트", "맞춤 문항"])
        sub = st.selectbox("선택과목", ["미적분", "확률과 통계", "기하"])
        num = 30 if mode == "30문항 풀세트" else st.slider("문항 수", 2, 30, 4, step=2)
        score = int(st.selectbox("난이도 설정", ["2", "3", "4"])) if mode == "맞춤 문항" else None
        btn = st.button("🚀 발간 시작", use_container_width=True)
        # 자동 파밍 스레드가 작동하며 숫자가 올라가는 것을 볼 수 있습니다.
        with DB_LOCK: st.caption(f"🗄️ DB 축적량: {len(bank_db)} / 10000")

if st.session_state.verified and btn:
    with st.spinner("AI 엔진 가동 중... (안전 필터 해제 완료)"):
        p, s, hits = asyncio.run(run_orchestrator(sub, num, score))
        st.success(f"✅ 발간 완료! (DB 활용: {hits}개)")
        st.components.v1.html(get_html_template(p, s), height=1200, scrolling=True)
