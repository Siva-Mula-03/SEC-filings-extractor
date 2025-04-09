# Configuration must be at the very top
import streamlit as st
st.set_page_config(
    page_title="SEC Filing Analyzer Pro", 
    layout="wide", 
    page_icon="📈",
    initial_sidebar_state="expanded"
)

import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
from datetime import datetime
import xml.etree.ElementTree as ET
import plotly.express as px
from urllib.parse import urljoin

# Configuration
SEC_API = "https://data.sec.gov/submissions"
BASE_URL = "https://www.sec.gov"
HEADERS = {
    'User-Agent': 'Financial Analysis App contact@example.com',
    'Accept-Encoding': 'gzip, deflate',
    'Accept': 'application/json'
}

# Initialize session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'selected_filing' not in st.session_state:
    st.session_state.selected_filing = None
if 'financial_data' not in st.session_state:
    st.session_state.financial_data = None
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False

# Dark mode CSS
st.markdown("""
<style>
:root {
    --primary-color: #1F1F1F;
    --secondary-color: #2D2D2D;
    --text-color: #FFFFFF;
    --accent-color: #00FF88;
}

/* Main content styling */
.stApp {
    background-color: var(--primary-color);
    color: var(--text-color);
}

/* Sidebar styling */
[data-testid="stSidebar"] {
    background-color: var(--secondary-color) !important;
    border-right: 1px solid #3D3D3D;
}

/* Chat interface styling */
.chat-message {
    padding: 12px;
    border-radius: 8px;
    margin: 8px 0;
    max-width: 80%;
    background-color: #2D2D2D;
    color: var(--text-color);
}

.user-message {
    margin-left: 20%;
    border: 1px solid #3D3D3D;
}

.bot-message {
    margin-right: 20%;
    background-color: #1A1A1A;
}

/* Input fields */
.stTextInput>div>div>input {
    background-color: #2D2D2D;
    color: var(--text-color);
    border: 1px solid #3D3D3D;
}

/* Buttons */
.stButton>button {
    background-color: var(--accent-color);
    color: #1F1F1F;
    border: none;
    font-weight: bold;
}

.stButton>button:hover {
    background-color: #00CC6A !important;
}

/* Cards */
.card {
    background: var(--secondary-color);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    border: 1px solid #3D3D3D;
}

/* Plotly chart styling */
.js-plotly-plot .plotly, .js-plotly-plot .plotly div {
    background-color: var(--secondary-color) !important;
}
</style>
""", unsafe_allow_html=True)

# --------------------------
# Core Application Functions
# --------------------------

def normalize_cik(cik):
    """Convert CIK to 10-digit format"""
    try:
        return str(int(cik.strip())).zfill(10)
    except:
        return None

def get_company_filings(cik, form_type, start_date, end_date):
    """Retrieve SEC filings for a company"""
    try:
        normalized_cik = normalize_cik(cik)
        if not normalized_cik:
            st.error("Invalid CIK format")
            return None
            
        url = f"{SEC_API}/CIK{normalized_cik}.json"
        response = requests.get(url, headers=HEADERS, timeout=15)
        
        if response.status_code != 200:
            st.error(f"SEC API Error: {response.status_code}")
            return None
            
        filings_data = response.json()
        filings = []
        
        recent_filings = filings_data.get('filings', {}).get('recent', {})
        if recent_filings:
            for i in range(len(recent_filings.get('accessionNumber', []))):
                try:
                    filing_date = datetime.strptime(recent_filings['filingDate'][i], '%Y-%m-%d').date()
                    if (recent_filings['form'][i].upper() == form_type.upper() and 
                        start_date <= filing_date <= end_date):
                        filings.append({
                            'form': recent_filings['form'][i],
                            'filingDate': filing_date,
                            'accessionNumber': recent_filings['accessionNumber'][i],
                            'primaryDocument': recent_filings['primaryDocument'][i],
                        })
                except:
                    continue
        
        return sorted(filings, key=lambda x: x['filingDate'], reverse=True)
        
    except Exception as e:
        st.error(f"Error fetching filings: {str(e)}")
        return None

