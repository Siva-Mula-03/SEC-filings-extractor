import streamlit as st
import requests
import pandas as pd
import zipfile
import io
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# SEC Base URL
BASE_URL = "https://www.sec.gov"

# Headers to avoid 403 Forbidden errors
HEADERS = {
    'User-Agent': 'Siva Nehesh - For Research - siva.nehesh@example.com',
    'Accept-Encoding': 'gzip, deflate',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Connection': 'keep-alive'
}

# Validate and fix SEC URLs
def validate_url(url):
    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None  # Invalid URL
    return url

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
                for part in parts:
                    if part.startswith('/Archives/edgar/data/'):
                        filings.append({
                            "Company": " ".join(parts[:-3]),
                            "CIK": parts[-3],
                            "Date": parts[-2],
                            "URL": urljoin(BASE_URL, part)
                        })
                        break
        return filings
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching filings: {e}")
        return []

# Function to create ZIP file for filings
def create_zip(filings):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filing in filings:
            fixed_url = validate_url(filing["URL"])
            if not fixed_url:
                continue  # Skip invalid URLs
            response = requests.get(fixed_url, headers=HEADERS, stream=True)
            if response.status_code == 200:
                zip_file.writestr(f"{filing['Company']}_{filing['Date']}.txt", response.text)
    zip_buffer.seek(0)
    return zip_buffer

# Function to extract SEC document sections with improved parsing
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

    if st.button("Fetch Filings", key="fetch_btn"):
        with st.spinner("Fetching filings..."):
            all_filings = []
            for q in quarters:
                filings = fetch_10q_filings(year, q)
                if filings:
                    all_filings.extend(filings)

            if all_filings:
                df = pd.DataFrame(all_filings)
                st.success(f"Found {len(df)} filings!")
                
                st.write("### Filter Results")
                query = st.text_input("Search by CIK, Company, or Date")
                if query:
                    df = df[df.apply(lambda row: query.lower() in str(row).lower(), axis=1)]
                    st.info(f"Filtered to {len(df)} filings")

                st.dataframe(df)
                
                # Improved download options
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📥 Download as CSV"):
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="Download CSV",
                            data=csv,
                            file_name=f"10Q_filings_{year}_Q{'-'.join(map(str, quarters))}.csv",
                            mime='text/csv'
                        )
                with col2:
                    if st.button("📦 Download as ZIP"):
                        zip_buffer = create_zip(all_filings)
                        st.download_button(
                            label="Download ZIP",
                            data=zip_buffer,
                            file_name=f"10Q_filings_{year}_Q{'-'.join(map(str, quarters))}.zip",
                            mime='application/zip'
                        )
            else:
                st.error("No filings found for the selected criteria.")

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

# Add some footer information
st.sidebar.markdown("---")
st.sidebar.markdown("""
**About this tool:**
- Extracts SEC filings and documents
- Data is sourced directly from SEC.gov
- For research purposes only
""")
