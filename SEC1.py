import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

# SEC Base URL
BASE_URL = "https://www.sec.gov"

# Headers to avoid 403 Forbidden errors
HEADERS = {
    'User-Agent': 'Siva Nehesh - For Research - siva.nehesh@example.com',
    'Accept-Encoding': 'gzip, deflate',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Connection': 'keep-alive'
}

# Function to fetch and filter 10-Q filings
def fetch_10q_filings(year, quarter):
    sec_url = f"{BASE_URL}/Archives/edgar/full-index/{year}/QTR{quarter}/crawler.idx"
    
    try:
        response = requests.get(sec_url, headers=HEADERS)
        response.raise_for_status()
        filings = []
        for line in response.text.split('\n'):
            if '10-Q' in line and 'edgar/data/' in line:
                parts = line.split()
                if len(parts) >= 5:
                    filings.append({
                        "Form Type": parts[-4],
                        "CIK": parts[-3],
                        "Date": parts[-2],
                        "URL": parts[-1]
                    })
        return filings
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching filings: {e}")
        return []

# Document extraction functions
def extract_section(url, start_section=None, end_section=None):
    try:
        full_url = urljoin(BASE_URL, url)
        response = requests.get(full_url, headers=HEADERS)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        doc_link = None
        for link in soup.find_all("a", href=True):
            if ".htm" in link['href'] or ".html" in link['href']:
                doc_link = urljoin(full_url, link['href'])
                break
        
        if not doc_link:
            return None

        doc_response = requests.get(doc_link, headers=HEADERS)
        doc_response.raise_for_status()
        doc_soup = BeautifulSoup(doc_response.text, 'html.parser')
        all_text = doc_soup.get_text('\n', strip=True).split('\n')
        
        if not start_section and not end_section:
            return [line for line in all_text if line.strip()]

        start_idx = 0
        end_idx = len(all_text)
        
        if start_section:
            for i, line in enumerate(all_text):
                if start_section.lower() in line.lower():
                    start_idx = i
                    break
        
        if end_section:
            for i, line in enumerate(all_text[start_idx:], start=start_idx):
                if end_section.lower() in line.lower():
                    end_idx = i
                    break
        
        return [line for line in all_text[start_idx:end_idx] if line.strip()]

    except Exception as e:
        st.error(f"Extraction error: {str(e)}")
        return None

# Function to identify and extract structured headers and values
def parse_headers_and_values(extracted_text):
    sections = []
    current_section = None
    content = []

    # Regular expressions to detect headers (Item numbers, etc.)
    header_regex = r"(Item \d+\.?[\d]*|Section \d+\.?[\d]*)"
    
    for line in extracted_text:
        header_match = re.match(header_regex, line)
        if header_match:
            if current_section:
                # Save the last section if it's not empty
                sections.append({"Header": current_section, "Content": "\n".join(content)})
            # Start a new section
            current_section = line.strip()
            content = []
        else:
            content.append(line.strip())

    # Append the last section if it exists
    if current_section and content:
        sections.append({"Header": current_section, "Content": "\n".join(content)})
    
    return sections

# Streamlit UI
st.title("📊 SEC Filing & Document Extractor")
task = st.sidebar.radio("Select Task", ["Task 1: 10-Q Filings", "Task 2: Document Extraction"])

if task == "Task 1: 10-Q Filings":
    st.header("🔍 Fetch 10-Q Filings")
    col1, col2 = st.columns(2)
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

    if 'df' in st.session_state:
        st.write("### Filter Results")
        query = st.text_input("Search by CIK, Form Type, or Date")
        
        if query:
            st.session_state.filtered_df = st.session_state.df[
                st.session_state.df.apply(
                    lambda row: query.lower() in str(row).lower(), 
                    axis=1
                )
            ]
            st.info(f"Filtered to {len(st.session_state.filtered_df)} filings")
        else:
            st.session_state.filtered_df = st.session_state.df.copy()

        st.dataframe(st.session_state.filtered_df)

        if not st.session_state.filtered_df.empty:
            col1, col2 = st.columns(2)
            with col1:
                csv = st.session_state.filtered_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download as CSV",
                    data=csv,
                    file_name=f"10Q_filings_{year}_Q{'-'.join(map(str, quarters))}.csv",
                    mime='text/csv',
                    key='csv_download'
                )
            with col2:
                txt = st.session_state.filtered_df.to_string(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download as TXT",
                    data=txt,
                    file_name=f"10Q_filings_{year}_Q{'-'.join(map(str, quarters))}.txt",
                    mime='text/plain',
                    key='txt_download'
                )

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

                    # Parsing the extracted text into structured sections
                    structured_sections = parse_headers_and_values(extracted_text)

                    # Convert structured data into a DataFrame for better visualization
                    if structured_sections:
                        structured_df = pd.DataFrame(structured_sections)
                        st.dataframe(structured_df)

                        # Download options
                        col1, col2 = st.columns(2)
                        with col1:
                            st.download_button(
                                label="📥 Download as CSV",
                                data=structured_df.to_csv(index=False).encode('utf-8'),
                                file_name="structured_sections.csv",
                                mime='text/csv',
                                key='csv_download_extract'
                            )
                        with col2:
                            st.download_button(
                                label="📄 Download as TXT",
                                data="\n".join([f"{row['Header']}\n{row['Content']}" for index, row in structured_df.iterrows()]).encode('utf-8'),
                                file_name="structured_sections.txt",
                                mime='text/plain',
                                key='txt_download_extract'
                            )
                else:
                    st.error("No content found. Try adjusting your section markers.")
        else:
            st.warning("Please enter a valid SEC filing URL")
