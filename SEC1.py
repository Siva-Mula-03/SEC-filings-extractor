# Streamlit UI
st.set_page_config(page_title="SEC Filing Analyzer", layout="wide")
st.title("📊 SEC Extract")

# Sidebar: Task Selection
with st.sidebar:
    st.header("Configuration")
    
    # Task Selection
    task = st.radio("Select Task", ["Task 1: 10-Q Filings", "Task 2: URL Text Extraction"])
    
    # Code Files Dropdown
    st.header("Code Files")
    file_option = st.selectbox(
        "Select Code/Documentation",
        [
            "Select File", 
            "combined_tsk1_tsk2_with_ui.py", 
            "simple_task1.py", 
            "simple_task2.py", 
            "documentation.pdf"
        ]
    )

# Debug: Check which task is selected
st.write(f"Selected Task: {task}")

if task == "Task 1: 10-Q Filings":
    st.header("🔍 Fetch 10-Q Filings")
    col1, col2 = st.columns([1, 2])
    with col1:
        year = st.number_input("Enter Year", min_value=1995, max_value=2025, value=2024)
    with col2:
        quarters = st.multiselect("Select Quarters", [1, 2, 3, 4], default=[1])

    if st.button("Fetch Filings"):
        with st.spinner("Fetching filings..."):
            all_filings = []
            for q in quarters:
                filings = fetch_10q_filings(year, q)
                if filings:
                    all_filings.extend(filings)

            if all_filings:
                df = pd.DataFrame(all_filings)
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
                df = df.sort_values(by='Date', ascending=False)
                st.session_state.df = df
                st.session_state.filtered_df = df.copy()
                st.success(f"Found {len(df)} filings!")
            else:
                st.warning("No filings found for the selected criteria")

    if 'df' in st.session_state:
        st.write("### Filter Results")
        query = st.text_input("Search by CIK, Form Type, or Date")
        
        if query:
            st.session_state.filtered_df = st.session_state.df[st.session_state.df.apply(
                lambda row: query.lower() in str(row).lower(), axis=1
            )]
            st.info(f"Filtered to {len(st.session_state.filtered_df)} filings")
        else:
            st.session_state.filtered_df = st.session_state.df.copy()

        st.dataframe(st.session_state.filtered_df, height=500)

        if not st.session_state.filtered_df.empty:
            col1, col2 = st.columns(2)
            with col1:
                csv = st.session_state.filtered_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download as CSV",
                    data=csv,
                    file_name=f"10Q_filings_{year}_Q{'-'.join(map(str, quarters))}.csv",
                    mime='text/csv'
                )
            with col2:
                txt = st.session_state.filtered_df.to_string(index=False)
                st.download_button(
                    label="📥 Download as Text",
                    data=txt,
                    file_name=f"10Q_filings_{year}_Q{'-'.join(map(str, quarters))}.txt",
                    mime='text/plain'
                )

elif task == "Task 2: URL Text Extraction":
    st.header("📑 Extract SEC Document Section")
    
    with st.expander("ℹ️ How to use", expanded=True):
        st.write("""
        1. Paste the SEC Filing URL for the document you want to extract from.
        2. Specify the sections of the document (optional).
        3. Extract the document and let the AI analyze its contents.
        """)

    # Debugging step: Ensure input fields are displayed
    doc_url = st.text_input("Enter SEC Filing URL", value="")
    start_section = st.text_input("Enter start section (optional)")
    end_section = st.text_input("Enter end section (optional)")

    if st.button("Extract Section"):
        if doc_url:
            with st.spinner("Extracting document..."):
                content = extract_section_text(doc_url, start_section, end_section)
                if not content:
                    st.warning("No content was extracted. Please check the URL and section names.")
                else:

                    st.write("### Extracted Content")
                    st.write("\n".join(content))
                    st.write("### Processing with AI...")
                    ai_results = process_with_groq(content)
                    if ai_results:
                        st.write("### AI Analysis Result")
                        st.markdown(ai_results)
                    else:
                        st.warning("AI processing did not return results.")
        else:
            st.warning("Please enter a valid SEC filing URL.")

# Display Code or Documentation based on user selection
if file_option != "Select File":
    file_path = f"data/{file_option}"
    
    try:
        with open(file_path, "r") as file:
            if file_option.endswith(".py"):
                # Display Python code with pretty formatting
                code = file.read()
                st.code(code, language='python')
            elif file_option.endswith(".pdf"):
                # Display PDF (since it's documentation)
                st.write("### Documentation")
                st.markdown(f'<embed src="{file_path}" width="100%" height="600px" type="application/pdf">', unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Error loading file: {e}")
