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

# --- 3. [수정됨] 텍스트 정제 엔진 (수식 이중 이스케이프 방지) ---
def polish_output(text):
    if not text: return ""
    text = re.sub(r'^(과목|단원|배점|유형|난이도|수학\s?[I|II|1|2]|Step\s?\d):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'\[.*?점\]\s*', '', text)
    # 8.pdf 오류 원인: \$ 가 화면에 그대로 나오는 현상 방지
    text = text.replace(r'\$', '$') 
    text = text.replace('->', r'\to')
    return text.strip()

def clean_option(text):
    return polish_output(re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)).strip())

# --- 4. [수정됨] 난이도 및 진짜 SVG 가이드 ---
def get_pro_guide(score):
    if score == 2:
        return "[2점 절대 엄수] 무조건 1분 컷 단순 연산(예: 단순 지수/로그, 미분계수). 도형, 그래프, 복합 추론 절대 금지."
    elif score == 3:
        return "[3점 응용] 개념 2개 결합 또는 교과서 유제 수준."
    else:
        return "[4점 킬러] (가), (나) 조건 제시 필수. 케이스 분류 및 복합 추론이 필요한 최고난도."

# --- 5. HTML/CSS (인쇄 최적화) ---
def get_html_template(p_html, s_html):
    return f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
        * {{ font-family: 'Nanum Myeongjo', serif !important; }}
        body {{ background: #e9ecef; padding: 20px; color: #000; display: flex; flex-direction: column; align-items: center; }}
        .paper {{ background: white; width: 210mm; min-height: 297mm; padding: 20mm 18mm; margin-bottom: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.15); }}
        .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 50px; position: relative; }}
        .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: #ddd; }}
        .question-box {{ position: relative; line-height: 2.2; font-size: 11pt; padding-left: 28px; margin-bottom: 45px; text-align: justify; min-height: 120px; }}
        .q-num {{ position: absolute; left: 0; top: 0; font-weight: 800; font-size: 13pt; }}
        .svg-container {{ margin: 15px 0; text-align: center; width: 100%; }}
        .svg-container svg {{ max-width: 100%; max-height: 200px; background: #fff; }}
        .options-container {{ margin-top: 15px; display: flex; flex-wrap: wrap; gap: 5px; }}
        .options-container span {{ flex: 0 0 18%; min-width: 130px; font-size: 10.5pt; white-space: nowrap; }}
        @media print {{ 
            .no-print {{ display: none !important; }} 
            body {{ padding: 0; background: white; }} 
            .paper {{ box-shadow: none; margin: 0; page-break-after: always; }} 
        }}
    </style></head>
    <body>
        <div class="no-print" style="margin-bottom: 20px; text-align: center;">
            <p style="color: #555; font-size: 14px; font-weight: bold;">이 창에서 CTRL+P 또는 CMD+P를 눌러 PDF로 저장하세요.</p>
            <button style="background:#000; color:#fff; padding:10px 20px; border:none; border-radius:5px; cursor:pointer; font-size:16px;" onclick="window.print()">🖨️ 인쇄하기</button>
        </div>
        {p_html}
        <div class="paper"><h2 style="text-align:center; border-bottom:2px solid #000; padding-bottom:10px;">[정답 및 해설]</h2>{s_html}</div>
    </body></html>
    """

# --- 6. AI 생성 엔진 ---
async def generate_batch_ai(q_info, size=2):
    model = genai.GenerativeModel('models/gemini-2.0-flash')
    guide = get_pro_guide(q_info['score'])
    prompt = f"""과목:{q_info['sub']} | 단원:{q_info['topic']} | 배점:{q_info['score']}
[절대 지시사항] 
1. 언어: 한국어. {guide}
2. 도형/그래프 필수 시: 말로 설명하지 말고 무조건 `<svg viewBox="0 0 200 200" ...>` 형태의 완성된 코드를 `svg_draw` 필드에 작성하라.
3. 수식 기호: 반드시 단일 $ 기호만 사용 (예: $x^2+1$). \\$ 사용 금지.
4. JSON {size}개 생성:
[{{ "topic": "{q_info['topic']}", "question": "...", "svg_draw": "<svg...> (없으면 null)", "options": ["선지1",...], "solution": "..." }}]"""
    try:
        res = await model.generate_content_async(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.8, response_mime_type="application/json"))
        data = json.loads(res.text.strip())
        return [{**d, "batch_id": str(uuid.uuid4()), "sub": q_info['sub'], "score": q_info['score'], "type": "객관식"} for d in data]
    except: return []

async def get_safe_q(q_info, used_ids, topic_counts, total_num):
    with DB_LOCK:
        available = bank_db.search((QBank.sub == q_info['sub']) & (QBank.topic == q_info['topic']) & (QBank.score == q_info['score']))
    fresh = [q for q in available if str(q.doc_id) not in used_ids]
    quota = max(2, (total_num // 3))
    
    if fresh and topic_counts.get(q_info['topic'], 0) < quota:
        sel = random.choice(fresh)
        topic_counts[sel['topic']] = topic_counts.get(sel['topic'], 0) + 1
        used_ids.add(str(sel.doc_id))
        return {**sel, "num": q_info['num'], "source": "DB"}
    
    for _ in range(2):
        new_batch = await generate_batch_ai(q_info, size=2)
        if new_batch:
            sel = new_batch[0]
            topic_counts[sel['topic']] = topic_counts.get(sel['topic'], 0) + 1
            return {**sel, "num": q_info['num'], "source": "AI", "full_batch": new_batch}
    
    # 지연 시 Fallback 방어 로직
    return {"num": q_info['num'], "score": q_info['score'], "question": "서버 부하로 예비 문항이 로드되었습니다. $\\log_2 8 + \\log_3 9$ 의 값을 구하시오.", "options": ["3", "4", "5", "6", "7"], "solution": "$\\log_2 2^3 + \\log_3 3^2 = 3 + 2 = 5$ 이므로 정답은 5이다.", "source": "SAFE", "svg_draw": None}

def safe_save_to_bank(batch):
    def _bg_save():
        with DB_LOCK:
            for q in batch:
                if q.get('topic') and q.get('question') and q.get('solution'):
                    if isinstance(q.get('options', []), list) and len(q.get('options', [])) == 5:
                        if not bank_db.search(QBank.question == q["question"]):
                            bank_db.insert(q)
    threading.Thread(target=_bg_save, daemon=True).start()

async def run_orchestrator(sub_choice, num_choice, score_choice=None):
    topics = {"미적분": ["수열의 극한", "미분법", "적분법"], "확률과 통계": ["경우의 수", "확률", "통계"], "기하": ["이차곡선", "평면벡터", "공간도형"]}[sub_choice]
    
    blueprint = []
    if num_choice == 30:
        m1 = ["지수함수와 로그함수", "삼각함수", "수열"]
        m2 = ["함수의 극한과 연속", "다항함수의 미분법", "다항함수의 적분법"]
        for i in range(1, 16):
            s = "수학 I" if i % 2 != 0 else "수학 II"
            blueprint.append({"num": i, "sub": s, "topic": m1[(i//2)%3] if s=="수학 I" else m2[(i//2)%3], "score": 2 if i<=3 else 4 if i>8 else 3})
        for i in range(16, 23):
            s = "수학 II" if i % 2 == 0 else "수학 I"
            blueprint.append({"num": i, "sub": s, "topic": m2[i%3] if s=="수학 II" else m1[i%3], "score": 4 if i>20 else 3})
        for i in range(23, 31):
            blueprint.append({"num": i, "sub": sub_choice, "topic": topics[(i-23)%3], "score": 2 if i==23 else 4 if i>27 else 3})
    else:
        blueprint = [{"num": i+1, "sub": sub_choice, "topic": topics[i % 3], "score": score_choice or 3} for i in range(num_choice)]
    
    used_ids, topic_counts, results = set(), {}, []
    prog, status = st.progress(0), st.empty()
    
    for q_info in blueprint:
        status.text(f"⏳ {q_info['num']}번 조판 및 SVG 렌더링 중...")
        res = await get_safe_q(q_info, used_ids, topic_counts, num_choice)
        results.append(res)
        if res.get('source') == "AI" and "full_batch" in res:
            safe_save_to_bank(res['full_batch'])
        prog.progress(q_info['num'] / num_choice)
    
    p_html, s_html = "", ""
    q_html_list = []
    for item in results:
        num, score, q_text = item['num'], item['score'], polish_output(item['question'])
        svg = f"<div class='svg-container'>{item['svg_draw']}</div>" if item.get('svg_draw') else ""
        opts = "".join([f"<span>{chr(9312+j)} {clean_option(str(o))}</span>" for j, o in enumerate(item.get('options', []))])
        q_html_list.append(f"<div class='question-box'><span class='q-num'>{num}</span> {q_text} <b>[{score}점]</b>{svg}<div class='options-container'>{opts}</div></div>")
        s_html += f"<div style='margin-bottom:15px; padding-bottom:10px; border-bottom:1px dashed #ccc;'><b>{num}번:</b> {polish_output(item.get('solution'))}</div>"

    for i in range(0, len(q_html_list), 2):
        chunk = "".join(q_html_list[i:i+2])
        p_html += f"<div class='paper'><div style='text-align:center; border-bottom:3px solid #000; margin-bottom:20px; padding-bottom:10px;'><h1>2026 수능 모의평가</h1></div><div class='question-grid'>{chunk}</div></div>"
    
    return get_html_template(p_html, s_html), sum(1 for r in results if r.get('source') == "DB")

# --- 7. [수정됨] 백그라운드 파밍 메모리 누수 방지 로직 ---
def run_auto_farmer():
    sync_model = genai.GenerativeModel('models/gemini-2.0-flash')
    while True:
        try:
            with DB_LOCK: cur_len = len(bank_db)
            if cur_len < 10000:
                sub = random.choice(["미적분", "확률과 통계", "기하", "수학 I", "수학 II"])
                score = random.choice([2, 3, 4])
                prompt = f"과목:{sub} | 배점:{score} | [지시] 기준 문항 1개와 변형 3개를 JSON으로 생성. 수식 $$, 도형 필요시 <svg> 직접 작성 필수."
                res = sync_model.generate_content(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.9, response_mime_type="application/json"))
                data = json.loads(res.text.strip())
                with DB_LOCK:
                    for q in data:
                        q.update({"batch_id": str(uuid.uuid4()), "sub": sub, "score": score, "type": "객관식"})
                        if q.get('topic') and q.get('question'): bank_db.insert(q)
            time.sleep(20) # 부하 조절을 위해 인터벌 증가
        except: time.sleep(30)

@st.cache_resource
def start_global_farmer():
    thread = threading.Thread(target=run_auto_farmer, daemon=True)
    thread.start()
    return thread

# 앱 기동 시 서버 전체에서 단 1개의 스레드만 실행됨
start_global_farmer()

# --- 8. UI 및 관리자 메뉴 ---
st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")
if 'verified' not in st.session_state: st.session_state.verified, st.session_state.user_email = False, ""

with st.sidebar:
    st.title("🎓 본부 제어실")
    if not st.session_state.verified:
        email_in = st.text_input("접속 이메일 입력")
        if email_in == ADMIN_EMAIL and st.button("관리자 로그인"):
            st.session_state.verified, st.session_state.user_email = True, ADMIN_EMAIL; st.rerun()
        elif email_in and st.button("사용자 접속"):
            st.session_state.verified, st.session_state.user_email = True, email_in; st.rerun()
    else:
        st.success(f"✅ {st.session_state.user_email} 님 접속 중")
        if st.button("🚪 로그아웃"): st.session_state.verified = False; st.rerun()
        
        if st.session_state.user_email == ADMIN_EMAIL:
            st.warning("👑 시스템 관리")
            if 'confirm_reset' not in st.session_state: st.session_state.confirm_reset = False
            
            if not st.session_state.confirm_reset:
                if st.button("🚨 전체 DB 강제 초기화"): st.session_state.confirm_reset = True; st.rerun()
            else:
                st.error("⚠️ 정말로 모든 문제를 삭제하시겠습니까?")
                if st.button("✔️ 삭제 승인", type="primary"):
                    with DB_LOCK: bank_db.truncate()
                    st.session_state.confirm_reset = False; st.rerun()
                if st.button("❌ 취소"): st.session_state.confirm_reset = False; st.rerun()

        st.divider()
        mode = st.radio("모드", ["30문항 풀세트", "맞춤 문항"])
        sub_choice = st.selectbox("선택과목", ["미적분", "확률과 통계", "기하"])
        
        if mode == "맞춤 문항":
            num_choice = st.slider("문항 수", 2, 20, 4, step=2)
            score_val = int(st.selectbox("배점 설정", ["2", "3", "4"]))
        else:
            num_choice = 30
            score_val = None
            
        btn = st.button("🚀 프리미엄 발간 시작", use_container_width=True)
        with DB_LOCK: st.caption(f"🗄️ 백그라운드 DB 비축량: {len(bank_db)} / 10000")

# --- 9. [수정됨] Iframe 인쇄 잘림 방지 (다운로드 버튼 제공) ---
if st.session_state.verified and btn:
    with st.spinner("AI가 SVG 도면을 렌더링하고 수능 규격에 맞춰 조판 중입니다..."):
        try:
            html_out, db_hits = asyncio.run(run_orchestrator(sub_choice, num_choice, score_val))
            st.success(f"✅ 발간 완료! (DB 추출: {db_hits}개 / AI 신규 생성: {num_choice - db_hits}개)")
            
            # 1. 완벽한 인쇄를 위한 HTML 직접 다운로드 버튼
            st.download_button(
                label="📥 깔끔한 인쇄용 파일 다운로드 (다운 후 더블클릭하여 인쇄하세요)",
                data=html_out,
                file_name=f"2026_수능모의평가_{sub_choice}.html",
                mime="text/html",
                type="primary",
                use_container_width=True
            )
            
            st.info("👇 아래는 미리보기 화면입니다. 완벽한 A4 출력을 원하시면 위의 다운로드 버튼을 이용해 주세요.")
            
            # 2. 웹상에서의 미리보기 화면 (스크롤 제공)
            st.components.v1.html(html_out, height=800, scrolling=True)
            
        except Exception as e: 
            st.error(f"❌ 발간 중 오류가 발생했습니다: {e}")