def extract_financial_data(filing_url):
    """Extract financial data from filing documents"""
    try:
        if '/ix?doc=' in filing_url:
            response = requests.get(filing_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            iframe = soup.find('iframe', {'id': 'edgar-iframe'})
            if iframe and iframe.get('src'):
                filing_url = urljoin(BASE_URL, iframe.get('src'))
        
        response = requests.get(filing_url, headers=HEADERS, timeout=15)
        content = response.text
        
        # XBRL extraction logic
        xbrl_url = filing_url.replace('.htm', '.xml').replace('.html', '.xml')
        xbrl_response = requests.get(xbrl_url, headers=HEADERS, timeout=10)
        if xbrl_response.status_code == 200:
            return parse_xbrl_filing(xbrl_response.content)
        
        # HTML fallback extraction
        soup = BeautifulSoup(content, 'html.parser')
        financial_data = {}
        
        # Table parsing logic
        table_patterns = [
            ('balance sheet', ['total assets', 'current assets', 'total liabilities']),
            ('income statement', ['revenue', 'net income']),
            ('cash flow', ['cash and cash equivalents'])
        ]
        
        for pattern, fields in table_patterns:
            table = find_table_by_header(soup, pattern)
            if table:
                for row in table.find_all('tr'):
                    cells = [cell.get_text(strip=True).lower() for cell in row.find_all(['td', 'th'])]
                    for i in range(len(cells)-1):
                        for field in fields:
                            if field in cells[i]:
                                value = parse_numeric_value(cells[i+1])
                                if value: financial_data[field.replace(' ', '_')] = value
        
        return financial_data or None
        
    except Exception as e:
        st.error(f"Error processing filing: {str(e)}")
        return None

# --------------------------
# Visualization & Analysis
# --------------------------

def analyze_and_visualize(financial_data):
    """Generate analysis and visualizations"""
    analysis = []
    figs = []
    
    if not financial_data:
        return "No financial data available", []
    
    # Balance Sheet Analysis
    if all(k in financial_data for k in ['total_assets', 'total_liabilities']):
        equity = financial_data['total_assets'] - financial_data['total_liabilities']
        analysis.append("## 📊 Balance Sheet")
        analysis.append(f"- **Total Assets**: ${financial_data['total_assets']:,.2f}")
        analysis.append(f"- **Total Liabilities**: ${financial_data['total_liabilities']:,.2f}")
        analysis.append(f"- **Shareholders' Equity**: ${equity:,.2f}")
        
        fig = px.bar(
            x=['Assets', 'Liabilities', 'Equity'],
            y=[financial_data['total_assets'], financial_data['total_liabilities'], equity],
            labels={'x': 'Category', 'y': 'Amount'},
            color=['Assets', 'Liabilities', 'Equity'],
            template='plotly_dark'
        )
        figs.append(fig)
    
    # Income Statement Analysis
    if all(k in financial_data for k in ['revenue', 'net_income']):
        margin = (financial_data['net_income'] / financial_data['revenue']) * 100
        analysis.append("\n## 💰 Income Statement")
        analysis.append(f"- **Revenue**: ${financial_data['revenue']:,.2f}")
        analysis.append(f"- **Net Income**: ${financial_data['net_income']:,.2f}")
        analysis.append(f"- **Profit Margin**: {margin:.2f}%")
        
        fig = px.pie(
            names=['Profit', 'Expenses'],
            values=[financial_data['net_income'], financial_data['revenue'] - financial_data['net_income']],
            hole=0.5,
            template='plotly_dark'
        )
        figs.append(fig)
    
    return "\n".join(analysis), figs

# --------------------------
# Chat Interface
# --------------------------

def handle_chat_query(query, financial_data):
    """Process user queries about financial data"""
    query = query.lower()
    
    if not financial_data:
        return "Please analyze a filing first"
    
    response = []
    
    # Balance Sheet Questions
    if any(word in query for word in ['asset', 'liability', 'equity']):
        response.append("### Balance Sheet Insights")
        if 'total_assets' in financial_data:
            response.append(f"- Total Assets: ${financial_data['total_assets']:,.2f}")
            response.append(f"- Total Liabilities: ${financial_data['total_liabilities']:,.2f}")
            response.append(f"- Equity: ${financial_data['total_assets'] - financial_data['total_liabilities']:,.2f}")
    
    # Income Questions
    if any(word in query for word in ['revenue', 'income', 'profit']):
        response.append("\n### Income Insights")
        if 'revenue' in financial_data:
            response.append(f"- Revenue: ${financial_data['revenue']:,.2f}")
        if 'net_income' in financial_data:
            response.append(f"- Net Income: ${financial_data['net_income']:,.2f}")
    
    return "\n".join(response) if response else "I can answer questions about assets, liabilities, revenue, and profits"

# --------------------------
# Main Application
# --------------------------

def main():
    st.title("📈 SEC Filing Analyzer Pro")
    
    # Sidebar Controls
    with st.sidebar:
        st.header("Analysis Controls")
        analysis_type = st.radio("Select Analysis Type", ["Company Search", "Direct Filing"])
        
        if analysis_type == "Company Search":
            cik = st.text_input("Enter CIK Number", "790652")
            report_type = st.selectbox("Report Type", ["10-Q", "10-K", "8-K"])
            start_date = st.date_input("Start Date", value=datetime(2022, 1, 1))
            end_date = st.date_input("End Date", value=datetime.today())
            
            if st.button("Search Filings"):
                with st.spinner("Fetching filings..."):
                    filings = get_company_filings(cik, report_type, start_date, end_date)
                    st.session_state.filings = filings
                    st.session_state.analysis_done = False
                    st.session_state.financial_data = None
                    st.session_state.selected_filing = None
        
        elif analysis_type == "Direct Filing":
            filing_url = st.text_input("Filing URL", value="https://www.sec.gov/ix?doc=/Archives/edgar/data/0000790652/000121390024098306/ea0220916-10q_imaging.htm")
            
            if st.button("Analyze Filing"):
                with st.spinner("Processing filing..."):
                    financial_data = extract_financial_data(filing_url)
                    st.session_state.financial_data = financial_data
                    st.session_state.analysis_done = True
                    st.session_state.selected_filing = {'form': 'Direct URL', 'filingDate': '', 'accessionNumber': '', 'primaryDocument': ''}
    
    # Display filings if searched
    if analysis_type == "Company Search" and 'filings' in st.session_state and st.session_state.filings:
        st.subheader("Available Filings")
        for i, filing in enumerate(st.session_state.filings):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{filing['form']}** - {filing['filingDate']} - Accession #: `{filing['accessionNumber']}`")
            with col2:
                if st.button("Analyze", key=f"analyze_{i}"):
                    accession = filing['accessionNumber'].replace("-", "")
                    cik = normalize_cik(cik)
                    filing_url = f"{BASE_URL}/Archives/edgar/data/{cik}/{accession}/{filing['primaryDocument']}"
                    with st.spinner("Processing filing..."):
                        financial_data = extract_financial_data(filing_url)
                        st.session_state.financial_data = financial_data
                        st.session_state.analysis_done = True
                        st.session_state.selected_filing = filing

    # Display analysis results
    if st.session_state.analysis_done and st.session_state.financial_data:
        st.subheader("📊 Financial Analysis")
        analysis_text, charts = analyze_and_visualize(st.session_state.financial_data)
        st.markdown(analysis_text)
        for fig in charts:
            st.plotly_chart(fig, use_container_width=True)
    
    # Chat Interface
    if st.session_state.analysis_done and st.session_state.financial_data:
        st.subheader("💬 Ask Questions About the Filing")
        user_input = st.text_input("Your question", key="chat_input")
        if st.button("Ask"):
            if user_input:
                response = handle_chat_query(user_input, st.session_state.financial_data)
                st.session_state.chat_history.append(("user", user_input))
                st.session_state.chat_history.append(("bot", response))
        
        # Display chat history
        for sender, message in st.session_state.chat_history:
            css_class = "user-message" if sender == "user" else "bot-message"
            st.markdown(f'<div class="chat-message {css_class}">{message}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()

