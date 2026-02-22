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

# --- 3. 텍스트 정제 엔진 (수식 깨짐 방어) ---
def polish_output(text):
    if not text: return ""
    text = re.sub(r'^(과목|단원|배점|유형|난이도|수학\s?[I|II|1|2]|Step\s?\d):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'\[.*?점\]\s*', '', text)
    text = text.replace('Mn', r'\ln').replace(r'\$', '$').replace('->', r'\to')
    text = re.sub(r'sqrt\((.*?)\)', r'\\sqrt{\1}', text)
    
    math_tokens = ['sin', 'cos', 'tan', 'log', 'ln', 'lim', 'exp', 'vec', 'cdot', 'frac', 'theta', 'pi', 'infty', 'to', 'sum', 'int', 'alpha', 'beta', 'mu', 'sigma']
    for token in math_tokens:
        text = re.sub(rf'(?<!\\)\b{token}\b', rf'\\{token}', text)
    return text.strip()

def clean_option(text):
    return polish_output(re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)).strip())

# --- 4. [강화] 수능 출제 위원급 난이도 가이드라인 ---
def get_pro_guide(sub, score):
    if score == 2:
        return f"""[최우선: 수능 2점 난이도 절대 엄수]
- 1분 내외로 암산 가능한 '기초 공식 대입 및 연산' 문제여야 합니다.
- {sub} 과목의 가장 기본적인 성질(단순 극한, 단순 미분/적분, 기초 확률 계산 등)만 물어보세요.
- 🚨절대 금지: (가)(나) 조건 박스, 케이스 분류, 복잡한 도형/그래프, 추론 영역은 무조건 배제하세요."""
    elif score == 3:
        return f"""[최우선: 수능 3점 응용 난이도]
- 2~3개의 기본 개념을 결합하여 푸는 전형적인 3점 문항.
- {sub} 교과서 예제/유제 수준을 약간 변형한 깔끔한 문제로 출제하세요."""
    else:
        return f"""[최우선: 수능 4점 킬러/준킬러 난이도]
- 1등급을 가르는 고난도 문항입니다.
- 🚨필수 포함: (가), (나) 형태의 복합 조건 박스.
- 케이스 분류, 다단계 논리적 추론, 여러 개념의 융합을 반드시 포함하세요."""

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
    guide = get_pro_guide(q_info['sub'], q_info['score'])
    
    prompt = f"""당신은 대한민국 최고의 수능 수학 출제 위원입니다.
과목:{q_info['sub']} | 단원:{q_info['topic']} | 배점:{q_info['score']}
[지시사항] 
1. {guide}
2. [중요] 수식은 단일 $ 기호 사용. `sqrt()` 절대 금지, `\\sqrt{{}}` 사용. `Mn` 오타 내지 말고 `\\ln` 사용.
3. JSON 이스케이프: JSON 내부이므로 모든 LaTeX 백슬래시는 두 번(`\\\\`) 작성.
4. 오직 [{{"topic": "{q_info['topic']}", "question": "...", "svg_draw": null, "options": ["①",...], "solution": "..."}}] 형태의 JSON 배열만 출력."""
    
    try:
        res = await model.generate_content_async(prompt, safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.85))
        match = re.search(r'\[.*\]', res.text.strip(), re.DOTALL)
        if not match: return []
        data = json.loads(match.group(0))
        return [{**d, "batch_id": str(uuid.uuid4()), "sub": q_info['sub'], "score": q_info['score'], "type": "객관식"} for d in data]
    except: 
        return []

