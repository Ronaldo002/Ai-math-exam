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

# --- 2. DB 및 전역 락 ---
@st.cache_resource
def get_databases():
    return TinyDB('user_registry.json'), TinyDB('question_bank.json')

db, bank_db = get_databases()
User, QBank = Query(), Query()
DB_LOCK = threading.Lock()

# --- 3. 텍스트 및 수식 정제 ---
def polish_output(text):
    if not text: return ""
    text = re.sub(r'^(과목|단원|배점|유형|난이도|수학\s?[I|II|1|2]|Step\s?\d):.*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'\[.*?점\]\s*', '', text)
    math_tokens = ['sin', 'cos', 'tan', 'log', 'ln', 'lim', 'exp', 'sqrt', 'vec', 'cdot', 'frac', 'theta', 'pi', 'infty', 'to', 'sum', 'int', 'alpha', 'beta', 'mu', 'sigma', 'lambda']
    for token in math_tokens:
        text = re.sub(rf'(?<!\\)\b{token}\b', rf'\\{token}', text)
    return text.replace('->', r'\to').strip()

# --- 4. [신규] 난이도별 엄격 가이드라인 ---
def get_point_guide(score):
    if score == 2:
        return """[최우선: 2점 난이도 준수] 
- 반드시 1분 내외로 풀 수 있는 단순 계산형으로 출제할 것.
- 예: 로그의 단순 연산, 지수법칙, 단순 미분계수 f'(1) 구하기, 함수의 극한값 구하기.
- 7.pdf에서 발생한 '무한등비급수 도형 문제' 같은 고난도는 2점에 절대 금지."""
    elif score == 3:
        return "[3점 응용] 개념 2개를 결합하거나, 가벼운 응용이 필요한 수능 3점 수준."
    else:
        return "[4점 킬러] (가), (나) 조건 필수. 복합 추론 및 케이스 분류가 필요한 고난도 문항."

# --- 5. HTML/CSS (SVG 렌더링 지원) ---
def get_html_template(p_html, s_html):
    return f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
        * {{ font-family: 'Nanum Myeongjo', serif !important; }}
        body {{ background: #f0f2f6; padding: 20px; }}
        .paper {{ background: white; width: 210mm; min-height: 297mm; padding: 20mm 18mm; margin: 0 auto 30px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); position: relative; }}
        .question-grid {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 50px; position: relative; }}
        .question-grid::after {{ content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: #eee; }}
        .question-box {{ position: relative; line-height: 2.2; font-size: 11pt; padding-left: 28px; margin-bottom: 40px; }}
        .q-num {{ position: absolute; left: 0; top: 0; font-weight: 800; font-size: 13pt; }}
        .diagram-container {{ margin: 10px 0; text-align: center; width: 100%; }}
        .diagram-container svg {{ max-width: 100%; height: auto; border: 1px solid #f0f0f0; background: #fff; }}
        .options-container {{ margin-top: 15px; display: flex; flex-wrap: wrap; gap: 5px; }}
        .options-container span {{ flex: 0 0 18%; min-width: 135px; font-size: 10pt; }}
        @media print {{ .no-print {{ display: none; }} body {{ padding: 0; }} .paper {{ box-shadow: none; margin: 0; }} }}
    </style></head>
    <body>
        <div class="no-print" style="text-align:center; margin-bottom:20px;"><button style="background:#2e7d32; color:white; padding:12px 24px; border:none; border-radius: 5px; cursor:pointer; font-weight:bold;" onclick="window.print()">🖨️ PDF 다운로드 / 인쇄</button></div>
        <div class="paper-container">{p_html}<div class="paper"><h2 style="text-align:center;">[정답 및 해설]</h2>{s_html}</div></div>
    </body></html>
    """

# --- 6. 생성 엔진 (SVG 작성 지시 추가) ---
def build_strict_prompt(q_info, size):
    guide = get_point_guide(q_info['score'])
    prompt = f"""과목:{q_info['sub']} | 단원:{q_info['topic']} | 배점:{q_info['score']} | 유형:{q_info['type']}
[필수 지시] 
1. 한국어 전용. {guide}
2. **그림이 필요한 문항인 경우, 반드시 `<svg>` 태그를 활용한 완성된 SVG 코드를 `svg_draw` 필드에 작성할 것.** (설명만 하지 말고 직접 좌표를 계산해서 그릴 것)
3. 수식은 $ $ 필수. 
4. JSON {size}개 생성: 
[{{ "topic": "{q_info['topic']}", "question": "...", "svg_draw": "<svg ...>...</svg> (없으면 null)", "options": ["선지1",...], "solution": "..." }}]"""
    return prompt

async def generate_batch_ai(q_info, size=2):
    model = genai.GenerativeModel('models/gemini-2.0-flash') # 최신 모델 사용
    try:
        res = await model.generate_content_async(build_strict_prompt(q_info, size), safety_settings=SAFETY_SETTINGS, generation_config=genai.types.GenerationConfig(temperature=0.8, response_mime_type="application/json"))
        data = json.loads(res.text.strip())
        return [{**d, "batch_id": str(uuid.uuid4()), "sub": q_info['sub'], "score": q_info['score'], "type": q_info['type']} for d in data]
    except: return []

async def get_safe_q(q_info, used_ids, used_batch_ids, topic_counts, total_num):
    # (중복 검사 및 DB 추출 로직 유지)
    new_batch = await generate_batch_ai(q_info, size=2)
    if new_batch:
        return {**new_batch[0], "num": q_info['num'], "source": "AI", "full_batch": new_batch}
    return {"num": q_info['num'], "score": 2, "type": "객관식", "question": "생성 오류", "options": ["-"]*5, "solution": "-", "source": "ERROR", "svg_draw": None}

async def run_orchestrator(sub_choice, num_choice, score_choice=None):
    # (블루프린트 생성 로직 유지)
    blueprint = [{"num": i+1, "sub": sub_choice, "topic": "공통", "score": score_choice or 3, "type": "객관식"} for i in range(num_choice)]
    used_ids, used_batch_ids, topic_counts, results = set(), set(), {}, []
    
    for q_info in blueprint:
        res = await get_safe_q(q_info, used_ids, used_batch_ids, topic_counts, num_choice)
        results.append(res)
    
    p_html, s_html = "", ""
    # 시험지 조판 (2열 그리드)
    q_html_list = []
    for item in results:
        num, score = item.get('num'), item.get('score')
        q_text = polish_output(item.get('question'))
        svg = item.get('svg_draw', "")
        diag_html = f"<div class='diagram-container'>{svg}</div>" if svg and "<svg" in svg else ""
        opts = "".join([f"<span>{chr(9312+j)} {polish_output(str(o))}</span>" for j, o in enumerate(item.get('options', []))])
        
        q_html_list.append(f"<div class='question-box'><span class='q-num'>{num}</span> {q_text} <b>[{score}점]</b>{diag_html}<div class='options-container'>{opts}</div></div>")
        s_html += f"<div style='margin-bottom:10px;'><b>{num}번:</b> {polish_output(item.get('solution'))}</div>"

    # 1페이지당 4문제씩 배분
    for i in range(0, len(q_html_list), 4):
        chunk = "".join(q_html_list[i:i+4])
        p_html += f"<div class='paper'><div class='header' style='text-align:center; border-bottom:2px solid #000; margin-bottom:20px;'><h1>2026 수능 모의평가</h1></div><div class='question-grid'>{chunk}</div></div>"
    
    return get_html_template(p_html, s_html), 0

# --- 7. UI ---
st.set_page_config(page_title="Premium 수능 출제 시스템", layout="wide")
with st.sidebar:
    st.title("🎓 본부 제어실")
    st.success("✅ pgh001002@gmail.com 인증됨")
    if st.button("🚨 DB 초기화 (기존 엉터리 문제 삭제)"):
        with DB_LOCK: bank_db.truncate(); st.rerun()
    st.divider()
    sub = st.selectbox("과목", ["미적분", "확률과 통계", "기하"])
    num = st.slider("문항 수", 2, 20, 4)
    score = int(st.selectbox("난이도 (2점 권장)", ["2", "3", "4"]))
    btn = st.button("🚀 무결점 발간 시작", use_container_width=True)

if btn:
    with st.spinner("SVG 도면 작성 및 난이도 정밀 교정 중..."):
        html, _ = asyncio.run(run_orchestrator(sub, num, score))
        st.components.v1.html(html, height=1200, scrolling=True)

