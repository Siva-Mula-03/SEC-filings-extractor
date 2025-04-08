import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
from datetime import datetime
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import seaborn as sns
import time

# Configuration
SEC_API = "https://data.sec.gov/submissions"
BASE_URL = "https://www.sec.gov"
HEADERS = {
    'User-Agent': 'Financial Analyst admin@analytics.com',
    'Accept-Encoding': 'gzip, deflate',
    'Accept': 'application/json'
}
GROQ_API_KEY = "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"

# Initialize session state
if 'financial_data' not in st.session_state:
    st.session_state.financial_data = []

# Core Functions
@st.cache_data(show_spinner=False)
def get_company_filings(cik, form_type, start_date, end_date):
    """Fetch SEC filings with proper CIK handling"""
    try:
        # Proper CIK formatting for API
        cik = cik.strip().lstrip('0')  # Remove leading zeros for API
        url = f"{SEC_API}/CIK{cik}.json"
        
        response = requests.get(url, headers=HEADERS)
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
                    'primaryDoc': filing['primaryDocument']
                })
        return filings
    
    except requests.exceptions.HTTPError as e:
        st.error(f"SEC API Error: {e.response.status_code} - {e.response.reason}")
        return []
    except Exception as e:
        st.error(f"Error fetching filings: {str(e)}")
        return []

def get_filing_url(cik, accession_number, document):
    """Construct proper SEC filing URL with 10-digit CIK"""
    return f"{BASE_URL}/Archives/edgar/data/{cik.zfill(10)}/{accession_number}/{document}"

def extract_xbrl_facts(filing_url):
    """Extract financial data from XBRL filings with error handling"""
    try:
        # Get XBRL URL from filing URL
        xbrl_url = filing_url.replace('-10q_', '-xbrl_').replace('.htm', '.xml')
        response = requests.get(xbrl_url, headers=HEADERS)
        response.raise_for_status()
        
        # Parse XML with proper namespaces
        root = ET.fromstring(response.content)
        ns = {
            'xbrli': 'http://www.xbrl.org/2003/instance',
            'us-gaap': 'http://fasb.org/us-gaap/2023-01-31',
            'dei': 'http://xbrl.sec.gov/dei/2023-01-31'
        }
        
        facts = {}
        # Common financial concepts to extract
        concepts = {
            'AssetsCurrent': 'assets',
            'LiabilitiesCurrent': 'liabilities',
            'RevenueFromContractWithCustomer': 'revenue',
            'NetIncomeLoss': 'net_income',
            'EarningsPerShareBasic': 'eps',
            'EntityCommonStockSharesOutstanding': 'shares'
        }
        
        for concept, key in concepts.items():
            elem = root.find(f'.//us-gaap:{concept}', ns)
            if elem is not None:
                facts[key] = {
                    'value': elem.text,
                    'context': elem.attrib.get('contextRef', ''),
                    'unit': elem.attrib.get('unitRef', 'USD'),
                    'decimals': elem.attrib.get('decimals', '0')
                }
        
        # Add filing metadata
        elem = root.find('.//dei:DocumentType', ns)
        if elem is not None:
            facts['document_type'] = elem.text
            
        elem = root.find('.//dei:DocumentPeriodEndDate', ns)
        if elem is not None:
            facts['period_end'] = elem.text
            
        return facts
    
    except Exception as e:
        st.error(f"XBRL parsing error: {str(e)}")
        return {}

