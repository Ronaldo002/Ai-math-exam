import streamlit as st
import google.generativeai as genai
import asyncio

st.set_page_config(page_title="AI 모의고사 생성기", page_icon="🏎️", layout="wide")
st.title("🏎️ AI 수능 모의고사 생성기 (극한 병렬 모드)")
st.markdown("무료 API 한도(15명)를 꽉 채워 15명의 AI가 동시에 2문제씩 출제합니다!")

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
        .paper { max-width: 210mm; min-height: 1200mm; margin: 0 auto; background: white; padding: 20mm; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .header { text-align: center; border-bottom: 2px solid black; padding-bottom: 10px; margin-bottom: 20px; }
        .header h1 { margin: 0; font-size: 24px; font-weight: bold; }
        .header h2 { margin: 5px 0 0 0; font-size: 18px; font-weight: bold; }
        .twocolumn { column-count: 2; column-gap: 30px; column-rule: 1px solid #ccc; }
        .question { margin-bottom: 60px; page-break-inside: avoid; }
        .q-number { font-weight: bold; font-size: 1.1em; margin-right: 5px; }
        .options { display: flex; justify-content: space-between; margin-top: 15px; font-size: 0.9em; }
        .score { float: right; font-weight: bold; }
        @media print {
            body { background: white; }
            .paper { box-shadow: none; margin: 0; padding: 0; max-width: 100%; height: auto; }
        }
    </style>
</head>
<body>
    <div class="paper">
        <div class="header">
            <h1>2026학년도 대학수학능력시험 모의평가 문제지</h1>
            <h2>수학 영역</h2>
        </div>
        <div class="twocolumn">
            {content}
        </div>
    </div>
</body>
</html>
"""

async def fetch_questions(model, start_num, end_num, subject, difficulty):
    prompt = f"""
    너는 수능 수학 출제 위원이야. {subject} 과목의 모의고사 중 **{start_num}번부터 {end_num}번까지** 총 {end_num - start_num + 1}문제를 만들어. 난이도는 '{difficulty}'에 맞춰.
    오직 HTML 태그로만 출력하고, 설명이나 인사말은 절대 하지 마. 수식은 MathJax (\\( \\), \\[ \\])를 써.
    
    [특수 조건]
    - 인쇄 시 총 12페이지 분량이 넉넉히 나올 수 있도록 문항 사이에 <br><br><br><br>를 넣어 여백을 아주 길게 줄 것.
    - 만약 이 번호대 안에 17번 문항이 있다면 문제 내용에 [그림 추가] 공간을 반드시 표시할 것.
    - 만약 이 번호대 안에 26번 문항이 있다면 문제 내용에 [그래프 추가] 공간을 반드시 표시할 것.

    [출력 구조 예시]
    <div class="question">
        <span class="q-number">{start_num}.</span> 문제 내용... <span class="score">[3점]</span>
        <div class="options">
            <span>① 1</span><span>② 2</span><span>③ 3</span><span>④ 4</span><span>⑤ 5</span>
        </div>
    </div>
    """
    try:
        response = await model.generate_content_async(prompt)
        return response.text.replace('```html', '').replace('```', '')
    except Exception as e:
        # 에러 발생 시 프로그램이 멈추지 않고, 해당 번호대에만 에러 메시지를 표시합니다.
        return f"<p style='color:red; font-weight:bold;'>[⚠️ {start_num}~{end_num}번 생성 실패: API 무료 한도 초과]</p>"

async def generate_exam(model, total_questions, subject, difficulty):
    # 🔥 극단적 쥐어짜기 핵심: 2문제씩 쪼개서 최대 15명의 AI를 동원합니다!
    chunk_size = 2 
    tasks = []
    
    for i in range(1, total_questions + 1, chunk_size):
        start = i
        end = min(i + chunk_size - 1, total_questions)
        tasks.append(fetch_questions(model, start, end, subject, difficulty))
    
    results = await asyncio.gather(*tasks)
    return "".join(results)

st.sidebar.header("출제 옵션 설정")
subject = st.sidebar.selectbox("📚 과목 선택", ["미적분", "확률과 통계", "수학 I, II"])
num_questions_str = st.sidebar.radio("🔢 문항 수", ["5문항 (테스트용)", "10문항", "20문항", "30문항"])
difficulty = st.sidebar.select_slider("🔥 난이도", options=["개념 확인", "수능 실전형", "최상위권 킬러형"])

if st.sidebar.button("🚀 극한의 속도로 출제 시작"):
    try:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash') 
        
        total_q = int(num_questions_str.split("문항")[0])
        
        # 몇 명의 AI가 투입되는지 계산해서 화면에 보여줍니다.
        ai_count = (total_q + 1) // 2 
        st.info(f"⏳ {total_q}문항 출제 중... 🔥 무려 {ai_count}명의 AI 조수가 동시에 작업을 시작했습니다! (약 5~10초 소요)")
        
        html_content = asyncio.run(generate_exam(model, total_q, subject, difficulty))
        final_html = HTML_TEMPLATE.replace("{content}", html_content)
        
        st.success(f"🎉 단숨에 생성 완료! 총 {ai_count}명의 AI가 협력했습니다.")
        st.markdown("💡 **꿀팁:** 다운받은 파일을 브라우저로 열고, **`Ctrl + P` (인쇄) -> 'PDF로 저장'**을 누르세요.")
        
        st.download_button(
            label="📥 완성된 시험지 다운로드 (HTML)",
            data=final_html,
            file_name=f"수능_모의고사_{subject}_극한.html",
            mime="text/html"
        )

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
