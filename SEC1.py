import streamlit as st
import requests
import pandas as pd
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

# Extract SEC document section with improved parsing
def extract_sec_filing_details(filing_url):
    """Extract and structure SEC filing details from the filing page"""
    try:
        response = requests.get(filing_url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract header information
        header_info = {
            'Form Type': extract_field(soup, 'Form Type'),
            'SEC Accession No.': extract_field(soup, 'SEC Accession No.'),
            'Filing Date': extract_field(soup, 'Filing Date'),
            'Accepted': extract_field(soup, 'Accepted'),
            'Documents': extract_field(soup, 'Documents'),
            'Period of Report': extract_field(soup, 'Period of Report'),
            'Company Name': extract_field(soup, 'Company Name'),
            'CIK': extract_field(soup, 'CIK'),
            'SIC': extract_field(soup, 'SIC')
        }
        
        # Extract document format files
        doc_tables = soup.find_all('table')
        document_files = []
        data_files = []
        
        if len(doc_tables) > 0:
            document_files = parse_file_table(doc_tables[0])
        if len(doc_tables) > 1:
            data_files = parse_file_table(doc_tables[1])
        
        return {
            'header': header_info,
            'document_files': document_files,
            'data_files': data_files
        }
    except Exception as e:
        st.error(f"Error extracting filing details: {e}")
        return None

def extract_field(soup, field_name):
    """Extract specific field from the filing page"""
    try:
        element = soup.find(string=re.compile(field_name))
        if element:
            return element.find_next('td').get_text(strip=True)
    except:
        return None
    return None

def parse_file_table(table):
    """Parse document or data files table"""
    rows = []
    for row in table.find_all('tr')[1:]:  # Skip header row
        cols = row.find_all('td')
        if len(cols) >= 4:  # Ensure we have all columns
            rows.append({
                'Seq': cols[0].get_text(strip=True),
                'Description': cols[1].get_text(strip=True),
                'Document': cols[2].get_text(strip=True),
                'Type': cols[3].get_text(strip=True),
                'Size': cols[4].get_text(strip=True) if len(cols) > 4 else ''
            })
    return rows

# In the Streamlit UI (Task 2 section):
elif task == "Task 2: Document Extraction":
    st.header("📑 SEC Filing Document Explorer")
    
    filing_url = st.text_input("Enter SEC Filing URL", 
                             placeholder="https://www.sec.gov/Archives/edgar/data/...")
    
    if st.button("Analyze Filing"):
        if filing_url:
            with st.spinner("Extracting filing details..."):
                filing_data = extract_sec_filing_details(filing_url)
                
                if filing_data:
                    # Display header information
                    st.subheader("Filing Information")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("""
                        **Form Type:** {form_type}  
                        **Accession No.:** {accession_no}  
                        **Filing Date:** {filing_date}  
                        **Accepted:** {accepted}  
                        **Documents:** {documents}
                        """.format(**filing_data['header']))
                    
                    with col2:
                        st.markdown("""
                        **Period of Report:** {period}  
                        **Company:** {company}  
                        **CIK:** {cik}  
                        **SIC:** {sic}
                        """.format(**filing_data['header']))
                    
                    # Display document files
                    st.subheader("Document Format Files")
                    doc_df = pd.DataFrame(filing_data['document_files'])
                    st.dataframe(doc_df)
                    
                    # Display data files
                    st.subheader("Data Files")
                    data_df = pd.DataFrame(filing_data['data_files'])
                    st.dataframe(data_df)
                    
                    # Download options
                    st.download_button(
                        label="📥 Download Full Filing Data (JSON)",
                        data=json.dumps(filing_data, indent=2),
                        file_name="filing_data.json",
                        mime='application/json'
                    )
                else:
                    st.error("Could not extract filing details. Please check the URL.")
        else:
            st.warning("Please enter a valid SEC filing URL")

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
            # Fetch and display filings (use previously defined fetch_10q_filings and display logic)
            pass  # Replace with your logic

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
                    st.write("### Extracted Document Content")
                    st.markdown("Here are the first 100 lines of the extracted content:")
                    st.dataframe(df.head(100), height=400)
                    
                    if len(extracted_text) > 100:
                        st.info(f"Showing first 100 of {len(extracted_text)} lines. Use download to get full content.")
                    
                    # Improved download options
                    st.write("### Download Extracted Content")
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
