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

# --- 3. [강화] 초정밀 텍스트 정제 엔진 (수식 깨짐 방어) ---
def polish_output(text):
    if not text: return ""
    text = re.sub(r'^(과목|단원|배점|유형|난이도|수학\s?[I|II|1|2]|Step\s?\d):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'\[.*?점\]\s*', '', text)
    
    # AI의 흔한 실수 강제 교정 (9.pdf 오류 해결)
    text = text.replace('Mn', r'\ln')
    text = text.replace(r'\$', '$')
    text = text.replace('->', r'\to')
    
    # sqrt() 를 \sqrt{} 로 강제 변환
    text = re.sub(r'sqrt\((.*?)\)', r'\\sqrt{\1}', text)
    
    math_tokens = ['sin', 'cos', 'tan', 'log', 'ln', 'lim', 'exp', 'vec', 'cdot', 'frac', 'theta', 'pi', 'infty', 'to', 'sum', 'int', 'alpha', 'beta', 'mu', 'sigma']
    for token in math_tokens:
        text = re.sub(rf'(?<!\\)\b{token}\b', rf'\\{token}', text)
    return text.strip()

def clean_option(text):
    return polish_output(re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)).strip())

# --- 4. 가이드라인 ---
def get_pro_guide(score):
    if score == 2:
        return "[2점] 1분 컷 단순 연산. 복잡한 도형 절대 금지."
    elif score == 3:
        return "[3점] 개념 2개 결합 응용."
    else:
        return "[4점 킬러] 조건 (가), (나) 활용, 케이스 분류 필수 최고난도."

# --- 5. HTML 템플릿 ---
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

# --- 6. AI 생성 엔진 ---
async def generate_batch_ai(q_info, size=2):
    model = genai.GenerativeModel('models/gemini-2.0-flash')
    guide = get_pro_guide(q_info['score'])
    
    prompt = f"""과목:{q_info['sub']} | 단원:{q_info['topic']} | 배점:{q_info['score']}
[지시사항] 
1. {guide}
2. [중요] 수식은 단일 $ 기호 사용. `sqrt()` 같은 일반 텍스트 수식 절대 금지, 무조건 LaTeX `\\sqrt{{}}` 사용. `Mn` 오타 내지 말고 `\\ln` 사용.
3. JSON 이스케이프: JSON 내부이므로 LaTeX 백슬래시 두 번(`\\\\`) 필수.
4. 오직 [{{"topic": "{q_info['topic']}", "question": "...", "svg_draw": null, "options": ["①",...], "solution": "..."}}] 형태의 JSON 배열만 출력."""
    
    try:
        res = await model.generate_content_async(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.85))
        match = re.search(r'\[.*\]', res.text.strip(), re.DOTALL)
        if not match: return []
        data = json.loads(match.group(0))
        return [{**d, "batch_id": str(uuid.uuid4()), "sub": q_info['sub'], "score": q_info['score'], "type": "객관식"} for d in data]
    except: 
        return []

# --- 7. [신규] 다중 섀도우 예비 문항 뱅크 (중복 방지용) ---
FALLBACK_BANK = {
    ("미적분", 4, "미분법"): [
        {"question": "함수 $f(x) = e^x \\sin x$ 에 대하여 구간 $[0, \\pi]$에서 곡선 $y=f(x)$ 의 변곡점의 $x$ 좌표를 $a$ 라 할 때, $\\tan a$ 의 값을 구하시오.", "options": ["-1", "0", "1", "$\\sqrt{2}$", "$\\sqrt{3}$"], "solution": "$f''(x) = 2e^x \\cos x=0$ 에서 $x = \\frac{\\pi}{2}$ 이다. $\\tan(\\frac{\\pi}{2})$ 는 정의되지 않는다."},
        {"question": "실수 전체의 집합에서 미분가능한 함수 $f(x)$가 $f(x) = x e^{-x^2}$ 일 때, $f(x)$의 극댓값을 구하시오.", "options": ["$\\frac{1}{\\sqrt{e}}$", "$\\frac{1}{e}$", "$\\frac{2}{e}$", "$1$", "$\\sqrt{e}$"], "solution": "$f'(x) = e^{-x^2}(1-2x^2)=0$ 에서 $x=\\frac{1}{\\sqrt{2}}$ 일 때 극대이다."}
    ],
    ("미적분", 4, "적분법"): [
        {"question": "$\\int_{0}^{\\frac{\\pi}{2}} x \\cos x \\, dx$ 의 값은?", "options": ["$\\frac{\\pi}{2}-1$", "$\\frac{\\pi}{2}$", "$\\frac{\\pi}{2}+1$", "$\\pi-1$", "$\\pi$"], "solution": "부분적분법을 이용한다. $[x \\sin x]_0^{\\frac{\\pi}{2}} - \\int_0^{\\frac{\\pi}{2}} \\sin x dx = \\frac{\\pi}{2} - 1$."},
        {"question": "$\\int_{1}^{e} x^2 \\ln x \\, dx$ 의 값을 구하시오.", "options": ["$\\frac{2e^3+1}{9}$", "$\\frac{2e^3}{9}$", "$\\frac{e^3-1}{3}$", "$\\frac{2e^3-1}{9}$", "$\\frac{e^3+1}{3}$"], "solution": "부분적분법을 사용하면 $\\frac{2e^3+1}{9}$ 이 나온다."}
    ],
    ("미적분", 4, "수열의 극한"): [
        {"question": "$\\lim_{n \\to \\infty} \\frac{3^n + 4^n}{3^{n+1} + 4^{n-1}}$ 의 값은?", "options": ["$\\frac{1}{4}$", "$\\frac{1}{3}$", "$1$", "$3$", "$4$"], "solution": "분모 분자를 $4^n$으로 나누면 $4$ 가 된다."},
        {"question": "수열 $\\{a_n\\}$ 에 대하여 $\\lim_{n \\to \\infty} n a_n = 2$ 일 때, $\\lim_{n \\to \\infty} \\frac{n^2 a_n + 1}{n+2}$ 의 값을 구하시오.", "options": ["1", "2", "3", "4", "5"], "solution": "주어진 식을 변형하면 극한값은 $2$가 된다."}
    ]
}
# (기본값 처리를 위한 헬퍼)
def get_fallback(sub, score, topic, used_fallbacks):
    # 키에 맞는 리스트를 찾음 (없으면 미분법 4점으로 대체)
    key = (sub, score, topic)
    if key not in FALLBACK_BANK:
        key = ("미적분", 4, "미분법") 
    
    available_qs = [q for q in FALLBACK_BANK[key] if q['question'] not in used_fallbacks]
    
    # 다 썼으면 초기화 (무한 루프 방지)
    if not available_qs:
        available_qs = FALLBACK_BANK[key]
        
    selected = random.choice(available_qs)
    used_fallbacks.add(selected['question'])
    return selected

