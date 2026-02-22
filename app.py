import streamlit as st
import google.generativeai as genai

# --- 1. 보안 설정 ---
st.set_page_config(page_title="API 모델 진단 도구", layout="wide")

st.title("🔍 내 API 키로 사용 가능한 모델 확인")

# Secrets에서 키를 가져오거나 화면에서 직접 입력받습니다.
if "PAID_API_KEY" in st.secrets:
    api_key = st.secrets["PAID_API_KEY"]
else:
    api_key = st.text_input("API 키가 설정되지 않았습니다. 여기에 입력하세요:", type="password")

if api_key:
    try:
        genai.configure(api_key=api_key)
        
        st.subheader("✅ 연결 성공! 사용 가능한 모델 목록:")
        
        # 구글 서버에서 사용 가능한 모델 리스트를 불러옵니다.
        models = genai.list_models()
        
        # 결과를 예쁘게 보여주기 위한 리스트 생성
        available_models = []
        for m in models:
            if 'generateContent' in m.supported_generation_methods:
                available_models.append({
                    "모델 이름(ID)": m.name,
                    "설명": m.description,
                    "버전": m.version
                })
        
        if available_models:
            # 표 형식으로 출력
            st.table(available_models)
            
            st.info("💡 위 표의 '모델 이름(ID)' 칸에 있는 이름을 코드의 genai.GenerativeModel('...') 안에 넣으시면 됩니다.")
            
            # 복사하기 편하게 리스트로도 제공
            st.write("---")
            st.write("📝 **복사용 모델명 리스트:**")
            for model in available_models:
                st.code(model["모델 이름(ID)"])
        else:
            st.warning("연결은 되었으나 사용할 수 있는 생성 모델이 없습니다.")
            
    except Exception as e:
        st.error(f"❌ 오류 발생: {e}")
        st.write("API 키가 유효하지 않거나 플랜 설정(결제 수단 등록 등)이 완료되지 않았을 수 있습니다.")
else:
    st.info("사이드바 또는 Secrets에 API 키를 등록해 주세요.")