# --- 7. [버그 수정] 배점 동기화 예비 문항 (Dynamic Score Fallback) ---
def get_fallback(score, used_fallbacks):
    # 각 배점별로 난이도에 맞는 예비 문항을 여러 개 준비
    fallbacks_by_score = {
        2: [
            {"question": "$\\lim_{x \\to 0} \\frac{\\sin 2x}{x}$ 의 값을 구하시오.", "options": ["1", "2", "3", "4", "5"], "solution": "극한의 기본 성질에 의해 $2$이다."},
            {"question": "$\\log_2 8 + \\log_3 9$ 의 값을 구하시오.", "options": ["2", "3", "4", "5", "6"], "solution": "$3 + 2 = 5$ 이다."},
            {"question": "함수 $f(x) = x^3 + 2x$ 에 대하여 $f'(1)$ 의 값을 구하시오.", "options": ["1", "3", "5", "7", "9"], "solution": "$f'(x) = 3x^2 + 2$ 이므로 $f'(1) = 5$ 이다."}
        ],
        3: [
            {"question": "함수 $f(x) = x^3 - 3x^2 + a$ 가 $x=2$ 에서 극솟값 $-1$ 을 가질 때, 상수 $a$ 의 값을 구하시오.", "options": ["1", "2", "3", "4", "5"], "solution": "$f'(x) = 3x^2 - 6x = 0$ 에서 $x=2$ 일 때 극소이다. $f(2) = 8 - 12 + a = -1$ 이므로 $a = 3$ 이다."},
            {"question": "$\\int_{0}^{1} x e^x dx$ 의 값을 구하시오.", "options": ["$e-2$", "$1$", "$e-1$", "$e$", "$e+1$"], "solution": "부분적분법을 이용하면 $[x e^x]_0^1 - \\int_0^1 e^x dx = e - (e - 1) = 1$ 이다."}
        ],
        4: [
            {"question": "실수 전체의 집합에서 미분가능한 함수 $f(x)$가 다음 조건을 만족시킨다.\n(가) $f(0) = 0$\n(나) 모든 실수 $x$에 대하여 $f'(x) = e^{-x^2}$ 이다.\n$\\int_{0}^{1} x f(x) dx$ 의 값을 구하시오.", "options": ["$\\frac{1}{2e}$", "$\\frac{1}{2}(1-\\frac{1}{e})$", "$1-\\frac{1}{e}$", "$\\frac{1}{e}$", "$\\frac{e-1}{2}$"], "solution": "부분적분법을 이용하여 $\\int x f(x) dx$ 를 $\\frac{1}{2}x^2 f(x)$ 꼴로 유도하여 계산한다. (고난도 예비)"},
            {"question": "주사위를 4번 던져서 나오는 눈의 수를 차례로 $a, b, c, d$라 할 때, $(a-b)(b-c)(c-d) \\neq 0$ 일 확률을 구하시오.", "options": ["$\\frac{1}{6}$", "$\\frac{5}{18}$", "$\\frac{5}{12}$", "$\\frac{125}{216}$", "$\\frac{25}{36}$"], "solution": "이웃한 수가 같지 않을 확률이므로 첫 번째는 6가지, 나머지는 각각 앞의 수와 다른 5가지씩 가능하다. 따라서 $\\frac{6 \\times 5^3}{6^4} = \\frac{125}{216}$ 이다."}
        ]
    }
    
    # 요청된 배점의 풀(pool)을 가져오고, 없으면 3점으로 대체
    pool = fallbacks_by_score.get(score, fallbacks_by_score[3])
    
    # 사용되지 않은 문항 필터링
    available_qs = [q for q in pool if q['question'] not in used_fallbacks]
    
    # 만약 모두 다 썼다면 리셋 (무한 루프 방지)
    if not available_qs:
        available_qs = pool
        
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
    
    # [수정됨] 배점에 맞는 예비 문항 호출
    fallback_data = get_fallback(q_info['score'], used_fallbacks)
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
    
    blueprint = [{"num": i+1, "sub": sub_choice, "topic": topics[i % 3], "score": score_choice or 4} for i in range(num_choice)]
    
    used_ids, topic_counts, results = set(), {}, []
    used_fallbacks = set()
    
    prog, status = st.progress(0), st.empty()
    
    for q_info in blueprint:
        status.text(f"⏳ {q_info['num']}번 난이도({q_info['score']}점) 조판 중...")
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
        mode = st.radio("모드", ["맞춤 문항", "30문항 풀세트"])
        sub_choice = st.selectbox("선택과목", ["미적분", "확률과 통계", "기하"])
        
        if mode == "맞춤 문항":
            num_choice = st.slider("문항 수", 2, 20, 10, step=2)
            score_val = int(st.selectbox("배점 설정", ["2", "3", "4"]))
        else:
            num_choice = 30
            score_val = None
            
        btn = st.button("🚀 프리미엄 발간 시작", use_container_width=True)

if st.session_state.verified and btn:
    with st.spinner(f"AI가 {score_val}점 난이도에 맞춰 조판 중입니다..."):
        try:
            html_out, db_hits = asyncio.run(run_orchestrator(sub_choice, num_choice, score_val))
            st.success(f"✅ 발간 완료! (DB 추출: {db_hits}개 / AI 신규 생성(또는 안전망): {num_choice - db_hits}개)")
            
            st.download_button(label="📥 깔끔한 인쇄용 HTML 다운로드", data=html_out, file_name=f"2026_수능모의평가_{sub_choice}.html", mime="text/html", type="primary", use_container_width=True)
            st.components.v1.html(html_out, height=800, scrolling=True)
        except Exception as e: 
            st.error(f"❌ 발간 중 오류 발생: {e}")



