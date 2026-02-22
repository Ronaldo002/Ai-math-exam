def generate_exam(subject, difficulty, count, email):
    # [핵심 수정] models/ 를 제거하여 'gemini-2.0-flash'로만 설정합니다.
    model = genai.GenerativeModel('gemini-2.0-flash')
    q_html_list, s_html_list = [], []
    
    progress_bar = st.progress(0)
    percent_text = st.empty()
    status_text = st.empty()
    
    for i in range(1, count + 1):
        percent_val = int((i / count) * 100)
        status_text.markdown(f"✍️ **{i}번 문항** 출제 중...")
        percent_text.markdown(f"📊 **진행률: {percent_val}%**")
        
        prompt = f"""
        수능 수학 {subject} {difficulty} 난이도 {i}번 문항을 출제하세요.
        인사말 없이 아래 형식만 지키세요.
        [문항]
        <div class='question'><span class='q-num'>{i}.</span> 문제 내용...</div>
        ---SPLIT---
        [해설]
        <div class='sol'><b>{i}번 해설:</b> 해설 내용...</div>
        """
        
        try:
            # 유료 API 호출
            response = model.generate_content(prompt)
            raw_text = response.text.replace("```html", "").replace("```", "").strip()
            
            if "---SPLIT---" in raw_text:
                parts = raw_text.split("---SPLIT---")
                q_html_list.append(parts[0].replace("[문항]", "").strip())
                s_html_list.append(parts[1].replace("[해설]", "").strip())
            else:
                q_html_list.append(f"<div class='question'><span class='q-num'>{i}.</span>{raw_text}</div>")
            
            progress_bar.progress(i / count)
            time.sleep(0.5)
        except Exception as e:
            # 에러 발생 시 사용자에게 명확한 메시지 전달
            st.error(f"❌ {i}번 생성 중 연결 오류: {e}")
            continue
            
    status_text.success(f"✅ {count}문항 발간이 모두 완료되었습니다!")
    percent_text.empty()
    
    # DB 업데이트 로직 (생략 가능)
    user_data = db.table('users').get(User.email == email)
    db.table('users').update({'count': user_data['count'] + 1}, User.email == email)
    
    return get_html_template(subject, "".join(q_html_list), "".join(s_html_list))
