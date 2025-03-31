import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import openai
import re

# SEC Base URL
BASE_URL = "https://www.sec.gov"

# Headers to avoid 403 Forbidden errors
HEADERS = {
    'User-Agent': 'Company Name - Your Name - your.email@example.com',
    'Accept-Encoding': 'gzip, deflate',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Connection': 'keep-alive'
}

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

def get_document_url(filing_url):
    try:
        response = requests.get(filing_url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the table with filing documents
        documents_table = soup.find('table', {'class': 'tableFile'})
        if not documents_table:
            st.error("Could not find documents table in the filing")
            return None
            
        # Find the primary document (usually 10-Q)
        primary_doc = None
        for row in documents_table.find_all('tr')[1:]:  # Skip header row
            cols = row.find_all('td')
            if len(cols) >= 3:
                doc_type = cols[3].text.strip()
                if '10-Q' in doc_type or '10Q' in doc_type:
                    doc_href = cols[2].find('a')['href']
                    primary_doc = urljoin(filing_url, doc_href)
                    break
        
        if not primary_doc:
            # If no 10-Q found, get the first HTML document
            for row in documents_table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) >= 3:
                    doc_href = cols[2].find('a')['href']
                    if doc_href.endswith('.htm') or doc_href.endswith('.html'):
                        primary_doc = urljoin(filing_url, doc_href)
                        break
        
        return primary_doc
    except Exception as e:
        st.error(f"Error finding document URL: {str(e)}")
        return None

def extract_section_text(doc_url, start_section=None, end_section=None):
    try:
        response = requests.get(doc_url, headers=HEADERS)
        response.raise_for_status()
        
        # Handle both HTML and plain text documents
        if doc_url.endswith('.txt'):
            # For plain text filings
            text = response.text
            lines = [line.strip() for line in text.split('\n') if line.strip()]
        else:
            # For HTML filings
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'meta', 'link', 'nav', 'header', 'footer']):
                element.decompose()
            
            text = soup.get_text('\n', strip=True)
            lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if not start_section and not end_section:
            return lines
        
        start_idx = 0
        end_idx = len(lines)
        
        if start_section:
            start_pattern = re.compile(rf'\b{re.escape(start_section)}\b', re.IGNORECASE)
            for i, line in enumerate(lines):
                if start_pattern.search(line):
                    start_idx = i
                    break
        
        if end_section:
            end_pattern = re.compile(rf'\b{re.escape(end_section)}\b', re.IGNORECASE)
            for i, line in enumerate(lines[start_idx:], start=start_idx):
                if end_pattern.search(line):
                    end_idx = i
                    break
        
        return lines[start_idx:end_idx]
    except Exception as e:
        st.error(f"Extraction error: {str(e)}")
        return None

def process_with_ai(text, api_key):
    try:
        openai.api_key = api_key
        truncated_text = ' '.join(text[:3000]) if len(text) > 3000 else ' '.join(text)
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """You are a financial analyst expert in SEC filings. 
                Extract key headers and their corresponding values from the text. 
                Return only a markdown table with columns 'Header' and 'Value'.
                Preserve all numerical values exactly as they appear."""},
                {"role": "user", "content": f"Text: {truncated_text}"}
            ],
            temperature=0.3
        )
        
        table = response.choices[0].message['content']
        if '| Header' in table and '| Value' in table:
            return table
        return None
    except Exception as e:
        st.error(f"AI processing error: {str(e)}")
        return None

# Streamlit UI
st.set_page_config(page_title="SEC Filing Analyzer", layout="wide")
st.title("📊 SEC Filing & Document Extractor")

