import streamlit as st
import google.generativeai as genai
import os
import subprocess
import tempfile

st.set_page_config(page_title="AI 모의고사 생성기", page_icon="📝", layout="wide")
st.title("📝 AI 수능 모의고사 생성기")
st.markdown("클릭 한 번으로 나만의 맞춤형 수능 모의고사 PDF를 바로 다운로드하세요!")

LATEX_PREAMBLE = r"""\documentclass[10pt, a4paper, twocolumn]{article}
\usepackage{kotex}
\usepackage{amsmath, amssymb, amsfonts}
\usepackage{graphicx}
\usepackage{tikz} 
\usepackage[a4paper, left=1.4cm, right=1.4cm, top=2.2cm, bottom=2.0cm, columnsep=1.3cm, headheight=25pt, headsep=0.6cm]{geometry}
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0.7pt}
\renewcommand{\footrulewidth}{0pt}
\fancyhead[L]{\textbf{제2교시}}
\fancyhead[C]{\large\textbf{2026학년도 대학수학능력시험 모의평가 문제지}\\[4pt] \LARGE\textbf{수학 영역}}
\fancyhead[R]{\textbf{홀수형}\\[4pt] \textbf{\thepage}}
\fancyfoot[C]{}
\usepackage{tasks}
\settasks{label=\textcircled{\scriptsize\arabic*}, label-width=14pt, item-indent=16pt, after-item-skip=0.5em, label-offset=3pt}
\newcounter{qnumber}
\newcommand{\question}[2]{\stepcounter{qnumber}\noindent\textbf{\arabic{qnumber}.} #1 \hfill \textbf{[#2점]}\par\vspace{0.8em}}
\begin{document}
"""

st.sidebar.header("출제 옵션 설정")
subject = st.sidebar.selectbox("📚 과목 선택", ["미적분", "확률과 통계", "수학 I, II"])
num_questions = st.sidebar.radio("🔢 문항 수", ["5문항 (테스트용)", "10문항", "20문항", "30문항"])
difficulty = st.sidebar.select_slider("🔥 난이도", options=["개념 확인", "수능 실전형", "최상위권 킬러형"])

# [수정됨] 사용자에게 API 키를 묻지 않습니다!

if st.sidebar.button("🚀 모의고사 PDF 만들기"):
    try:
        # [수정됨] 클라우드 서버의 비밀 금고(secrets)에서 내 API 키를 몰래 꺼내옵니다.
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash') 
        
        prompt = f"""
        너는 수능 수학 출제 위원이야. {subject} 과목의 {num_questions} 수능 모의고사를 출제해. 난이도는 '{difficulty}'에 맞춰줘.
        반드시 아래의 LaTeX 구조를 100% 똑같이 유지해서 문제만 채워넣어.
        마지막 번호대 문항들은 단답형 주관식(정답 0~999)으로 출제해.
        설명이나 인사말은 절대 하지 말고 오직 \question 으로 시작하는 LaTeX 코드만 출력해.
        
        [반드시 지켜야 할 출력 구조 예시]
        \question{{1번 문제 내용...}}{{2}}
        \\begin{{tasks}}(5) \\task 1 \\task 2 \\task 3 \\task 4 \\task 5 \\end{{tasks}}
        \\vfill
        """
        
        status_text = st.info("⏳ AI 출제위원이 문제를 만들고 있습니다. (약 15~30초 소요)")
        response = model.generate_content(prompt)
        status_text.success("✅ 문제 출제 완료! PDF로 변환합니다.")
        
        tex_body = response.text.replace('```latex', '').replace('```', '')
        full_tex_code = LATEX_PREAMBLE + tex_body + "\n\\end{document}"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_file_path = os.path.join(tmpdir, "exam.tex")
            pdf_file_path = os.path.join(tmpdir, "exam.pdf")
            
            with open(tex_file_path, "w", encoding="utf-8") as f:
                f.write(full_tex_code)
            
            try:
                subprocess.run(["xelatex", "-interaction=nonstopmode", "exam.tex"], cwd=tmpdir, check=True, capture_output=True)
                
                with open(pdf_file_path, "rb") as pdf_file:
                    st.success("🎉 모든 작업이 완료되었습니다!")
                    st.download_button(
                        label="📥 완성된 PDF 다운로드",
                        data=pdf_file,
                        file_name=f"수능_모의고사_{subject}.pdf",
                        mime="application/pdf"
                    )
            except subprocess.CalledProcessError:
                 st.error("⚠️ PDF 변환 중 수식 오류가 발생했습니다.")
                 st.download_button(label="📄 오류 확인용 TeX 다운로드", data=full_tex_code, file_name="error_exam.tex", mime="text/plain")

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")