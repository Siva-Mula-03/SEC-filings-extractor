import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# SEC Base URL
BASE_URL = "https://www.sec.gov"

# Headers to avoid 403 Forbidden errors
HEADERS = {
    'User-Agent': 'Siva Nehesh - For Research - siva.nehesh@example.com',
    'Accept-Encoding': 'gzip, deflate',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Connection': 'keep-alive'
}

# Function to fetch and filter 10-Q filings for a specific year and quarter
def fetch_10q_filings(year, quarter):
    # The URL to access the relevant quarter's data
    sec_url = f"{BASE_URL}/Archives/edgar/full-index/{year}/QTR{quarter}/crawler.idx"
    
    try:
        # Make the HTTP request to fetch the data
        response = requests.get(sec_url, headers=HEADERS)
        response.raise_for_status()  # Raise error for bad responses (e.g., 404)

        filings = []
        for line in response.text.split('\n'):
            if '10-Q' in line and 'edgar/data/' in line:
                parts = line.split()
                # We know the last part is URL, second-last is Date, and third-last is CIK
                if len(parts) >= 5:  # Ensure there are enough parts in the line
                    form_type = parts[-4]  # Form type (should be '10-Q' for our case)
                    cik = parts[-3]
                    date_filed = parts[-2]
                    url = parts[-1]  # Last part is the URL
                    filings.append({
                        "Form Type": form_type,
                        "CIK": cik,
                        "Date": date_filed,
                        "URL": url  # Full URL as it is
                    })
        return filings
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching filings: {e}")
        return []

# Task 2: Extract documents based on SEC 10-Q URL
def fetch_document_from_url(url):
    try:
        # Build the full URL
        full_url = urljoin(BASE_URL, url)
        response = requests.get(full_url, headers=HEADERS)
        response.raise_for_status()

        # Check if it's an HTML document
        if "text/html" in response.headers['Content-Type']:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the document link
            doc_link = None
            for link in soup.find_all("a", href=True):
                if ".txt" in link['href'] or ".htm" in link['href'] or ".html" in link['href']:
                    doc_link = urljoin(full_url, link['href'])
                    break
            
            if doc_link:
                # Fetch the actual document content
                doc_response = requests.get(doc_link, headers=HEADERS)
                doc_response.raise_for_status()
                
                # Parse the document content
                doc_soup = BeautifulSoup(doc_response.text, 'html.parser')
                
                # Extract key information sections
                info_sections = {
                    "COMPANY INFORMATION": [],
                    "FILING INFORMATION": [],
                    "FINANCIAL DATA": [],
                    "BUSINESS OVERVIEW": []
                }
                
                # Find all tables in the document
                tables = doc_soup.find_all('table')
                
                # Parse tables for key information
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['th', 'td'])
                        if len(cells) == 2:  # Key-value pairs
                            key = cells[0].get_text(strip=True).upper()
                            value = cells[1].get_text(strip=True)
                            
                            # Categorize the information
                            if 'COMPANY' in key or 'NAME' in key or 'ADDRESS' in key:
                                info_sections["COMPANY INFORMATION"].append((key, value))
                            elif 'FILING' in key or 'DATE' in key or 'PERIOD' in key:
                                info_sections["FILING INFORMATION"].append((key, value))
                            elif 'REVENUE' in key or 'INCOME' in key or 'ASSET' in key:
                                info_sections["FINANCIAL DATA"].append((key, value))
                            else:
                                info_sections["BUSINESS OVERVIEW"].append((key, value))
                
                # Display the information in pretty tables
                st.success("Document found! Here's the extracted information:")
                
                for section, items in info_sections.items():
                    if items:  # Only show sections with content
                        st.subheader(section)
                        
                        # Create a dataframe for better display
                        df = pd.DataFrame(items, columns=["Field", "Value"])
                        
                        # Apply some styling
                        st.dataframe(
                            df.style
                            .set_properties(**{'text-align': 'left'})
                            .set_table_styles([{
                                'selector': 'th',
                                'props': [('background-color', '#f0f2f6'), 
                                         ('font-weight', 'bold')]
                            }]),
                            height=min(len(items)*35 + 35, 500),  # Dynamic height
                            use_container_width=True
                        )
                
                st.markdown(f"[Download Full Document]({doc_link})")
                return doc_link
            else:
                st.warning("No document link found on the page.")
                return None
        else:
            st.warning("The URL doesn't point to an HTML document.")
            return None
            
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching document: {e}")
        return None

# Streamlit UI
st.title("📊 SEC Filing & Document Extractor")
task = st.sidebar.radio("Select Task", ["Task 1: 10-Q Filings", "Task 2: Extract Document"])

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
                
                # Ensure Date is in datetime format
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                
                # Remove time (00:00:00) from the Date
                df['Date'] = df['Date'].dt.date
                
                # Sort by Date in descending order
                df = df.sort_values(by='Date', ascending=False)

                st.success(f"Found {len(df)} filings!")
                
                # Store the dataframe in session state
                st.session_state.df = df
                st.session_state.filtered_df = df.copy()

    # Display filter and results if dataframe exists
    if 'df' in st.session_state:
        st.write("### Filter Results")
        query = st.text_input("Search by CIK, Form Type, or Date", key="search_query")
        
        # Apply filter when query changes
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

        # Display the current dataframe
        st.dataframe(st.session_state.filtered_df)

        # Download buttons (always visible if data exists)
        if not st.session_state.filtered_df.empty:
            col1, col2 = st.columns(2)
            with col1:
                # CSV Download
                csv = st.session_state.filtered_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download as CSV",
                    data=csv,
                    file_name=f"10Q_filings_{year}_Q{'-'.join(map(str, quarters))}.csv",
                    mime='text/csv',
                    key='csv_download'
                )
            with col2:
                # TXT Download
                txt = st.session_state.filtered_df.to_string(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download as TXT",
                    data=txt,
                    file_name=f"10Q_filings_{year}_Q{'-'.join(map(str, quarters))}.txt",
                    mime='text/plain',
                    key='txt_download'
                )

elif task == "Task 2: Extract Document":
    st.header("🔍 Extract Document from 10-Q URL")
    url_input = st.text_input("Enter SEC 10-Q Filing URL", "https://www.sec.gov/Archives/edgar/data/320193/000032019323000065/")
    
    if st.button("Fetch Document"):
        with st.spinner("Fetching document..."):
            doc_link = fetch_document_from_url(url_input)
            if doc_link:
                st.success("Document found! You can download it here:")
                st.markdown(f"[Download Document]({doc_link})")
            else:
                st.error("No document found for the given filing URL.")