async def get_safe_q(q_info, used_ids, topic_counts, total_num, used_fallbacks):
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
    
    # [핵심] 중복 없는 그림자 예비 문항 로드 (예비 문항 꼬리표 삭제)
    fallback_data = get_fallback(q_info['sub'], q_info['score'], q_info['topic'], used_fallbacks)
    return {"num": q_info['num'], "score": q_info['score'], "question": fallback_data['question'], "options": fallback_data['options'], "solution": fallback_data['solution'], "source": "SAFE", "svg_draw": None}

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
    
    # [비율 검증] 블루프린트 생성 시 1:1:1 비율 강제 할당
    blueprint = [{"num": i+1, "sub": sub_choice, "topic": topics[i % 3], "score": score_choice or 4} for i in range(num_choice)]
    
    used_ids, topic_counts, results = set(), {}, []
    used_fallbacks = set() # 예비 문항 중복 방지 트래커
    
    prog, status = st.progress(0), st.empty()
    
    for q_info in blueprint:
        status.text(f"⏳ {q_info['num']}번 조판 중... ({q_info['topic']} 비율 매칭)")
        res = await get_safe_q(q_info, used_ids, topic_counts, num_choice, used_fallbacks)
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

# --- 8. UI 및 관리자 메뉴 ---
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
            if st.button("🧹 수식 깨진 불량 문항 정밀 삭제"):
                with DB_LOCK:
                    def is_broken(doc):
                        text = str(doc.get('question','')) + str(doc.get('solution',''))
                        return any(p in text for p in [r'\$', 'sqrt(', r'\backslash', 'Mn'])
                    bad_docs = [doc.doc_id for doc in bank_db.all() if is_broken(doc)]
                    if bad_docs:
                        bank_db.remove(doc_ids=bad_docs)
                        st.success(f"✅ {len(bad_docs)}개 불량 삭제 완료!")
                    else: st.info("✨ DB가 깨끗합니다.")
            
            if st.button("🚨 전체 DB 강제 초기화"):
                with DB_LOCK: bank_db.truncate(); st.success("초기화 완료!"); st.rerun()

        st.divider()
        mode = st.radio("모드", ["30문항 풀세트", "맞춤 문항"])
        sub_choice = st.selectbox("선택과목", ["미적분", "확률과 통계", "기하"])
        
        if mode == "맞춤 문항":
            num_choice = st.slider("문항 수", 2, 20, 10, step=2)
            score_val = int(st.selectbox("배점 설정", ["2", "3", "4"]))
        else:
            num_choice = 30
            score_val = None
            
        btn = st.button("🚀 프리미엄 발간 시작", use_container_width=True)

if st.session_state.verified and btn:
    with st.spinner("AI가 수식을 정제하고 수능 단원 비율(1:1:1)에 맞춰 조판 중입니다..."):
        try:
            html_out, db_hits = asyncio.run(run_orchestrator(sub_choice, num_choice, score_val))
            st.success(f"✅ 발간 완료! (DB 추출: {db_hits}개 / AI 신규 생성(또는 안전망): {num_choice - db_hits}개)")
            
            st.download_button(label="📥 깔끔한 인쇄용 HTML 다운로드", data=html_out, file_name=f"2026_수능모의평가_{sub_choice}.html", mime="text/html", type="primary", use_container_width=True)
            st.components.v1.html(html_out, height=800, scrolling=True)
        except Exception as e: 
            st.error(f"❌ 발간 중 오류 발생: {e}")



