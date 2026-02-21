import streamlit as st
import google.generativeai as genai
import time

st.set_page_config(page_title="오류 수정 테스트 모드", layout="wide")

with st.sidebar:
    st.title("🧪 긴급 테스트 컨트롤")
    # 404 에러 방지를 위해 'models/'를 제외한 순수 모델명 사용
    selected_model = st.selectbox("모델 선택", 
                                ['gemini-1.5-flash-8b', 'gemini-1.5-flash', 'gemini-2.0-flash'])
    
    # 비상용 키 입력창 (신규 계정 키 권장)
    emergency_key = st.text_input("비상용 API Key 입력", type="password")
    st.info("429 한도 초과 시 새 계정의 키를 입력하세요.")

def run_fixed_generation(subject, num, model_name, key):
    # 키 설정: 비상키 우선 적용
    api_key = key if key else st.secrets["API_KEYS"][0]
    genai.configure(api_key=api_key)
    
    try:
        # 모델 선언 시 경로 접두사 제거 (404 에러 해결 핵심)
        model = genai.GenerativeModel(model_name)
        
        for i in range(1, num + 1):
            st.write(f"🔄 {i}번 문항 생성 중...")
            response = model.generate_content(f"수능 수학 {subject} 문제 1개 생성")
            st.success(f"{i}번 완료")
            st.write(response.text)
            time.sleep(4) # RPM 한도 보존을 위한 여유 있는 대기
            
    except Exception as e:
        err = str(e)
        if "404" in err:
            st.error("🚫 모델명을 다시 확인해주세요. 'models/'를 빼고 입력해야 합니다.")
        elif "429" in err:
            st.error("🚨 일일 한도 초과! 다른 구글 계정의 API 키가 필요합니다.")
        else:
            st.error(f"오류 발생: {e}")

if st.sidebar.button("🚀 수정 버전 발간 시작"):
    run_fixed_generation("수학 I", 5, selected_model, emergency_key)
