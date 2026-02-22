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

# --- 1. 환경 설정 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("PAID_API_KEY 설정이 필요합니다!")
    st.stop()

SAFETY_SETTINGS = [{"category": f"HARM_CATEGORY_{c}", "threshold": "BLOCK_NONE"} for c in ["HARASSMENT", "HATE_SPEECH", "SEXUALLY_EXPLICIT", "DANGEROUS_CONTENT"]]
ADMIN_EMAIL = "pgh001002@gmail.com"

# --- 2. DB 로직 ---
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

# --- 3. 텍스트 정제 엔진 ---
def polish_output(text):
    if not text: return ""
    text = str(text)
    text = re.sub(r'^(과목|단원|배점|유형|난이도|수학\s?[I|II|1|2]|Step\s?\d):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'\[.*?점\]\s*', '', text)
    text = text.replace('Mn', r'\ln').replace(r'\$', '$').replace('->', r'\to')
    text = re.sub(r'sqrt\((.*?)\)', r'\\sqrt{\1}', text)
    text = re.sub(r'(?<!\\)mathcal\{S\}', r'\\int', text)
    text = re.sub(r'\bS_\{', r'\\int_{', text)
    math_tokens = ['sin', 'cos', 'tan', 'log', 'ln', 'lim', 'exp', 'vec', 'cdot', 'frac', 'theta', 'pi', 'infty', 'to', 'sum', 'int', 'alpha', 'beta', 'mu', 'sigma']
    for token in math_tokens:
        text = re.sub(rf'(?<!\\)\b{token}\b', rf'\\{token}', text)
    return text.strip()

def clean_option(text):
    return polish_output(re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)).strip())

def get_pro_guide(sub, score):
    if score == 2: return f"[2점] 무조건 1분 컷 단순 연산. 복잡한 도형/그래프 절대 금지."
    elif score == 3: return f"[3점] 개념 2개 결합 응용. 교과서 수준."
    else: return f"[4점 킬러] (가), (나) 조건 활용. 케이스 분류 필수. 최고난도."

