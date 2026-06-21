import streamlit as st
from PyPDF2 import PdfReader
import re
import pandas as pd
import json

from llm_client import get_client, get_model, get_available_providers

st.set_page_config(page_title="AI Resume Demo", page_icon=":book:", layout="wide")
st.title("AI Resume Demo :book:")
st.caption(
    "Demo-only UI. Flow chinh cua he thong la backend_cv -> ai_service/api.py -> /internal/cv/analyze."
)

if "provider" not in st.session_state:
    st.session_state.provider = "gemini"

col_config, _ = st.columns([1, 3])
with col_config:
    st.subheader("Settings")
    try:
        available_providers = get_available_providers()
        default_index = available_providers.index(st.session_state.provider) if st.session_state.provider in available_providers else 0
        selected_provider = st.selectbox(
            "Select LLM Provider",
            available_providers,
            index=default_index,
            help="Switch between Groq, Gemini, and GLM"
        )
        st.session_state.provider = selected_provider
        
        st.info(f"Current: {selected_provider.upper()} - {get_model(selected_provider)}")
    except ValueError as e:
        st.error(str(e))
        st.stop()

st.markdown("---")
st.markdown(
    "Upload your resume and get a quick **summary, skills snapshot, and improvement suggestions**."
)

uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])

if uploaded_file:
    pdf = PdfReader(uploaded_file)
    text = ""
    for page in pdf.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text

    text_clean = re.sub(r"(?<!\n)\n(?!\n)", " ", text)

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Resume Summary")
        st.text_area("Resume Text", value=text_clean, height=400)

    with col2:
        st.subheader("AI Analysis")
        if st.button("Analyze Resume"):
            with st.spinner("Analyzing resume..."):
                try:
                    client, provider = get_client(st.session_state.provider)
                    model = get_model(st.session_state.provider)
                    
                    prompt = f"""
You are resume expert.
Analyze the following resume provided:
1. Summary
2. List of key skills
3. Suggestions for improvement
4. A score out of 100 based on:
    - Skills match (30 points)
    - Experience & achievement (30 points)
    - Clarity & formatting (20 points)
    - Overall impression (20 points)
Also provide the individual category score in JSON format after "Score JSON:" marker.

Resume text:
{text_clean}
"""
                    if provider == "gemini":
                        model = f"models/{model}"
                    
                    response = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=700,
                    )
                    
                    result = response.choices[0].message.content
                    
                    if "Score JSON:" in result:
                        part = result.split("Score JSON:")
                        analysis_text = part[0]
                        st.write(analysis_text)
                        
                        if len(part) > 1:
                            try:
                                score_data = json.loads(part[1].strip())
                                st.subheader("Score Breakdown")
                                df = pd.DataFrame({
                                    "Category": list(score_data.keys()),
                                    "Score": list(score_data.values())
                                })
                                st.bar_chart(df.set_index("Category"))
                                
                                st.subheader("Overall Score")
                                total_score = sum(score_data.values())
                                st.progress(min(total_score / 100, 1.0))
                            except json.JSONDecodeError:
                                st.warning("Failed to parse score data JSON.")
                    else:
                        st.write(result)
                        
                except Exception as e:
                    st.error(f"Error: {str(e)}")
