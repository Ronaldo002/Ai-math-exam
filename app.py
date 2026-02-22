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

# --- 1. 환경 설정 및 API 보안 ---
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("PAID_API_KEY 설정이 필요합니다!")
    st.stop()

SAFETY_SETTINGS = [{"category": f"HARM_CATEGORY_{c}", "threshold": "BLOCK_NONE"} for c in ["HARASSMENT", "HATE_SPEECH", "SEXUALLY_EXPLICIT", "DANGEROUS_CONTENT"]]
ADMIN_EMAIL = "pgh001002@gmail.com"

# --- 2. DB 및 전역 락 (자가 치유 로직) ---
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

# --- 3. 초정밀 텍스트 정제 엔진 (수식 및 벡터 최적화) ---
def polish_output(text):
    if not text: return ""
    # 불필요한 레이블 제거
    text = re.sub(r'^(과목|단원|배점|유형|난이도|수학\s?[I|II|1|2]|Step\s?\d):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'\[.*?점\]\s*', '', text)
    
    # LaTeX 주요 토큰 강제 보정 (깨짐 방지)
    math_tokens = [
        'sin', 'cos', 'tan', 'log', 'ln', 'lim', 'exp', 'sqrt', 'vec', 'cdot', 
        'frac', 'theta', 'pi', 'infty', 'to', 'sum', 'int', 'alpha', 'beta', 'mu', 'sigma', 'lambda'
    ]
    for token in math_tokens:
        text = re.sub(rf'(?<!\\)\b{token}\b', rf'\\{token}', text)
    
    return text.replace('->', r'\to').strip()

def clean_option(text):
    # 선지 번호(①~⑤) 제거 후 정제
    clean = re.sub(r'^([①-⑤]|[1-5][\.\)])\s*', '', str(text)).strip()
    return polish_output(clean)

# --- 4. [핵심] 난이도 및 그림 생성 가이드라인 ---
def get_pro_guide(score):
    if score == 2:
        return """[최우선: 2점 난이도 절대 엄수]
- 반드시 '1분 이내'에 풀리는 단순 계산형 문항으로 구성할 것.
- 복잡한 도형 활용이나 다단계 추론은 절대 금지.
- 예: 단순 지수/로그 연산, 간단한 미분계수 f'(a) 구하기, 극한값 계산."""
    elif score == 3:
        return "[3점 응용] 기본 개념 2개를 결합하거나, 교과서 예제 수준의 응용이 필요한 문항."
    else:
        return """[4점 킬러/준킬러]
- (가), (나) 조건을 활용한 복합 추론 필수.
- 케이스 분류가 필요하거나 신유형 아이디어를 포함할 것.
- 변별력이 확보되는 고난도 문항으로 설계할 것."""

# --- 5. HTML/CSS 템플릿 (진짜 그림 및 선지 정렬 최적화) ---
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
        .question-box {{ position: relative; line-height: 2.3; font-size: 11pt; padding-left: 28px; margin-bottom: 45px; text-align: justify; }}
        .q-num {{ position: absolute; left: 0; top: 0; font-weight: 800; font-size: 13pt; }}
        .diagram-container {{ margin: 15px 0; text-align: center; width: 100%; }}
        .diagram-container svg {{ max-width: 100%; height: auto; background: #fff; border: 1px solid #f9f9f9; }}
        .options-container {{ margin-top: 15px; display: flex; flex-wrap: wrap; gap: 5px; }}
        .options-container span {{ flex: 0 0 18%; min-width: 140px; font-size: 10.5pt; white-space: nowrap; }}
        @media print {{ .no-print {{ display: none; }} body {{ padding: 0; }} .paper {{ box-shadow: none; margin: 0; }} }}
    </style></head>
    <body>
        <div class="no-print" style="text-align:center; margin-bottom:20px;">
            <button style="background:#2e7d32; color:white; padding:12px 24px; border:none; border-radius:5px; cursor:pointer; font-weight:bold;" onclick="window.print()">🖨️ PDF 다운로드 / 인쇄</button>
        </div>
        <div class="paper-container">{p_html}<div class="paper"><h2 style="text-align:center;">[정답 및 해설]</h2>{s_html}</div></div>
    </body></html>
    """

# --- 6. 생성 엔진 (SVG 직접 그리기 지시) ---
def build_strict_prompt(q_info, size):
    guide = get_pro_guide(q_info['score'])
    prompt = f"""과목:{q_info['sub']} | 단원:{q_info['topic']} | 배점:{q_info['score']} | 유형:{q_info['type']}
[지시] 
1. 한국어 전용. {guide}
2. **도형이나 그래프가 필요한 경우, 반드시 `<svg>` 태그를 사용하여 직접 좌표를 계산해 `svg_draw` 필드에 그려낼 것.** (설명만 하지 말 것)
3. 수식은 $ $ 필수. 벡터는 \\vec{{a}} 사용.
4. JSON {size}개 생성: 
[{{ "topic": "{q_info['topic']}", "question": "...", "svg_draw": "<svg ...>...</svg> (없으면 null)", "options": ["선지1",...], "solution": "..." }}]"""
    return prompt

async def generate_batch_ai(q_info, size=2):
    model = genai.GenerativeModel('models/gemini-2.0-flash')
    try:
        res = await model.generate_content_async(build_strict_prompt(q_info, size), safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.85, response_mime_type="application/json"))
        data = json.loads(res.text.strip())
        return [{**d, "batch_id": str(uuid.uuid4()), "sub": q_info['sub'], "score": q_info['score'], "type": q_info['type']} for d in data]
    except: return []

async def get_safe_q(q_info, used_ids, used_batch_ids, topic_counts, total_num):
    # 2문항 쿼터제 및 DB 추출 로직
    with DB_LOCK:
        available = bank_db.search((QBank.sub == q_info['sub']) & (QBank.topic == q_info['topic']) & (QBank.score == q_info['score']))
    
    fresh = [q for q in available if str(q.doc_id) not in used_ids]
    quota = max(2, (total_num // 3))
    
    if fresh and topic_counts.get(q_info['topic'], 0) < quota:
        sel = random.choice(fresh)
        topic_counts[sel['topic']] = topic_counts.get(sel['topic'], 0) + 1
        used_ids.add(str(sel.doc_id))
        return {**sel, "num": q_info['num'], "source": "DB"}
    
    # DB에 없으면 AI 생성
    for _ in range(2):
        new_batch = await generate_batch_ai(q_info, size=2)
        if new_batch:
            sel = new_batch[0]
            topic_counts[sel['topic']] = topic_counts.get(sel['topic'], 0) + 1
            return {**sel, "num": q_info['num'], "source": "AI", "full_batch": new_batch}
    
    return {"num": q_info['num'], "score": q_info['score'], "type": "객관식", "question": "지연 발생 (재시도 필요)", "options": ["-"]*5, "solution": "-", "source": "ERROR", "svg_draw": None}

async def run_orchestrator(sub_choice, num_choice, score_choice=None):
    # 실제 수능 단원 배분 로직
    topics = {"미적분": ["수열의 극한", "미분법", "적분법"], "확률과 통계": ["경우의 수", "확률", "통계"], "기하": ["이차곡선", "평면벡터", "공간도형"]}[sub_choice]
    blueprint = [{"num": i+1, "sub": sub_choice, "topic": topics[i % 3], "score": score_choice or 3, "type": "객관식"} for i in range(num_choice)]
    
    used_ids, used_batch_ids, topic_counts, results = set(), set(), {}, []
    prog, status = st.progress(0), st.empty()
    
    for q_info in blueprint:
        status.text(f"⏳ {q_info['num']}번 정밀 조판 및 SVG 도면 작성 중...")
        res = await get_safe_q(q_info, used_ids, used_batch_ids, topic_counts, num_choice)
        results.append(res)
        if res.get('source') == "AI" and "full_batch" in res:
            safe_save_to_bank(res['full_batch'], q_info['type'])
        prog.progress(q_info['num'] / num_choice)
        await asyncio.sleep(0.5)
    
    p_html, s_html = "", ""
    q_html_list = []
    for item in results:
        num, score = item.get('num'), item.get('score')
        q_text = polish_output(item.get('question'))
        svg = item.get('svg_draw', "")
        diag_html = f"<div class='diagram-container'>{svg}</div>" if svg and "<svg" in svg else ""
        opts_html = "".join([f"<span>{chr(9312+j)} {clean_option(str(o))}</span>" for j, o in enumerate(item.get('options', []))])
        
        q_html_list.append(f"<div class='question-box'><span class='q-num'>{num}</span> {q_text} <b>[{score}점]</b>{diag_html}<div class='options-container'>{opts_html}</div></div>")
        s_html += f"<div style='margin-bottom:15px;'><b>{num}번:</b> {polish_output(item.get('solution'))}</div>"

    # 페이지당 2문제씩 그리드 배치
    for i in range(0, len(q_html_list), 2):
        chunk = "".join(q_html_list[i:i+2])
        p_html += f"<div class='paper'><div class='header' style='text-align:center; border-bottom:2.5px solid #000; margin-bottom:25px;'><h1>2026 수능 모의평가</h1></div><div class='question-grid'>{chunk}</div></div>"
    
    return get_html_template(p_html, s_html), sum(1 for r in results if r.get('source') == "DB")

# --- 7. UI ---
st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")
with st.sidebar:
    st.title("🎓 본부 제어실")
    st.success(f"✅ {ADMIN_EMAIL} 인증됨")
    if st.button("🚨 전체 DB 초기화 (기존 엉터리 문제 소각)"):
        with DB_LOCK: bank_db.truncate(); st.rerun()
    st.divider()
    sub = st.selectbox("과목", ["미적분", "확률과 통계", "기하"])
    num = st.slider("문항 수", 2, 20, 4, step=2)
    score = int(st.selectbox("난이도 설정 (2점=기초, 4점=킬러)", ["2", "3", "4"]))
    btn = st.button("🚀 무결점 발간 시작", use_container_width=True)

if btn:
    with st.spinner("AI가 SVG 도면을 설계하고 수능 규격에 맞춰 조판 중입니다..."):
        try:
            html, db_hits = asyncio.run(run_orchestrator(sub, num, score))
            st.success(f"✅ 발간 완료! (DB 활용: {db_hits}개)")
            st.components.v1.html(html, height=1200, scrolling=True)
        except Exception as e:
            st.error(f"❌ 발간 중 오류 발생: {e}")

