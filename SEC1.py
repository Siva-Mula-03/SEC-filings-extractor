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
SEC_API = "https://data.sec.gov/submissions"
BASE_URL = "https://www.sec.gov"
HEADERS = {
    'User-Agent': 'Financial Analysis App contact@example.com',
    'Accept-Encoding': 'gzip, deflate',
    'Accept': 'application/json'
}

# Initialize session state
if 'selected_filing' not in st.session_state:
    st.session_state.selected_filing = None

def normalize_cik(cik):
    """Convert CIK to proper format (10 digits with leading zeros)"""
    try:
        return str(int(cik.strip())).zfill(10)
    except:
        return None

def get_company_filings(cik, form_type, start_date, end_date):
    try:
        # Remove leading zeros for API call
        api_cik = str(int(cik))  
        url = f"{SEC_API}/CIK{api_cik}.json"
        
        response = requests.get(url, headers=HEADERS)
        filings_data = response.json()
        
        filings = []
        for filing in filings_data['filings']['recent']:
            # Convert string dates properly
            filing_date = datetime.strptime(filing['filingDate'], '%Y-%m-%d').date()
            
            # Check both form type AND date range
            if (filing['form'].upper() == form_type.upper() and 
                filing_date >= start_date and 
                filing_date <= end_date):
                filings.append(filing)
        
        return filings

    except Exception as e:
        st.error(f"Error: {str(e)}")
        return []
        
def get_filing_url(cik, accession_number, document):
    """Construct proper SEC filing URL"""
    return f"{BASE_URL}/Archives/edgar/data/{cik.zfill(10)}/{accession_number}/{document}"

def extract_financial_data(filing_url):
    """Extract financial data from filing document"""
    try:
        response = requests.get(filing_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        # Check if this is an XBRL filing
        if '-xbrl_' in filing_url.lower() or '.xml' in filing_url.lower():
            return parse_xbrl_filing(response.content)
        else:
            return parse_html_filing(response.content)
            
    except Exception as e:
        st.error(f"Error extracting financial data: {str(e)}")
        return None

def parse_xbrl_filing(content):
    """Parse XBRL/XML financial data"""
    try:
        root = ET.fromstring(content)
        ns = {
            'xbrli': 'http://www.xbrl.org/2003/instance',
            'us-gaap': 'http://fasb.org/us-gaap/2023-01-31',
            'dei': 'http://xbrl.sec.gov/dei/2023-01-31'
        }
        
        data = {}
        # Common financial concepts to extract
        concepts = {
            'AssetsCurrent': 'current_assets',
            'LiabilitiesCurrent': 'current_liabilities',
            'RevenueFromContractWithCustomer': 'revenue',
            'NetIncomeLoss': 'net_income',
            'EarningsPerShareBasic': 'eps'
        }
        
        for concept, key in concepts.items():
            elem = root.find(f'.//us-gaap:{concept}', ns)
            if elem is not None and elem.text:
                try:
                    data[key] = float(elem.text.replace(',', ''))
                except ValueError:
                    continue
        
        return data
        
    except Exception as e:
        st.error(f"XBRL parsing error: {str(e)}")
        return None

def parse_html_filing(content):
    """Parse HTML financial statements"""
    try:
        soup = BeautifulSoup(content, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'meta', 'link', 'nav', 'header', 'footer']):
            element.decompose()
        
        # Find financial tables
        financial_data = {}
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    value = cells[-1].get_text(strip=True)
                    
                    # Look for common financial terms
                    if 'revenue' in label:
                        financial_data['revenue'] = parse_numeric_value(value)
                    elif 'net income' in label:
                        financial_data['net_income'] = parse_numeric_value(value)
                    elif 'assets' in label:
                        financial_data['assets'] = parse_numeric_value(value)
                    elif 'liabilities' in label:
                        financial_data['liabilities'] = parse_numeric_value(value)
        
        return financial_data
        
    except Exception as e:
        st.error(f"HTML parsing error: {str(e)}")
        return None

def parse_numeric_value(text):
    """Convert text to numeric value"""
    try:
        # Remove common non-numeric characters
        cleaned = re.sub(r'[^\d.-]', '', text)
        return float(cleaned)
    except:
        return None

def analyze_financials(financial_data):
    """Generate analysis of financial data"""
    if not financial_data:
        return "No financial data available for analysis"
    
    analysis = []
    
    # Basic metrics
    if 'revenue' in financial_data:
        analysis.append(f"Revenue: ${financial_data['revenue']:,.2f}")
    if 'net_income' in financial_data:
        analysis.append(f"Net Income: ${financial_data['net_income']:,.2f}")
    
    # Ratios
    if 'current_assets' in financial_data and 'current_liabilities' in financial_data:
        current_ratio = financial_data['current_assets'] / financial_data['current_liabilities']
        analysis.append(f"Current Ratio: {current_ratio:.2f} (Healthy if > 1.5)")
    
    # Profitability
    if 'revenue' in financial_data and 'net_income' in financial_data:
        profit_margin = (financial_data['net_income'] / financial_data['revenue']) * 100
        analysis.append(f"Profit Margin: {profit_margin:.2f}%")
    
    return "\n\n".join(analysis)


# Streamlit UI
def main():
    st.title("🔍 SEC Filing Analyzer Pro")
    
    # Sidebar for navigation
    st.sidebar.header("Navigation")
    analysis_type = st.sidebar.radio("Select Analysis Type", ["Company Filings", "Direct Filing Analysis"])
    
    if analysis_type == "Company Filings":
        st.header("📄 Company Filings Search")
        
        col1, col2 = st.columns(2)
        with col1:
            cik = st.text_input("Enter Company CIK", "320193")  # Apple's CIK as default
        with col2:
            report_type = st.selectbox("Select Report Type", ["10-Q", "10-K", "8-K"])
        
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
                
                if filings is None:
                    return
                    
                if filings:
                    st.success(f"Found {len(filings)} {report_type} filings")
                    
                    # Display filings in a table
                    df = pd.DataFrame(filings)
                    df['Filing Date'] = pd.to_datetime(df['filingDate']).dt.date
                    
                    # Add select button for each filing
                    df['Select'] = [f"<button onclick='selectFiling(\"{i}\")'>Analyze</button>" for i in range(len(filings))]
                    
                    # Display as HTML to allow button clicks
                    st.write(df[['form', 'Filing Date', 'Select']].to_html(escape=False), unsafe_allow_html=True)
                    
                    # Store filings in session state
                    st.session_state.filings = filings
                else:
                    st.warning(f"No {report_type} filings found for CIK {cik} in selected date range")
    
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

# JavaScript for handling button clicks
st.markdown("""
<script>
function selectFiling(index) {
    fetch('/select_filing', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({index: index}),
    })
    .then(response => response.json())
    .then(data => {
        window.location.href = '#analysis-section';
    });
}
</script>
""", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
