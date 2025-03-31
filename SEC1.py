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
            # Attempt to find the document link (for example in a link with ".txt" or ".pdf" file)
            doc_link = None
            for link in soup.find_all("a", href=True):
                if ".txt" in link['href'] or ".pdf" in link['href']:
                    doc_link = urljoin(full_url, link['href'])
                    break
            return doc_link
        else:
            st.warning("No document found, the page may not contain any document.")
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
                st.success(f"Found {len(df)} filings!")
                
                # Filter results based on user input
                st.write("### Filter Results")
                query = st.text_input("Search by CIK, Form Type, or Date")
                if query:
                    df = df[df.apply(lambda row: query.lower() in str(row).lower(), axis=1)]
                    st.info(f"Filtered to {len(df)} filings")

                st.dataframe(df)

                # Download options for CSV
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
                    if st.button("📥 Download as TXT"):
                        txt = df.to_string(index=False).encode('utf-8')
                        st.download_button(
                            label="Download TXT",
                            data=txt,
                            file_name=f"10Q_filings_{year}_Q{'-'.join(map(str, quarters))}.txt",
                            mime='text/plain'
                        )
            else:
                st.error("No filings found for the selected criteria.")

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
