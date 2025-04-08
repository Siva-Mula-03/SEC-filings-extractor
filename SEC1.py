import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import os
import xml.etree.ElementTree as ET
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns

# Configuration
SEC_API = "https://data.sec.gov/submissions"
BASE_URL = "https://www.sec.gov"
HEADERS = {'User-Agent': 'Financial Analyst admin@analytics.com'}
GROQ_API_KEY = "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"

# Initialize session state
if 'financial_data' not in st.session_state:
    st.session_state.financial_data = []

# Core Functions
@st.cache_data(show_spinner=False)
def get_company_filings(cik, form_type, start_date, end_date):
    """Fetch SEC filings with caching"""
    cik = cik.lstrip('0')
    try:
        response = requests.get(f"{SEC_API}/CIK{cik}.json", headers=HEADERS)
        response.raise_for_status()
        filings_data = response.json()
        
        filings = []
        for filing in filings_data['filings']['recent']:
            filing_date = datetime.strptime(filing['filingDate'], '%Y-%m-%d').date()
            if (filing['form'].upper() == form_type and 
                start_date <= filing_date <= end_date):
                filings.append({
                    'form': filing['form'],
                    'filingDate': filing_date,
                    'accessionNumber': filing['accessionNumber'].replace('-', ''),
                    'document': filing['primaryDocument']
                })
        return filings
    except Exception as e:
        st.error(f"Error fetching filings: {str(e)}")
        return []

def extract_xbrl_facts(filing_url):
    """Extract financial data from XBRL filings"""
    try:
        xbrl_url = filing_url.replace('-10q_', '-xbrl_').replace('.htm', '.xml')
        response = requests.get(xbrl_url, headers=HEADERS)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        ns = {'xbrli': 'http://www.xbrl.org/2003/instance',
              'us-gaap': 'http://fasb.org/us-gaap/2023-01-31'}
        
        facts = {}
        for concept in ['AssetsCurrent', 'LiabilitiesCurrent', 
                       'RevenueFromContractWithCustomer', 'NetIncomeLoss',
                       'EarningsPerShareBasic']:
            elem = root.find(f'.//us-gaap:{concept}', ns)
            if elem is not None:
                facts[concept] = {
                    'value': elem.text,
                    'context': elem.attrib.get('contextRef', ''),
                    'unit': elem.attrib.get('unitRef', 'USD'),
                    'decimals': elem.attrib.get('decimals', '0')
                }
        return facts
    except Exception as e:
        st.error(f"XBRL parsing error: {str(e)}")
        return {}

def process_with_groq(prompt):
    """Generate AI insights using Groq"""
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    data = {
        "model": "llama3-70b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"AI Analysis Error: {str(e)}"

# UI Components
def show_financial_analysis():
    """Main financial analysis interface"""
    st.header("🧠 AI-Powered Financial Analysis")
    
    col1, col2 = st.columns(2)
    with col1:
        cik = st.text_input("Enter Company CIK", "0000790652")
    with col2:
        report_type = st.selectbox("Select Report Type", ["10-Q", "10-K"])
    
    start_date = st.date_input("Start Date", value=datetime(2023, 1, 1))
    end_date = st.date_input("End Date", value=datetime(2024, 12, 31))
    
    if st.button("Analyze Filings"):
        with st.spinner("Processing SEC filings..."):
            filings = get_company_filings(cik, report_type, start_date, end_date)
            
            if filings:
                st.success(f"Found {len(filings)} {report_type} filings")
                financial_data = []
                
                for filing in filings[:3]:  # Limit to 3 filings for demo
                    acc_no = filing['accessionNumber']
                    doc_url = f"{BASE_URL}/Archives/edgar/data/{cik}/{acc_no}/{filing['document']}"
                    
                    with st.spinner(f"Analyzing {filing['filingDate']}..."):
                        facts = extract_xbrl_facts(doc_url)
                        if facts:
                            financial_data.append({
                                'date': filing['filingDate'],
                                'assets': float(facts.get('AssetsCurrent', {}).get('value', 0)),
                                'revenue': float(facts.get('RevenueFromContractWithCustomer', {}).get('value', 0)),
                                'eps': float(facts.get('EarningsPerShareBasic', {}).get('value', 0))
                            })
                
                if financial_data:
                    st.session_state.financial_data = pd.DataFrame(financial_data)
                    show_analysis_results(cik, report_type)
                else:
                    st.warning("No financial data could be extracted")
            else:
                st.warning("No filings found in selected date range")

def show_analysis_results(cik, report_type):
    """Display analysis results"""
    df = st.session_state.financial_data
    
    st.subheader("📈 Financial Performance")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Latest Assets", f"${df['assets'].iloc[-1]:,.0f}", 
                 f"{df['assets'].pct_change().iloc[-1]:.1%}")
    with col2:
        st.metric("Latest Revenue", f"${df['revenue'].iloc[-1]:,.0f}", 
                 f"{df['revenue'].pct_change().iloc[-1]:.1%}")
    with col3:
        st.metric("Latest EPS", f"${df['eps'].iloc[-1]:.2f}", 
                 f"{df['eps'].pct_change().iloc[-1]:.1%}")
    
    st.subheader("Trend Analysis")
    fig, ax = plt.subplots(figsize=(10, 6))
    df.set_index('date').plot(ax=ax)
    st.pyplot(fig)
    
    st.subheader("AI Insights")
    analysis_prompt = f"""
    Analyze financial trends for CIK {cik} ({report_type}):
    {df.to_markdown()}
    
    Provide:
    1. Key performance highlights
    2. Risk factors
    3. Growth opportunities
    4. Investor recommendations
    """
    insights = process_with_groq(analysis_prompt)
    st.markdown(insights)

# Main App
def main():
    st.set_page_config(page_title="SEC Analyzer Pro", layout="wide")
    st.title("🔍 SEC Filing Analyzer Pro")
    
    with st.sidebar:
        st.header("Navigation")
        task = st.radio("Select Task", [
            "Financial Analysis", 
            "10-Q Search", 
            "Document Extraction",
            "Code Files"
        ])
    
    if task == "Financial Analysis":
        show_financial_analysis()
    elif task == "10-Q Search":
        # Original 10-Q search functionality
        pass
    elif task == "Document Extraction":
        # Original document extraction
        pass
    elif task == "Code Files":
        # Original code files viewer
        pass

if __name__ == "__main__":
    main()
