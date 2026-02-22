import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
import asyncio
import random
import json
import time
import threading
import re
import uuid
import os

# --- 1. 환경 설정 및 철통 보안 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("PAID_API_KEY 설정이 필요합니다!")
    st.stop()

SAFETY_SETTINGS = [{"category": f"HARM_CATEGORY_{c}", "threshold": "BLOCK_NONE"} for c in ["HARASSMENT", "HATE_SPEECH", "SEXUALLY_EXPLICIT", "DANGEROUS_CONTENT"]]
ADMIN_EMAIL = "pgh001002@gmail.com"

# --- 2. DB 및 자가 치유 로직 ---
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

# --- 3. 텍스트 정제 엔진 (수식 보호) ---
def polish_output(text):
    if not text: return ""
    text = re.sub(r'^(과목|단원|배점|유형|난이도|수학\s?[I|II|1|2]|Step\s?\d):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'\[.*?점\]\s*', '', text)
    math_tokens = ['sin', 'cos', 'tan', 'log', 'ln', 'lim', 'exp', 'sqrt', 'vec', 'cdot', 'frac', 'theta', 'pi', 'infty', 'to', 'sum', 'int', 'alpha', 'beta', 'mu', 'sigma', 'lambda']
    for token in math_tokens:
        text = re.sub(rf'(?<!\\)\b{token}\b', rf'\\{token}', text)
    return text.replace('->', r'\to').strip()

def clean_option(text):
    return polish_output(re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)).strip())

# --- 4. [핵심] 난이도 및 SVG 가이드 ---
def get_pro_guide(score):
    if score == 2:
        return """[최우선: 2점 난이도 절대 엄수]
- 반드시 '1분 이내' 단순 연산형 (예: 지수/로그 기본 성질, 단순 미분/적분 대입).
- 복잡한 도형이나 추론 절대 금지. 위반 시 시스템 오류로 간주됨."""
    elif score == 3:
        return "[3점 응용] 개념 2개 결합 또는 교과서 예제 변형 수준."
    else:
        return "[4점 킬러] (가), (나) 조건 필수. 복합 추론 및 케이스 분류 필수."