with st.sidebar:
    st.header("Configuration")
    task = st.radio("Select Task", ["Task 1: 10-Q Filings", "Task 2: Document Extraction"])
    
    if task == "Task 2: Document Extraction":
        st.markdown("---")
        st.subheader("AI Processing Options")
        use_ai = st.checkbox("Enable AI-powered structuring", value=True)
        if use_ai:
            api_key = st.text_input("OpenAI API Key", type="password",
                                  help="Get your key from platform.openai.com/account/api-keys")
        else:
            api_key = None

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
            st.session_state.filtered_df = st.session_state.df[
                st.session_state.df.apply(
                    lambda row: query.lower() in str(row).lower(), 
                    axis=1
                )
            ]
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
                txt = st.session_state.filtered_df.to_string(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download as TXT",
                    data=txt,
                    file_name=f"10Q_filings_{year}_Q{'-'.join(map(str, quarters))}.txt",
                    mime='text/plain'
                )

elif task == "Task 2: Document Extraction":
    st.header("📑 Extract SEC Document Section")
    
    with st.expander("ℹ️ How to use", expanded=True):
        st.write("""
        1. Paste a SEC filing URL (e.g., from 10-Q filings)
        2. Optionally specify section markers (like "Item 1. Business")
        3. Enable AI processing for structured data extraction
        4. Click "Extract Document"
        """)
    
    filing_url = st.text_input("Enter SEC Filing URL", 
                             placeholder="https://www.sec.gov/Archives/edgar/data/.../primary_doc.xml")
    
    col1, col2 = st.columns(2)
    with col1:
        section_name = st.text_input("Start Section (optional)", 
                                  placeholder="Item 1. Business")
    with col2:
        end_marker = st.text_input("End Section (optional)", 
                                 placeholder="Item 1A. Risk Factors")

    if st.button("Extract Document"):
        if filing_url:
            if not filing_url.startswith('https://www.sec.gov'):
                st.error("Please enter a valid SEC.gov URL")
                st.stop()
                
            with st.spinner("Locating document..."):
                doc_url = get_document_url(filing_url)
                
                if not doc_url:
                    st.error("Could not find document in this filing. Try a different URL.")
                    st.stop()
                    
                st.info(f"Found document at: {doc_url}")
                
                with st.spinner("Extracting content..."):
                    extracted_text = extract_section_text(doc_url, section_name, end_marker)

                    if not extracted_text:
                        st.error("No content extracted. Try different section markers.")
                        st.stop()
                        
                    st.success(f"Extracted {len(extracted_text)} lines of text!")
                    
                    if use_ai and api_key:
                        with st.spinner("🧠 Analyzing with AI..."):
                            ai_table = process_with_ai(extracted_text, api_key)
                            
                            if ai_table:
                                st.subheader("AI-Structured Data")
                                st.markdown(ai_table, unsafe_allow_html=True)
                                
                                try:
                                    df = pd.read_csv(pd.compat.StringIO(ai_table), 
                                                   sep="|", skipinitialspace=True)
                                    df = df.dropna(axis=1, how='all').iloc[1:]
                                    
                                    st.download_button(
                                        label="📥 Download Structured Data",
                                        data=df.to_csv(index=False),
                                        file_name="structured_data.csv",
                                        mime='text/csv'
                                    )
                                except Exception as e:
                                    st.error(f"Error processing AI output: {str(e)}")
                            else:
                                st.warning("AI processing failed. Showing raw text.")
                    else:
                        st.subheader("Extracted Text Content")
                        
                    df = pd.DataFrame({
                        'Line': range(1, len(extracted_text)+1),
                        'Content': extracted_text
                    })
                    st.dataframe(df.head(100), height=400)
                    
                    if len(extracted_text) > 100:
                        st.info(f"Showing first 100 of {len(extracted_text)} lines.")
                    
                    st.download_button(
                        label="📄 Download Full Text",
                        data="\n".join(extracted_text).encode('utf-8'),
                        file_name="extracted_text.txt",
                        mime='text/plain'
                    )
        else:
            st.warning("Please enter a valid SEC filing URL")

st.markdown("---")
st.markdown("""
<style>
.footer {
    font-size: 0.8rem;
    color: #666;
    text-align: center;
    margin-top: 2rem;
}
</style>
<div class="footer">
    SEC Filing Analyzer | Powered by Streamlit & OpenAI
</div>
""", unsafe_allow_html=True)
