import streamlit as st
import google.generativeai as genai
from tinydb import TinyDB, Query
from datetime import datetime
import time

# --- 1. 초기 설정 및 보안 ---
# Streamlit Cloud의 Secrets에 저장된 유료 키를 불러옵니다.
if "PAID_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["PAID_API_KEY"])
else:
    st.error("설정에서 PAID_API_KEY를 등록해주세요!")
    st.stop()

# 데이터베이스 설정 (사용자 기록 및 문제 보관용)
db = TinyDB('service_data.json')
User = Query()
Exam = Query()

# --- 2. 핵심 기능 함수 ---

def check_user_access(user_email):
    """사용자의 오늘 남은 생성 횟수를 확인합니다."""
    today = datetime.now().strftime("%Y-%m-%d")
    user_record = db.table('users').get(User.email == user_email)
    
    if not user_record:
        # 신규 사용자 등록
        db.table('users').insert({'email': user_email, 'count': 0, 'last_date': today})
        return True, 5
    
    if user_record['last_date'] != today:
        # 날짜가 바뀌었으면 카운트 초기화
        db.table('users').update({'count': 0, 'last_date': today}, User.email == user_email)
        return True, 5
    
    remaining = 5 - user_record['count']
    return (remaining > 0), remaining

def generate_math_exam(subject, difficulty, user_email):
    """Gemini 2.0 유료 API를 사용하여 문제를 생성합니다."""
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    # 프롬프트 고도화 (유료 버전의 지능 활용)
    prompt = f"""
    당신은 수능 수학 출제 위원입니다. {subject} 과목의 {difficulty} 난이도 문항을 제작하세요.
    반드시 다음 형식을 지키세요:
    1. 문제는 HTML 형식으로 작성하며 수식은 $기호를 사용한 LaTeX로 작성할 것.
    2. [해설시작]이라는 구분자 뒤에 상세한 풀이 과정을 HTML 형식으로 작성할 것.
    3. 정답이 선지에 반드시 존재하도록 검토할 것.
    """
    
    try:
        response = model.generate_content(prompt)
        content = response.text.replace('```html', '').replace('```', '').strip()
        
        # 생성 성공 시 사용자 카운트 증가
        current_count = db.table('users').get(User.email == user_email)['count']
        db.table('users').update({'count': current_count + 1}, User.email == user_email)
        
        return content
    except Exception as e:
        st.error(f"생성 중 오류 발생: {e}")
        return None

# --- 3. UI 레이아웃 (Streamlit) ---

st.set_page_config(page_title="2026 수능 수학 킬러 마스터", layout="wide")

st.title("♾️ 2026 수능 수학 무한 생성기 (Premium)")
st.caption("Gemini 2.0 Flash 유료 엔진이 가동 중입니다.")

# 로그인 섹션
with st.sidebar:
    st.header("👤 사용자 인증")
    user_email = st.text_input("이메일 주소를 입력하세요", placeholder="example@mail.com")
    
    if user_email:
        is_active, left_count = check_user_access(user_email)
        if is_active:
            st.success(f"오늘 생성 가능 횟수: {left_count}회")
        else:
            st.warning("오늘 할당량을 모두 사용하셨습니다.")
    
    st.divider()
    st.info("5,000원 예산 내에서 100명이 함께 사용하는 시스템입니다.")

# 메인 화면
if user_email and is_active:
    col1, col2 = st.columns(2)
    with col1:
        subject = st.selectbox("시험 과목 선택", ["수학 I, II", "미적분", "확률과 통계"])
    with col2:
        difficulty = st.select_slider("난이도 설정", options=["표준", "준킬러", "킬러"])

    if st.button("🚀 프리미엄 문항 발간 시작"):
        with st.spinner("AI 출제위원이 문제를 설계하고 있습니다..."):
            result = generate_math_exam(subject, difficulty, user_email)
            if result:
                # 결과 출력 (HTML 렌더링)
                st.markdown("---")
                st.components.v1.html(result, height=1000, scrolling=True)
                st.success("발간 완료! 위 화면에서 내용을 확인하세요.")

elif not user_email:
    st.info("좌측 사이드바에서 이메일 인증 후 시작해 주세요.")
