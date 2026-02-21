import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="AI 수능 모의고사 생성기", page_icon="📝", layout="wide")
st.title("📝 AI 수능 모의고사 생성기 (최적화 완료)")

# 1. 디자인 템플릿 (인쇄 최적화)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>수능 모의고사</title>
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        @page { size: A4; margin: 15mm; }
        body { font-family: 'Malgun Gothic', sans-serif; line-height: 1.6; background: #eee; }
        .paper { max-width: 210mm; margin: 0 auto; background: white; padding: 20mm; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .header { text-align: center; border-bottom: 2px solid black; padding-bottom: 10px; margin-bottom: 20px; }
        .twocolumn { column-count: 2; column-gap: 30px; column-rule: 1px solid #ccc; }
        .question { margin-bottom: 50px; page-break-inside: avoid; }
        .q-number { font-weight: bold; font-size: 1.1em; }
        .options { display: flex; justify-content: space-between; margin-top: 10px; }
        @media print { body { background: white; } .paper { box-shadow: none; margin: 0; padding: 0; } }
    </style>
</head>
<body>
    <div class="paper">
        <div class="header"><h1>2026학년도 대학수학능력시험 모의평가 문제지</h1><h2>수학 영역</h2></div>
        <div class="twocolumn">{content}</div>
    </div>
</body>
</html>
"""

# 2. AI 병렬 생성 함수
async def fetch_questions(model, start_num, end_num, subject, difficulty):
    prompt = f"너는 수능 출제 위원이야. {subject} 과목 {start_num}~{end_num}번 문제를 HTML로 만들어. 난이도: {difficulty}. 설명 없이 <div>태그만 출력해."
    try:
        # 구글 서버 차단 방지를 위한 미세한 지연
        await asyncio.sleep(0.5) 
        response = await model.generate_content_async(prompt)
        return response.text.replace('```html', '').replace('```', '')
    except Exception as e:
        return f"<p style='color:red;'> {start_num}번 문항 생성 실패: {e}</p>"

async def generate_exam(model, total_questions, subject, difficulty):
    # 5문제씩 6명의 AI가 동시에 작업 (무료 한도 내 최적 속도)
    chunk_size = 5 
    tasks = [fetch_questions(model, i, min(i+chunk_size-1, total_questions), subject, difficulty) 
             for i in range(1, total_questions + 1, chunk_size)]
    results = await asyncio.gather(*tasks)
    return "".join(results)

# 3. 사이드바 및 메인 화면
st.sidebar.header("출제 옵션 설정")
subject = st.sidebar.selectbox("📚 과목 선택", ["미적분", "확률과 통계", "수학 I, II"])
num_questions_str = st.sidebar.radio("🔢 문항 수", ["5문항 (테스트용)", "10문항", "30문항"])
difficulty = st.sidebar.select_slider("🔥 난이도", options=["개념 확인", "수능 실전형", "최상위권 킬러형"])

if st.sidebar.button("🚀 모의고사 생성 시작"):
    try:
        # [핵심] 최신 모델 이름 적용 및 Secrets 연결
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash-latest') # 모델 이름 수정 완료!
        
        total_q = int(num_questions_str.split("문항")[0])
        st.info(f"⏳ {total_q}문항을 생성 중입니다... (약 15~30초 소요)")
        
        # 병렬 생성 실행
        html_content = asyncio.run(generate_exam(model, total_q, subject, difficulty))
        final_html = HTML_TEMPLATE.replace("{content}", html_content)
        
        st.success("✅ 생성 완료! 아래 버튼을 눌러 저장하세요.")
        
        # 다운로드 버튼
        st.download_button(
            label="📥 HTML 파일 다운로드",
            data=final_html,
            file_name=f"수능_모의고사_{subject}.html",
            mime="text/html"
        )
        
        # 화면에 미리보기 출력
        st.components.v1.html(final_html, height=800, scrolling=True)

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
        st.info("API 키가 올바른지, 혹은 무료 한도를 초과하지 않았는지 확인해주세요.")