# --- 4. HTML 템플릿 ---
def get_html_template(p_html, s_html):
    return f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$']], displayMath: [['$$', '$$']] }} }};</script>
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js" id="MathJax-script" async></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
        * {{ font-family: 'Nanum Myeongjo', serif !important; }}
        body {{ background: #e9ecef; padding: 20px; color: #000; display: flex; flex-direction: column; align-items: center; }}
        .paper {{ background: white; width: 210mm; min-height: 297mm; padding: 20mm 18mm; margin-bottom: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.15); page-break-after: always; }}
        .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 50px; position: relative; }}
        .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: #ddd; }}
        .question-box {{ position: relative; line-height: 2.2; font-size: 11pt; padding-left: 28px; margin-bottom: 45px; text-align: justify; min-height: 120px; }}
        .q-num {{ position: absolute; left: 0; top: 0; font-weight: 800; font-size: 13pt; }}
        .svg-container {{ margin: 15px 0; text-align: center; width: 100%; }}
        .svg-container svg {{ max-width: 100%; max-height: 200px; background: #fff; }}
        .options-container {{ margin-top: 15px; display: flex; flex-wrap: wrap; gap: 5px; }}
        .options-container span {{ flex: 0 0 18%; min-width: 130px; font-size: 10.5pt; white-space: nowrap; overflow: hidden; }}
        @media print {{ .no-print {{ display: none !important; }} body {{ padding: 0; background: white; }} .paper {{ box-shadow: none; margin: 0; }} }}
    </style></head>
    <body>
        <div class="no-print" style="margin-bottom: 20px;"><button style="background:#000; color:#fff; padding:10px 20px; border:none; cursor:pointer; font-weight:bold;" onclick="window.print()">🖨️ 인쇄하기 (Ctrl+P)</button></div>
        {p_html}
        <div class="paper"><h2 style="text-align:center; border-bottom:2px solid #000; padding-bottom:10px;">[정답 및 해설]</h2>{s_html}</div>
    </body></html>
    """

# --- 5. [수정] AI 생성 엔진 (객/주관식 완벽 분리) ---
async def generate_batch_ai(q_info, size=2):
    model = genai.GenerativeModel('models/gemini-2.0-flash')
    guide = get_pro_guide(q_info['sub'], q_info['score'])
    
    # 객관식/주관식 지시사항 분기
    if q_info['type'] == '주관식':
        type_instruction = "이 문항은 [주관식(단답형)]입니다. options 배열은 반드시 빈 배열 [] 로 비워두고, 최종 정답은 무조건 3자리 이하의 자연수가 나오도록 문제를 설계하세요."
    else:
        type_instruction = "이 문항은 [객관식]입니다. options 배열에 매력적인 오답을 포함한 5개의 선지를 작성하세요."

    prompt = f"""과목:{q_info['sub']} | 단원:{q_info['topic']} | 배점:{q_info['score']} | 유형:{q_info['type']}
[지시사항] 
1. {guide}
2. {type_instruction}
3. 적분은 `\\int`, 로그는 `\\ln` 등 완벽한 LaTeX 사용. 백슬래시 두 번(`\\\\`) 필수.
4. 오직 [{{"topic": "{q_info['topic']}", "question": "...", "svg_draw": null, "options": ["①",...], "solution": "..."}}] 배열만 출력."""
    try:
        res = await model.generate_content_async(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.85))
        match = re.search(r'\[.*\]', res.text.strip(), re.DOTALL)
        if not match: return []
        data = json.loads(match.group(0))
        return [{**d, "batch_id": str(uuid.uuid4()), "sub": q_info['sub'], "score": q_info['score'], "type": q_info['type']} for d in data]
    except: return []

# --- 6. [수정] 예비 문항 뱅크 (객/주관식 분리 탑재) ---
FALLBACK_BANK = {
    # 수학 I (객관식)
    ("수학 I", 3, "객관식"): [
        {"question": "$\\sin \\theta = \\frac{1}{2}$ 이고 $\\frac{\\pi}{2} < \\theta < \\pi$ 일 때, $\\cos \\theta$ 의 값은?", "options": ["$-\\frac{\\sqrt{3}}{2}$", "$-\\frac{1}{2}$", "0", "$\\frac{1}{2}$", "$\\frac{\\sqrt{3}}{2}$"], "solution": "$-\\frac{\\sqrt{3}}{2}$"}
    ],
    # 수학 I (주관식)
    ("수학 I", 3, "주관식"): [
        {"question": "등차수열 $\\{a_n\\}$ 에 대하여 $a_2 = 5, a_5 = 14$ 일 때, $a_{10}$ 의 값을 구하시오.", "options": [], "solution": "공차 $d=3$. $a_{10} = 14 + 15 = 29$ 이다."}
    ],
    ("수학 I", 4, "주관식"): [
        {"question": "수열 $\\{a_n\\}$ 이 $a_1 = 1$ 이고, $a_{n+1} = a_n + n^2$ 일 때, $a_6$ 의 값을 구하시오.", "options": [], "solution": "$1 + 1^2 + 2^2 + 3^2 + 4^2 + 5^2 = 56$"}
    ],
    # 수학 II (주관식)
    ("수학 II", 3, "주관식"): [
        {"question": "함수 $f(x) = x^3 - 3x^2 + 5$ 의 극댓값을 구하시오.", "options": [], "solution": "$f'(x)=3x^2-6x=0$ 에서 $x=0$일 때 극댓값 $5$를 갖는다."}
    ],
    ("수학 II", 4, "주관식"): [
        {"question": "최고차항의 계수가 1인 삼차함수 $f(x)$가 $f'(1)=0, f'(3)=0$ 을 만족시킨다. $f(3)=2$ 일 때, $f(1)$ 의 값을 구하시오.", "options": [], "solution": "극댓값과 극솟값의 차이 공식을 이용하면 $f(1) - f(3) = \\frac{1}{2}|1| (3-1)^3 = 4$. 따라서 $f(1) = 6$ 이다."}
    ],
    # 미적분 (주관식)
    ("미적분", 3, "주관식"): [
        {"question": "$\\lim_{x \\to 0} \\frac{e^{5x}-1}{x}$ 의 값을 구하시오.", "options": [], "solution": "5"}
    ],
    ("미적분", 4, "주관식"): [
        {"question": "함수 $f(x) = e^x \\sin x$ 에 대하여 $f'(\\frac{\\pi}{2})$ 의 값을 $a e^{\\pi/2}$ 라 할 때, $a$ 의 값을 구하시오.", "options": [], "solution": "$f'(x) = e^x(\\sin x + \\cos x)$ 이므로 $f'(\\frac{\\pi}{2}) = e^{\\pi/2}$. 따라서 $a=1$."}
    ],
    # 확통, 기하 기본 예비(주관식)
    ("확률과 통계", 4, "주관식"): [{"question": "5명의 학생이 원탁에 둘러앉는 경우의 수를 구하시오.", "options": [], "solution": "24"}],
    ("기하", 4, "주관식"): [{"question": "두 벡터 $\\vec{a}=(3, 4), \\vec{b}=(4, 3)$ 에 대하여 $\\vec{a} \\cdot \\vec{b}$ 의 값을 구하시오.", "options": [], "solution": "12+12 = 24"}],
}

def get_fallback(sub, score, q_type, used_fallbacks):
    # 과목, 배점, 유형(객/주관식)까지 완벽히 일치하는 예비 문항 호출
    pool = FALLBACK_BANK.get((sub, score, q_type), [])
    
    # 매칭되는 게 없으면 같은 과목의 3점 해당 유형으로 대체
    if not pool:
        pool = FALLBACK_BANK.get((sub, 3, q_type), [{"question": f"시스템 지연으로 예비 문항이 로드되었습니다. 정답은 10입니다.", "options": [] if q_type == '주관식' else ["1","2","3","4","5"], "solution": "10"}])
        
    available_qs = [q for q in pool if q['question'] not in used_fallbacks]
    if not available_qs:
        available_qs = pool
        used_fallbacks.clear()
        
    selected = random.choice(available_qs)
    used_fallbacks.add(selected['question'])
    return selected

async def get_safe_q(q_info, used_ids, total_num, used_fallbacks):
    with DB_LOCK:
        available = bank_db.search((QBank.sub == q_info['sub']) & (QBank.topic == q_info['topic']) & (QBank.score == q_info['score']) & (QBank.type == q_info['type']))
    fresh = [q for q in available if str(q.doc_id) not in used_ids]
    
    if fresh:
        sel = random.choice(fresh)
        used_ids.add(str(sel.doc_id))
        return {**sel, "num": q_info['num'], "source": "DB"}
    
    for _ in range(2):
        new_batch = await generate_batch_ai(q_info, size=2)
        if new_batch:
            sel = new_batch[0]
            return {**sel, "num": q_info['num'], "source": "AI", "full_batch": new_batch}
    
    fallback_data = get_fallback(q_info['sub'], q_info['score'], q_info['type'], used_fallbacks)
    return {"num": q_info['num'], "score": q_info['score'], "type": q_info['type'], "question": fallback_data['question'], "options": fallback_data.get('options', []), "solution": fallback_data['solution'], "source": "SAFE", "svg_draw": None}

def safe_save_to_bank(batch):
    def _bg_save():
        with DB_LOCK:
            for q in batch:
                if q.get('topic') and q.get('question') and q.get('solution'):
                    if not bank_db.search(QBank.question == q["question"]):
                        bank_db.insert(q)
    threading.Thread(target=_bg_save, daemon=True).start()

# --- 7. 수능 배점 및 주관식 배치 블루프린트 ---
def get_csat_format(i, is_choice_sub=False):
    # 반환값: (배점, 유형)
    if not is_choice_sub: # 공통 1~22
        q_type = "주관식" if 16 <= i <= 22 else "객관식"
        if i in [1, 2, 3]: score = 2
        elif i in [4, 5, 6, 7, 8, 16, 17, 18, 19]: score = 3
        else: score = 4 
        return score, q_type
    else: # 선택 23~30
        q_type = "주관식" if 29 <= i <= 30 else "객관식"
        if i == 23: score = 2
        elif i in [24, 25, 26, 27]: score = 3
        else: score = 4 
        return score, q_type

async def run_orchestrator(sub_choice, num_choice, score_choice=None):
    topics_map = {
        "수학 I": ["지수함수와 로그함수", "삼각함수", "수열"],
        "수학 II": ["함수의 극한과 연속", "다항함수의 미분법", "다항함수의 적분법"],
        "미적분": ["수열의 극한", "미분법", "적분법"],
        "확률과 통계": ["경우의 수", "확률", "통계"],
        "기하": ["이차곡선", "평면벡터", "공간도형"]
    }
    
    blueprint = []
    if num_choice == 30:
        for i in range(1, 16):
            s = "수학 I" if i % 2 != 0 else "수학 II"
            score, q_type = get_csat_format(i, False)
            blueprint.append({"num": i, "sub": s, "topic": topics_map[s][(i//2)%3], "score": score, "type": q_type})
        for i in range(16, 23):
            s = "수학 II" if i % 2 == 0 else "수학 I"
            score, q_type = get_csat_format(i, False)
            blueprint.append({"num": i, "sub": s, "topic": topics_map[s][i%3], "score": score, "type": q_type})
        for i in range(23, 31):
            score, q_type = get_csat_format(i, True)
            blueprint.append({"num": i, "sub": sub_choice, "topic": topics_map[sub_choice][(i-23)%3], "score": score, "type": q_type})
    else:
        t_list = topics_map[sub_choice]
        blueprint = [{"num": i+1, "sub": sub_choice, "topic": t_list[i % len(t_list)], "score": score_choice or 3, "type": "객관식"} for i in range(num_choice)]
    
    used_ids, used_fallbacks, results = set(), set(), []
    prog, status = st.progress(0), st.empty()
    
    for q_info in blueprint:
        status.text(f"⏳ {q_info['num']}번 조판 중... ({q_info['type']})")
        res = await get_safe_q(q_info, used_ids, num_choice, used_fallbacks)
        results.append(res)
        if res.get('source') == "AI" and "full_batch" in res:
            safe_save_to_bank(res['full_batch'])
        prog.progress(q_info['num'] / num_choice)
    
    p_html, s_html = "", ""
    q_html_list = []
    for item in results:
        num, score, q_type = item['num'], item['score'], item.get('type', '객관식')
        q_text = polish_output(item['question'])
        svg = f"<div class='svg-container'>{item['svg_draw']}</div>" if item.get('svg_draw') else ""
        
        # [핵심] 주관식일 경우 선지 렌더링 생략
        opts = ""
        if q_type == '객관식' and isinstance(item.get('options'), list):
            opts = "".join([f"<span>{chr(9312+j)} {clean_option(str(o))}</span>" for j, o in enumerate(item.get('options', [])[:5])])
            opts = f"<div class='options-container'>{opts}</div>"
        
        q_html_list.append(f"<div class='question-box'><span class='q-num'>{num}</span> {q_text} <b>[{score}점]</b>{svg}{opts}</div>")
        s_html += f"<div style='margin-bottom:15px; padding-bottom:10px; border-bottom:1px dashed #ccc;'><b>{num}번:</b> {polish_output(item.get('solution'))}</div>"

    for i in range(0, len(q_html_list), 2):
        chunk = "".join(q_html_list[i:i+2])
        p_html += f"<div class='paper'><div style='text-align:center; border-bottom:3px solid #000; margin-bottom:20px; padding-bottom:10px;'><h1>2026 수능 모의평가</h1></div><div class='question-grid'>{chunk}</div></div>"
    
    return get_html_template(p_html, s_html), sum(1 for r in results if r.get('source') == "DB")

# --- 8. 파밍 엔진 (객/주관식 섞어서 농사) ---
def run_auto_farmer():
    sync_model = genai.GenerativeModel('models/gemini-2.0-flash')
    subjects_order = ["수학 I", "수학 II", "미적분", "확률과 통계", "기하"]
    topics_map = {
        "수학 I": ["지수함수와 로그함수", "삼각함수", "수열"],
        "수학 II": ["함수의 극한과 연속", "다항함수의 미분법", "다항함수의 적분법"],
        "미적분": ["수열의 극한", "미분법", "적분법"],
        "확률과 통계": ["경우의 수", "확률", "통계"],
        "기하": ["이차곡선", "평면벡터", "공간도형"]
    }
    subj_idx = 0
    topic_idxs = {s: 0 for s in subjects_order}
    
    while True:
        try:
            with DB_LOCK: cur_len = len(bank_db)
            if cur_len < 10000:
                sub = subjects_order[subj_idx]
                t_idx = topic_idxs[sub]
                topic = topics_map[sub][t_idx]
                score = random.choices([2, 3, 4], weights=[13, 43, 44], k=1)[0]
                q_type = random.choices(["객관식", "주관식"], weights=[70, 30], k=1)[0]
                
                type_instr = "객관식(options 5개 작성)" if q_type == "객관식" else "주관식(단답형, options 빈 배열 [], 정답은 자연수)"
                prompt = f"과목:{sub} | 단원:{topic} | 배점:{score} | 유형:{q_type}\n[지시] {type_instr}. LaTeX 백슬래시는 두 번(\\\\) 작성. JSON 1개 생성."
                
                res = sync_model.generate_content(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.85))
                match = re.search(r'\[.*\]', res.text.strip(), re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    with DB_LOCK:
                        for q in data:
                            q.update({"batch_id": str(uuid.uuid4()), "sub": sub, "topic": topic, "score": score, "type": q_type})
                            if q.get('question'): bank_db.insert(q)
                
                topic_idxs[sub] = (t_idx + 1) % len(topics_map[sub])
                subj_idx = (subj_idx + 1) % len(subjects_order)
            time.sleep(20)
        except: time.sleep(30)

@st.cache_resource
def start_global_farmer():
    thread = threading.Thread(target=run_auto_farmer, daemon=True)
    thread.start()
    return thread

start_global_farmer()

# --- 9. UI 및 관리자 메뉴 ---
st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")
if 'verified' not in st.session_state: st.session_state.verified, st.session_state.user_email = False, ""

with st.sidebar:
    st.title("🎓 본부 제어실")
    if not st.session_state.verified:
        email_in = st.text_input("접속 이메일 입력")
        if email_in == ADMIN_EMAIL and st.button("관리자 로그인"):
            st.session_state.verified, st.session_state.user_email = True, ADMIN_EMAIL; st.rerun()
    else:
        st.success(f"✅ {st.session_state.user_email} 님 접속 중")
        if st.button("🚪 로그아웃"): st.session_state.verified = False; st.rerun()
        
        if st.session_state.user_email == ADMIN_EMAIL:
            st.warning("👑 시스템 관리")
            if st.button("🚨 기존 오류 DB 싹 밀기"):
                with DB_LOCK: bank_db.truncate(); st.success("초기화 완료!"); st.rerun()

        st.divider()
        mode = st.radio("모드", ["맞춤 문항", "30문항 풀세트"])
        sub_choice = st.selectbox("선택과목", ["미적분", "확률과 통계", "기하"])
        
        if mode == "맞춤 문항":
            num_choice = st.slider("문항 수", 2, 20, 10, step=2)
            score_val = int(st.selectbox("배점 설정", ["2", "3", "4"]))
        else:
            num_choice = 30
            score_val = None
            
        btn = st.button("🚀 프리미엄 발간 시작", use_container_width=True)
        with DB_LOCK: st.caption(f"🗄️ 백그라운드 DB 비축량: {len(bank_db)} / 10000")

if st.session_state.verified and btn:
    with st.spinner("객관식/주관식 배치 및 수능 단원 비율에 맞춰 조판 중입니다..."):
        try:
            html_out, db_hits = asyncio.run(run_orchestrator(sub_choice, num_choice, score_val))
            st.success(f"✅ 발간 완료! (DB 추출: {db_hits}개 / AI 신규 생성: {num_choice - db_hits}개)")
            st.download_button(label="📥 인쇄용 HTML 다운로드", data=html_out, file_name=f"2026_수능_{sub_choice}.html", mime="text/html", type="primary", use_container_width=True)
            st.components.v1.html(html_out, height=800, scrolling=True)
        except Exception as e: 
            st.error(f"❌ 발간 중 오류 발생: {e}")




