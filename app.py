import google.generativeai as genai

# 사용자님의 실제 PAID_API_KEY를 넣어주세요
genai.configure(api_key="여기에_API_키_입력") 

# 기존에 잘 쓰셨다던 2.5 모델 호출
model = genai.GenerativeModel('models/gemini-2.5-flash')

try:
    print("API 서버에 요청 중...")
    response = model.generate_content("API 정상 작동 테스트입니다. 대답해주세요.")
    print("✅ API 정상 작동 중:", response.text)
except Exception as e:
    print("\n🚨 [원인 발견] 구글 API 서버 에러 메시지 🚨")
    print(e)

