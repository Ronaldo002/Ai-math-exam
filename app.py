import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
from datetime import datetime
import time

# --- 초기 설정 ---
db = TinyDB('exam_service_db.json')
Exam = Query()
User = Query()

# 1. 사용자 인증 및 일일 제한 확인
def check_user_limit(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    user_data = db.table('users').get(User.id == user_id)
    
    if not user_data:
        db.table('users').insert({'id': user_id, 'count': 0, 'last_date': today})
        return True, 0
    
    if user_data['last_date'] != today:
        db.table('users').update({'count': 0, 'last_date': today}, User.id == user_id)
        return True, 0
    
    if user_data['count'] >= 5: # 하루 5회 제한
        return False, user_data['count']
    return True, user_data['count']

# 2. 메인 생성 로직 (캐싱 포함)
def get_exam(subject, diff, user_id):
    # 캐시 확인
    cached = db.table('exams').search((Exam.subject == subject) & (Exam.diff == diff))
    if cached:
        # 30% 확률로 새로운 문제를 생성하고, 아니면 캐시된 것 중 랜덤 반환 (비용 절감)
        st.info("📦 최적화된 보관함에서 문제를 가져왔습니다.")
        return cached[0]['content']

    # 캐시 없으면 유료 API 호출
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    with st.spinner("🚀 AI가 고난도 문항을 설계 중입니다..."):
        prompt = f"수능 수학 {subject} {diff} 문항과 해설을 HTML로 제작하라."
        response = model.generate_content(prompt)
        content = response.text
        
        # DB에 저장 (캐싱)
        db.table('exams').insert({'subject': subject, 'diff': diff, 'content': content, 'date': str(datetime.now())})
        # 사용자 카운트 증가
        current_count = db.table('users').get(User.id == user_id)['count']
        db.table('users').update({'count': current_count + 1}, User.id == user_id)
        
        return content

# --- UI 레이아웃 ---
st.title("⚡ 2026 수능 수학 킬러 마스터")

user_id = st.text_input("ID(이메일)를 입력하세요", placeholder="user@example.com")

if user_id:
    can_gen, count = check_user_limit(user_id)
    st.write(f"📊 오늘 남은 생성 횟수: {5 - count}회")
    
    if can_gen:
        sub = st.selectbox("과목", ["수학 I, II", "미적분", "확률과 통계"])
        df = st.select_slider("난이도", options=["표준", "준킬러", "킬러"])
        
        if st.button("🚀 모의고사 발간"):
            result = get_exam(sub, df, user_id)
            st.components.v1.html(result, height=800, scrolling=True)
    else:
        st.error("🚫 오늘 할당량을 모두 사용하셨습니다. 내일 다시 만나요!")
