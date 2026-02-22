for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        st.write(f"사용 가능 모델: {m.name}")
