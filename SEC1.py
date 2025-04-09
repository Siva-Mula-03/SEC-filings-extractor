import streamlit as st
st.set_page_config(page_title="SEC Filing Analyzer", layout="wide")
import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
from datetime import datetime
import time
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt

# Configuration
SEC_API = "https://data.sec.gov/api/xbrl/companyfacts"
SUBMISSIONS_API = "https://data.sec.gov/submissions"
BASE_URL = "https://www.sec.gov"
HEADERS = {
    'User-Agent': 'Financial Analysis App contact@example.com',
    'Accept-Encoding': 'gzip, deflate',
    'Accept': 'application/json'
}

def normalize_cik(cik):
    """Convert CIK to proper format (10 digits with leading zeros)"""
    try:
        return str(int(cik.strip())).zfill(10)
    except:
        return None

def get_company_filings(cik, form_type, start_date, end_date):
    try:
        normalized_cik = normalize_cik(cik)
        if not normalized_cik:
            st.error("Invalid CIK format")
            return None
            
        url = f"{SUBMISSIONS_API}/CIK{normalized_cik}.json"
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        
        if response.status_code != 200:
            st.error(f"SEC API Error: {response.status_code} - {response.text}")
            return None
            
        filings_data = response.json()
        filings = []
        
        # Process recent filings
        for filing in filings_data.get('filings', {}).get('recent', []):
            try:
                filing_date = datetime.strptime(filing['filingDate'], '%Y-%m-%d').date()
                if (filing['form'].upper() == form_type.upper() and 
                    start_date <= filing_date <= end_date):
                    filings.append({
                        'form': filing['form'],
                        'filingDate': filing_date,
                        'accessionNumber': filing['accessionNumber'],
                        'primaryDocument': filing['primaryDocument']
                    })
            except Exception as e:
                continue
                
        # Process historical filings if available
        if 'filings' in filings_data and 'files' in filings_data['filings']:
            for file_info in filings_data['filings']['files']:
                file_url = f"{SUBMISSIONS_API}/{file_info['name']}"
                file_response = requests.get(file_url, headers=HEADERS)
                if file_response.status_code == 200:
                    file_data = file_response.json()
                    for filing in file_data:
                        try:
                            filing_date = datetime.strptime(filing['filingDate'], '%Y-%m-%d').date()
                            if (filing['form'].upper() == form_type.upper() and 
                                start_date <= filing_date <= end_date):
                                filings.append({
                                    'form': filing['form'],
                                    'filingDate': filing_date,
                                    'accessionNumber': filing['accessionNumber'],
                                    'primaryDocument': filing['primaryDocument']
                                })
                        except:
                            continue
        
        if not filings:
            st.warning(f"No {form_type} filings found for CIK {cik} between {start_date} and {end_date}")
            return None
            
        return filings
        
    except Exception as e:
        st.error(f"Error fetching filings: {str(e)}")
        return None

def get_filing_url(cik, accession_number, document):
    """Construct proper SEC filing URL"""
    accession_no_dashes = accession_number.replace("-", "")
    return f"{BASE_URL}/Archives/edgar/data/{cik}/{accession_no_dashes}/{document}"

# ... [rest of your functions remain the same] ...

def main():
    st.title("🔍 SEC Filing Analyzer Pro")
    
    # Sidebar for navigation
    st.sidebar.header("Navigation")
    analysis_type = st.sidebar.radio("Select Analysis Type", ["Company Filings", "Direct Filing Analysis"])
    
    if analysis_type == "Company Filings":
        st.header("📄 Company Filings Search")
        
        col1, col2 = st.columns(2)
        with col1:
            cik = st.text_input("Enter Company CIK", "0000320193")  # Apple's CIK with proper formatting
        with col2:
            report_type = st.selectbox("Select Report Type", ["10-Q", "10-K", "8-K", "DEF 14A"])
        
        col3, col4 = st.columns(2)
        with col3:
            start_date = st.date_input("Start Date", value=datetime(2023, 1, 1))
        with col4:
            end_date = st.date_input("End Date", value=datetime.today())
        
        if st.button("Search Filings"):
            if not cik or not cik.strip().isdigit():
                st.error("Please enter a valid CIK number")
                return
                
            with st.spinner("Fetching SEC filings..."):
                filings = get_company_filings(cik, report_type, start_date, end_date)
                
                if filings:
                    st.success(f"Found {len(filings)} {report_type} filings")
                    
                    # Display filings in a table
                    df = pd.DataFrame(filings)
                    df['Filing Date'] = pd.to_datetime(df['filingDate']).dt.date
                    df['Document Link'] = df.apply(
                        lambda row: f"[View Filing]({get_filing_url(cik, row['accessionNumber'], row['primaryDocument'])})", 
                        axis=1
                    )
                    
                    # Display the dataframe with links
                    st.dataframe(
                        df[['form', 'Filing Date', 'Document Link']],
                        column_config={
                            "Document Link": st.column_config.LinkColumn("Filing Link")
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    # Store filings in session state
                    st.session_state.filings = filings
                    
    elif analysis_type == "Direct Filing Analysis":
        st.header("📑 Direct Filing Analysis")
        filing_url = st.text_input("Enter SEC Filing URL", "")
        
        if st.button("Analyze Filing") and filing_url:
            with st.spinner("Analyzing filing..."):
                financial_data = extract_financial_data(filing_url)
                
                if financial_data:
                    st.subheader("Financial Data")
                    st.json(financial_data)
                    
                    st.subheader("Financial Analysis")
                    analysis = analyze_financials(financial_data)
                    st.write(analysis)
                    
                    # Basic visualization
                    if 'revenue' in financial_data and 'net_income' in financial_data:
                        fig, ax = plt.subplots()
                        ax.bar(['Revenue', 'Net Income'], 
                              [financial_data['revenue'], financial_data['net_income']])
                        ax.set_ylabel('Amount ($)')
                        st.pyplot(fig)
                else:
                    st.error("Could not extract financial data from this filing")

if __name__ == "__main__":
    main()