def process_with_groq(prompt):
    """Generate AI insights using Groq with error handling"""
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    data = {
        "model": "llama3-70b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"AI Analysis Error: {str(e)}"

# UI Components
def show_financial_analysis():
    """Main financial analysis interface"""
    st.header("🧠 AI-Powered Financial Analysis")
    
    col1, col2 = st.columns(2)
    with col1:
        cik = st.text_input("Enter Company CIK", "0000790652", 
                           help="Example: Apple = 0000320193, Microsoft = 0000789019")
    with col2:
        report_type = st.selectbox("Select Report Type", ["10-Q", "10-K"])
    
    col3, col4 = st.columns(2)
    with col3:
        start_date = st.date_input("Start Date", value=datetime(2023, 1, 1))
    with col4:
        end_date = st.date_input("End Date", value=datetime(2024, 12, 31))
    
    if st.button("Analyze Filings"):
        with st.spinner("Processing SEC filings..."):
            # Get filings with proper CIK handling
            filings = get_company_filings(cik, report_type, start_date, end_date)
            
            if filings:
                st.success(f"Found {len(filings)} {report_type} filings")
                financial_data = []
                
                # Process up to 3 most recent filings
                for filing in filings[:3]:
                    # Construct proper filing URL
                    filing_url = get_filing_url(
                        cik,
                        filing['accessionNumber'],
                        filing['primaryDoc']
                    )
                    
                    with st.spinner(f"Analyzing {filing['filingDate']}..."):
                        # Add delay to respect SEC rate limits
                        time.sleep(1)
                        
                        # Extract financial facts
                        facts = extract_xbrl_facts(filing_url)
                        
                        if facts:
                            # Convert to numeric values
                            try:
                                financial_data.append({
                                    'date': filing['filingDate'],
                                    'assets': float(facts.get('assets', {}).get('value', 0)),
                                    'revenue': float(facts.get('revenue', {}).get('value', 0)),
                                    'eps': float(facts.get('eps', {}).get('value', 0)),
                                    'shares': float(facts.get('shares', {}).get('value', 0)),
                                    'url': filing_url
                                })
                            except (ValueError, AttributeError):
                                continue
                
                if financial_data:
                    st.session_state.financial_data = pd.DataFrame(financial_data)
                    show_analysis_results(cik, report_type)
                else:
                    st.warning("No financial data could be extracted")
            else:
                st.warning("No filings found in selected date range")

def show_analysis_results(cik, report_type):
    """Display analysis results with visualizations"""
    df = st.session_state.financial_data
    
    # Metrics Section
    st.subheader("📈 Financial Performance")
    cols = st.columns(4)
    with cols[0]:
        st.metric("Latest Assets", f"${df['assets'].iloc[-1]:,.0f}", 
                 f"{df['assets'].pct_change().iloc[-1]:.1%}")
    with cols[1]:
        st.metric("Latest Revenue", f"${df['revenue'].iloc[-1]:,.0f}", 
                 f"{df['revenue'].pct_change().iloc[-1]:.1%}")
    with cols[2]:
        st.metric("Latest EPS", f"${df['eps'].iloc[-1]:.2f}", 
                 f"{df['eps'].pct_change().iloc[-1]:.1%}")
    with cols[3]:
        st.metric("Shares Outstanding", f"{df['shares'].iloc[-1]:,.0f}")
    
    # Trend Visualization
    st.subheader("Trend Analysis")
    fig, ax = plt.subplots(figsize=(10, 6))
    df.set_index('date').plot(y=['assets', 'revenue'], ax=ax)
    plt.title("Assets vs Revenue Trend")
    plt.ylabel("USD")
    st.pyplot(fig)
    
    # AI Insights
    st.subheader("🧠 AI Analysis")
    analysis_prompt = f"""
    Analyze financial trends for CIK {cik} ({report_type}):
    {df.to_markdown()}
    
    Provide concise analysis covering:
    1. Key performance highlights
    2. Notable trends and changes
    3. Potential risk factors
    4. Investor recommendations
    
    Format with bullet points and keep under 500 words.
    """
    
    with st.spinner("Generating AI insights..."):
        insights = process_with_groq(analysis_prompt)
        st.markdown(insights)
    
    # Filing Links
    st.subheader("🔗 Full Filing Documents")
    for idx, row in df.iterrows():
        st.markdown(f"[{report_type} - {row['date']}]({row['url']})")

# Main App
def main():
    st.set_page_config(page_title="SEC Analyzer Pro", layout="wide")
    st.title("🔍 SEC Filing Analyzer Pro")
    
    with st.sidebar:
        st.header("Navigation")
        task = st.radio("Select Task", [
            "Financial Analysis", 
            "View All Filings",
            "Document Extraction"
        ])
        
        st.markdown("---")
        st.markdown("**Example CIKs:**")
        st.markdown("- Apple: 0000320193")
        st.markdown("- Microsoft: 0000789019")
        st.markdown("- Amazon: 0001018724")
    
    if task == "Financial Analysis":
        show_financial_analysis()
    elif task == "View All Filings":
        cik = st.text_input("Enter CIK to view all filings", "0000790652")
        if cik:
            st.markdown(f"[View All Filings for CIK {cik}](https://www.sec.gov/edgar/browse/?CIK={cik.zfill(10)})")
    elif task == "Document Extraction":
        st.warning("Document extraction feature coming soon!")

if __name__ == "__main__":
    main()
