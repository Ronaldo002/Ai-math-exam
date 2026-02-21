import streamlit as st
import google.generativeai as genai
import os
import subprocess
import tempfile

st.set_page_config(page_title="AI 모의고사 생성기", page_icon="📝", layout="wide")
st.title("📝 AI 수능 모의고사 생성기 (초고속 실시간 ⚡)")
st.markdown("답답한 기다림은 끝! AI가 문제를 출제하는 과정을 실시간으로 확인하세요.")

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

if st.sidebar.button("🚀 모의고사 PDF 만들기"):
    try:
        # 서버 금고에서 API 키 가져오기
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
        
        st.info("⏳ 1단계: AI가 문제를 출제하고 있습니다. (실시간 타이핑 중...)")
        
        # [핵심] 실시간 스트리밍 모드 켜기
        response = model.generate_content(prompt, stream=True)
        
        # 화면에 글자가 나타날 빈 공간(placeholder) 만들기
        placeholder = st.empty()
        full_text = ""
        
        # AI가 뱉어내는 글자를 쪼개서 화면에 실시간으로 더해주기
        for chunk in response:
            full_text += chunk.text
            placeholder.code(full_text, language='latex')
            
        st.success("✅ 1단계 완료: 문제 출제가 끝났습니다! 바로 PDF 변환을 시작합니다.")
        
        # 마크다운 찌꺼기 제거 후 템플릿과 합치기
        tex_body = full_text.replace('```latex', '').replace('```', '')
        full_tex_code = LATEX_PREAMBLE + tex_body + "\n\\end{document}"
        
        pdf_status = st.info("⏳ 2단계: 코드를 PDF로 변환하는 중입니다... (고속 변환기 작동 🚀)")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_file_path = os.path.join(tmpdir, "exam.tex")
            pdf_file_path = os.path.join(tmpdir, "exam.pdf")
            
            with open(tex_file_path, "w", encoding="utf-8") as f:
                f.write(full_tex_code)
            
            try:
                # [핵심] 무거운 xelatex 대신 가볍고 빠른 pdflatex 사용
                subprocess.run(["pdflatex", "-interaction=nonstopmode", "exam.tex"], cwd=tmpdir, check=True, capture_output=True)
                
                with open(pdf_file_path, "rb") as pdf_file:
                    pdf_status.success("🎉 모든 작업이 완료되었습니다!")
                    st.download_button(
                        label="📥 완성된 PDF 다운로드",
                        data=pdf_file,
                        file_name=f"수능_모의고사_{subject}.pdf",
                        mime="application/pdf"
                    )
            except subprocess.CalledProcessError:
                 pdf_status.error("⚠️ PDF 변환 중 수식 오류가 발생했습니다.")
                 st.download_button(label="📄 오류 확인용 TeX 다운로드", data=full_tex_code, file_name="error_exam.tex", mime="text/plain")

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
