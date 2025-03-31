import streamlit as st
import requests
import pandas as pd
import zipfile
import io
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import nltk
nltk.download('punkt')
from nltk.tokenize import sent_tokenize


# Ensure necessary nltk data is downloaded
nltk.download('punkt')

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
                            "Company": "Unknown",
                            "CIK": "Unknown",
                            "Date": "Unknown",
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

# Function to extract SEC document sections
def extract_section(filing_url, section_name, end_marker):
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
    extracted_section = []
    capturing = False

    for element in soup.find_all(["p", "div", "table"]):
        text = element.get_text().strip()
        if section_name in text:
            capturing = True
        if capturing:
            extracted_section.append(element.prettify())
        if end_marker in text:
            break

    return extracted_section if extracted_section else None

# NLP-based extraction for financial highlights
def smart_extract(filing_url):
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

    text = BeautifulSoup(response.text, "html.parser").get_text()
    sentences = sent_tokenize(text)

    keywords = ["Revenue", "Net Income", "EPS", "Risk Factors", "Management Discussion"]
    financial_data = [s for s in sentences if any(k in s for k in keywords)]
    financial_data += [s for s in sentences if re.search(r"\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?", s)]

    return financial_data

# Streamlit UI
st.title("📊 SEC Filing & Document Extractor")
task = st.sidebar.radio("Select Task", ["Task 1: 10-Q Filings", "Task 2: Document Extraction"])

if task == "Task 1: 10-Q Filings":
    st.header("🔍 Fetch 10-Q Filings")
    year = st.number_input("Enter Year", min_value=1995, max_value=2025, value=2024)
    quarters = st.multiselect("Select Quarters", [1, 2, 3, 4], default=[1])

    if st.button("Fetch Filings"):
        all_filings = []
        for q in quarters:
            all_filings.extend(fetch_10q_filings(year, q))

        if all_filings:
            df = pd.DataFrame(all_filings)
            st.write("### Filter Results")
            query = st.text_input("Search by CIK, Company, or Date")
            if query:
                df = df[df.apply(lambda row: query.lower() in str(row).lower(), axis=1)]

            st.dataframe(df)
            zip_buffer = create_zip(all_filings)
            st.download_button("📥 Download ZIP", data=zip_buffer, file_name="10Q_filings.zip")
        else:
            st.error("No filings found.")

elif task == "Task 2: Document Extraction":
    st.header("📑 Extract SEC Document Section")
    filing_url = st.text_input("Enter SEC Filing URL")
    section_name = st.text_input("Start Section (Leave blank for full extraction)")
    end_marker = st.text_input("End Section (Leave blank for full extraction)")

    if st.button("Extract Section"):
        if section_name and end_marker:
            extracted_text = extract_section(filing_url, section_name, end_marker)
        else:
            extracted_text = smart_extract(filing_url)

        if extracted_text:
            df = pd.DataFrame({"Extracted Text": extracted_text})
            st.write("### Extracted Information")
            st.dataframe(df)
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download CSV", data=csv, file_name="extracted_data.csv")
        else:
            st.error("No relevant data found.")