# --- 5. HTML/CSS (선지 5열 정렬 및 SVG 최적화) ---
def get_html_template(p_html, s_html):
    return f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
        * {{ font-family: 'Nanum Myeongjo', serif !important; }}
        body {{ background: #f0f2f6; padding: 20px; color: #000; }}
        .paper {{ background: white; width: 210mm; min-height: 297mm; padding: 20mm 18mm; margin: 0 auto 30px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); position: relative; }}
        .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 50px; position: relative; }}
        .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: #eee; }}
        .question-box {{ position: relative; line-height: 2.3; font-size: 11pt; padding-left: 28px; margin-bottom: 45px; text-align: justify; min-height: 150px; }}
        .q-num {{ position: absolute; left: 0; top: 0; font-weight: 800; font-size: 13pt; }}
        .svg-container {{ margin: 15px 0; text-align: center; background: #fff; border: 1px solid #f0f0f0; padding: 5px; }}
        .options-container {{ margin-top: 15px; display: flex; flex-wrap: wrap; gap: 5px; }}
        .options-container span {{ flex: 0 0 18%; min-width: 140px; font-size: 10.5pt; white-space: nowrap; overflow: hidden; }}
        @media print {{ .no-print {{ display: none; }} body {{ padding: 0; }} .paper {{ box-shadow: none; margin: 0; }} }}
    </style></head>
    <body>
        <div class="no-print" style="text-align:center; margin-bottom:20px;">
            <button style="background:#2e7d32; color:white; padding:12px 24px; border:none; border-radius:5px; cursor:pointer; font-weight:bold;" onclick="window.print()">🖨️ PDF 다운로드 / 인쇄</button>
        </div>
        <div class="paper-container">{p_html}<div class="paper"><h2 style="text-align:center;">[정답 및 해설]</h2>{s_html}</div></div>
    </body></html>
    """

# --- 6. 생성 및 오케스트레이터 ---
async def generate_batch_ai(q_info, size=2):
    model = genai.GenerativeModel('models/gemini-2.0-flash')
    guide = get_pro_guide(q_info['score'])
    prompt = f"""과목:{q_info['sub']} | 단원:{q_info['topic']} | 배점:{q_info['score']}
[필수] 1.한국어 2.{guide} 3.그림필요시 <svg> 태그로 직접 작성해 svg_draw 필드에 주입(묘사 금지, 직접 그릴 것) 4.수식 $$ 필수 5.JSON {size}개 생성:
[{{ "topic": "{q_info['topic']}", "question": "...", "svg_draw": "<svg...> (없으면 null)", "options": ["선지1",...], "solution": "..." }}]"""
    try:
        res = await model.generate_content_async(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.8, response_mime_type="application/json"))
        data = json.loads(res.text.strip())
        return [{**d, "batch_id": str(uuid.uuid4()), "sub": q_info['sub'], "score": q_info['score'], "type": "객관식"} for d in data]
    except: return []

async def get_safe_q(q_info, used_ids, topic_counts, total_num):
    # 1. DB 검색 (단원별 쿼터제)
    with DB_LOCK:
        available = bank_db.search((QBank.sub == q_info['sub']) & (QBank.topic == q_info['topic']) & (QBank.score == q_info['score']))
    fresh = [q for q in available if str(q.doc_id) not in used_ids]
    quota = max(2, (total_num // 3))
    
    if fresh and topic_counts.get(q_info['topic'], 0) < quota:
        sel = random.choice(fresh)
        topic_counts[sel['topic']] = topic_counts.get(sel['topic'], 0) + 1
        used_ids.add(str(sel.doc_id))
        return {**sel, "num": q_info['num'], "source": "DB"}
    
    # 2. AI 생성 (재시도 및 Fallback)
    for _ in range(2):
        new_batch = await generate_batch_ai(q_info, size=2)
        if new_batch:
            sel = new_batch[0]
            topic_counts[sel['topic']] = topic_counts.get(sel['topic'], 0) + 1
            return {**sel, "num": q_info['num'], "source": "AI", "full_batch": new_batch}
    
    # 3. 비상 데이터 (지연 방어)
    return {"num": q_info['num'], "score": q_info['score'], "question": "시스템 부하로 인해 예비 문항이 로딩되었습니다. (로그 $2^3 + 2^2$ 의 값을 구하시오.)", "options": ["10", "11", "12", "13", "14"], "solution": "12", "source": "SAFE", "svg_draw": None}

async def run_orchestrator(sub_choice, num_choice, score_choice=None):
    topics = {"미적분": ["수열의 극한", "미분법", "적분법"], "확률과 통계": ["경우의 수", "확률", "통계"], "기하": ["이차곡선", "평면벡터", "공간도형"]}[sub_choice]
    blueprint = [{"num": i+1, "sub": sub_choice, "topic": topics[i % 3], "score": score_choice or 3} for i in range(num_choice)]
    
    used_ids, topic_counts, results = set(), {}, []
    prog, status = st.progress(0), st.empty()
    
    for q_info in blueprint:
        status.text(f"⏳ {q_info['num']}번 조판 및 SVG 도면 실시간 렌더링 중...")
        res = await get_safe_q(q_info, used_ids, topic_counts, num_choice)
        results.append(res)
        if res.get('source') == "AI" and "full_batch" in res:
            safe_save_to_bank(res['full_batch'], "객관식")
        prog.progress(q_info['num'] / num_choice)
    
    p_html, s_html = "", ""
    q_html_list = []
    for item in results:
        num, score, q_text = item['num'], item['score'], polish_output(item['question'])
        svg = f"<div class='svg-container'>{item['svg_draw']}</div>" if item.get('svg_draw') else ""
        opts = "".join([f"<span>{chr(9312+j)} {clean_option(str(o))}</span>" for j, o in enumerate(item.get('options', []))])
        q_html_list.append(f"<div class='question-box'><span class='q-num'>{num}</span> {q_text} <b>[{score}점]</b>{svg}<div class='options-container'>{opts}</div></div>")
        s_html += f"<div style='margin-bottom:15px;'><b>{num}번:</b> {polish_output(item.get('solution'))}</div>"

    for i in range(0, len(q_html_list), 2):
        chunk = "".join(q_html_list[i:i+2])
        p_html += f"<div class='paper'><div class='header' style='text-align:center; border-bottom:2.5px solid #000; margin-bottom:25px;'><h1>2026 수능 모의평가</h1></div><div class='question-grid'>{chunk}</div></div>"
    
    return get_html_template(p_html, s_html), sum(1 for r in results if r.get('source') == "DB")

# --- 7. [부활] 백그라운드 파밍 (Seed & Variant) ---
def run_auto_farmer():
    sync_model = genai.GenerativeModel('models/gemini-2.0-flash')
    while True:
        try:
            with DB_LOCK: cur_len = len(bank_db)
            if cur_len < 10000:
                sub = random.choice(["미적분", "확률과 통계", "기하"])
                score = random.choice([2, 3, 4])
                prompt = f"과목:{sub} | 배점:{score} | [지시] 기준 문항 1개와 변형 3개를 JSON으로 생성. 수식 $$, 그림 <svg> 필수."
                res = sync_model.generate_content(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.9, response_mime_type="application/json"))
                data = json.loads(res.text.strip())
                with DB_LOCK:
                    for q in data:
                        q.update({"batch_id": str(uuid.uuid4()), "sub": sub, "score": score, "type": "객관식"})
                        bank_db.insert(q)
            time.sleep(15) 
        except: time.sleep(20)

if 'farmer_running' not in st.session_state:
    threading.Thread(target=run_auto_farmer, daemon=True).start()
    st.session_state.farmer_running = True

# --- 8. UI 및 관리자 메뉴 ---
st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")
if 'verified' not in st.session_state: st.session_state.verified, st.session_state.user_email = False, ""

with st.sidebar:
    st.title("🎓 본부 제어실")
    if not st.session_state.verified:
        email_in = st.text_input("이메일 입력")
        if email_in == ADMIN_EMAIL and st.button("관리자 로그인"):
            st.session_state.verified, st.session_state.user_email = True, ADMIN_EMAIL; st.rerun()
        elif email_in and st.button("사용자 접속"):
            st.session_state.verified, st.session_state.user_email = True, email_in; st.rerun()
    else:
        st.success(f"✅ {st.session_state.user_email} 인증됨")
        if st.button("🚪 로그아웃"): st.session_state.verified = False; st.rerun()
        if st.session_state.user_email == ADMIN_EMAIL:
            st.warning("👑 관리자 권한")
            if st.button("🚨 전체 DB 초기화"): st.session_state.confirm = True
            if st.session_state.get('confirm'):
                if st.button("✔️ 삭제 승인"):
                    with DB_LOCK: bank_db.truncate(); st.session_state.confirm = False; st.rerun()
                if st.button("❌ 취소"): st.session_state.confirm = False; st.rerun()

        st.divider()
        mode = st.radio("모드", ["30문항 풀세트", "맞춤 문항"])
        sub_choice = st.selectbox("과목", ["미적분", "확률과 통계", "기하"])
        num_choice = st.slider("문항 수", 2, 20, 4, step=2)
        score_val = int(st.selectbox("배점 (맞춤 모드)", ["2", "3", "4"])) if mode == "맞춤 문항" else None
        btn = st.button("🚀 프리미엄 발간 시작", use_container_width=True)
        with DB_LOCK: st.caption(f"🗄️ 무결점 DB: {len(bank_db)} / 10000")

if st.session_state.verified and btn:
    with st.spinner("AI가 SVG 도면을 설계하고 수능 규격에 맞춰 조판 중..."):
        try:
            html, db_hits = asyncio.run(run_orchestrator(sub_choice, num_choice, score_val))
            st.success(f"✅ 발간 완료! (DB 활용: {db_hits}개)")
            st.components.v1.html(html, height=1200, scrolling=True)
        except Exception as e: st.error(f"❌ 오류 발생: {e}")


