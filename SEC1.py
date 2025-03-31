def extract_section(filing_url, section_name=None, end_marker=None):
    filing_url = validate_url(filing_url)
    if not filing_url:
        st.error("Invalid SEC filing URL.")
        return None

    try:
        response = requests.get(filing_url, headers=HEADERS)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        st.error(f"Request failed: {e}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    
    # If no section specified, extract all meaningful text
    if not section_name and not end_marker:
        # Extract all text content with proper line breaks
        all_text = soup.get_text('\n', strip=True)
        # Split into lines and filter empty ones
        return [line for line in all_text.split('\n') if line.strip()]
    
    # Section-based extraction
    extracted_lines = []
    capturing = False
    
    # Find all text elements in the document
    for element in soup.find_all(string=True):
        parent = element.parent
        if parent.name in ['script', 'style']:  # Skip scripts and styles
            continue
            
        text = element.strip()
        if not text:
            continue
            
        # Check if we should start capturing
        if section_name and section_name.lower() in text.lower():
            capturing = True
            
        # Check if we should stop capturing
        if end_marker and end_marker.lower() in text.lower():
            capturing = False
            break
            
        # Capture text if we're in the right section
        if capturing or (not section_name and not end_marker):
            # Split multi-line text and add line numbers
            lines = text.split('\n')
            for line in lines:
                if line.strip():
                    extracted_lines.append(line.strip())
    
    return extracted_lines if extracted_lines else None

# In the Streamlit UI (Task 2 section):
elif task == "Task 2: Document Extraction":
    st.header("📑 Extract SEC Document Section")
    filing_url = st.text_input("Enter SEC Filing URL", 
                             placeholder="https://www.sec.gov/Archives/edgar/data/...")
    
    with st.expander("Section Options (leave both blank for full extraction)"):
        col1, col2 = st.columns(2)
        with col1:
            section_name = st.text_input("Start Section (optional)", 
                                      placeholder="Item 1. Business")
        with col2:
            end_marker = st.text_input("End Section (optional)", 
                                     placeholder="Item 1A. Risk Factors")

    if st.button("Extract Document"):
        if filing_url:
            with st.spinner("Extracting document content..."):
                extracted_text = extract_section(filing_url, section_name, end_marker)

                if extracted_text:
                    st.success(f"Extracted {len(extracted_text)} lines of text!")
                    
                    # Create DataFrame with line numbers
                    df = pd.DataFrame({
                        'Line': range(1, len(extracted_text)+1),
                        'Content': extracted_text
                    })
                    
                    # Display first 100 lines with option to show more
                    st.dataframe(df.head(100), height=400)
                    
                    if len(extracted_text) > 100:
                        st.info(f"Showing first 100 of {len(extracted_text)} lines. Use download to get full content.")
                    
                    # Download options
                    st.download_button(
                        label="📥 Download as CSV",
                        data=df.to_csv(index=False).encode('utf-8'),
                        file_name="extracted_sections.csv",
                        mime='text/csv'
                    )
                    
                    st.download_button(
                        label="📄 Download as TXT",
                        data="\n".join(extracted_text).encode('utf-8'),
                        file_name="extracted_sections.txt",
                        mime='text/plain'
                    )
                else:
                    st.error("No content found. Try adjusting your section markers.")
        else:
            st.warning("Please enter a valid SEC filing URL")
