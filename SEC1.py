import streamlit as st
st.set_page_config(page_title="SEC Filing Analyzer Pro", layout="wide", page_icon="📈")
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

# Custom CSS for chat interface and overall styling
st.markdown("""
<style>
/* Chat interface styling */
.chat-message {
    padding: 12px;
    border-radius: 12px;
    margin: 8px 0;
    max-width: 80%;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.user-message {
    background-color: #e3f2fd;
    margin-left: 20%;
    border: 1px solid #bbdefb;
}
.bot-message {
    background-color: #f5f5f5;
    margin-right: 20%;
    border: 1px solid #e0e0e0;
}

/* Overall app styling */
.stApp {
    background-color: #fafafa;
}
.stButton>button {
    background-color: #1976d2;
    color: white;
    border-radius: 8px;
    padding: 8px 16px;
}
.stTextInput>div>div>input {
    border-radius: 8px;
    padding: 10px;
}
.stSelectbox>div>div>select {
    border-radius: 8px;
    padding: 8px;
}
.stDateInput>div>div>input {
    border-radius: 8px;
    padding: 8px;
}

/* Card styling */
.card {
    background: white;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}
</style>
""", unsafe_allow_html=True)

def normalize_cik(cik):
    """Convert CIK to proper format (10 digits with leading zeros)"""
    try:
        return str(int(cik.strip())).zfill(10)
    except:
        return None

def get_company_filings(cik, form_type, start_date, end_date):
    """Retrieve company filings from SEC EDGAR database"""
    try:
        normalized_cik = normalize_cik(cik)
        if not normalized_cik:
            st.error("Invalid CIK format")
            return None
            
        url = f"{SEC_API}/CIK{normalized_cik}.json"
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        
        if response.status_code != 200:
            st.error(f"SEC API Error: {response.status_code} - {response.text}")
            return None
            
        filings_data = response.json()
        filings = []
        
        # Process recent filings
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
                            'reportDate': recent_filings.get('reportDate', [None]*len(recent_filings['form']))[i],
                            'accessionNumber': recent_filings['accessionNumber'][i],
                            'primaryDocument': recent_filings['primaryDocument'][i],
                            'primaryDocDescription': recent_filings.get('primaryDocDescription', [None]*len(recent_filings['form']))[i]
                        })
                except:
                    continue
        
        # Sort by filing date (newest first)
        filings.sort(key=lambda x: x['filingDate'], reverse=True)
        return filings
        
    except Exception as e:
        st.error(f"Error fetching filings: {str(e)}")
        return None

def get_full_filing_url(cik, accession_number, primary_doc):
    """Construct proper SEC filing URL with correct path"""
    accession_no_clean = accession_number.replace("-", "")
    return f"{BASE_URL}/Archives/edgar/data/{cik}/{accession_no_clean}/{primary_doc}"

def extract_financial_data(filing_url):
    """Enhanced financial data extraction with multiple fallback methods"""
    try:
        # First get the actual document content
        if '/ix?doc=' in filing_url:
            response = requests.get(filing_url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            iframe = soup.find('iframe', {'id': 'edgar-iframe'})
            if iframe and iframe.get('src'):
                filing_url = urljoin(BASE_URL, iframe.get('src'))
        
        response = requests.get(filing_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        content = response.text
        
        # Try XBRL first
        xbrl_url = filing_url.replace('.htm', '.xml').replace('.html', '.xml')
        xbrl_response = requests.get(xbrl_url, headers=HEADERS, timeout=10)
        if xbrl_response.status_code == 200:
            xbrl_data = parse_xbrl_filing(xbrl_response.content)
            if xbrl_data:
                return xbrl_data
        
        # Fall back to HTML parsing with improved table detection
        soup = BeautifulSoup(content, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'meta', 'link', 'nav', 'header', 'footer']):
            element.decompose()
        
        financial_data = {}
        
        # Look for specific tables by common patterns
        table_patterns = [
            ('consolidated balance sheet', ['total assets', 'current assets', 
                                          'total liabilities', 'current liabilities']),
            ('consolidated statement of operations', ['revenue', 'net income']),
            ('consolidated statement of cash flows', ['cash and cash equivalents'])
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
                                if value is not None:
                                    financial_data[field.replace(' ', '_')] = value
        
        # If we still haven't found data, try to find financial statements links
        if not financial_data:
            financial_links = []
            for link in soup.find_all('a', href=True):
                if any(term in link.text.lower() for term in ['financial', 'statement', 'balance sheet', 'income']):
                    financial_links.append(urljoin(filing_url, link['href']))
            
            # Try each financial statement link
            for link in financial_links[:3]:  # Limit to first 3 links
                try:
                    stmt_response = requests.get(link, headers=HEADERS, timeout=10)
                    stmt_response.raise_for_status()
                    stmt_data = parse_html_filing(stmt_response.content)
                    if stmt_data:
                        financial_data.update(stmt_data)
                except:
                    continue
                
        return financial_data if financial_data else None
        
    except Exception as e:
        st.error(f"Error processing filing: {str(e)}")
        return None

def find_table_by_header(soup, header_text):
    """Find a table that has the given header text"""
    headers = soup.find_all(string=re.compile(header_text, re.IGNORECASE))
    for header in headers:
        parent = header.find_parent()
        while parent:
            if parent.name == 'table':
                return parent
            parent = parent.find_parent()
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
        concepts = {
            'Assets': 'total_assets',
            'AssetsCurrent': 'current_assets',
            'Liabilities': 'total_liabilities',
            'LiabilitiesCurrent': 'current_liabilities',
            'StockholdersEquity': 'shareholders_equity',
            'RevenueFromContractWithCustomer': 'revenue',
            'NetIncomeLoss': 'net_income',
            'EarningsPerShareBasic': 'eps_basic',
            'EarningsPerShareDiluted': 'eps_diluted',
            'OperatingIncomeLoss': 'operating_income',
            'CashAndCashEquivalentsAtCarryingValue': 'cash'
        }
        
        for concept, key in concepts.items():
            elem = root.find(f'.//us-gaap:{concept}', ns)
            if elem is not None and elem.text:
                try:
                    # Handle scale factors (e.g., units="USD" scale="6" means millions)
                    scale = int(elem.get('scale', '0'))
                    value = float(elem.text.replace(',', '')) * (10 ** scale)
                    data[key] = value
                except ValueError:
                    continue
        
        # Get reporting period
        period = root.find('.//dei:DocumentPeriodEndDate', ns)
        if period is not None and period.text:
            data['reporting_period'] = period.text
            
        return data if data else None
        
    except ET.ParseError:
        return None
    except Exception as e:
        st.error(f"XBRL parsing error: {str(e)}")
        return None

def parse_html_filing(content):
    """Parse HTML financial statements with improved table detection"""
    try:
        soup = BeautifulSoup(content, 'html.parser')
        financial_data = {}
        
        # Improved table detection with context awareness
        table_patterns = {
            'balance_sheet': ['total assets', 'current assets', 'total liabilities', 'current liabilities'],
            'income_statement': ['revenue', 'net income', 'operating income'],
            'cash_flow': ['cash and cash equivalents']
        }
        
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    value = parse_numeric_value(cells[-1].get_text(strip=True))
                    
                    # Match against known financial terms
                    for category, terms in table_patterns.items():
                        for term in terms:
                            if term in label and value is not None:
                                financial_data[term.replace(' ', '_')] = value
        
        return financial_data if financial_data else None
        
    except Exception as e:
        st.error(f"HTML parsing error: {str(e)}")
        return None

def parse_numeric_value(text):
    """More robust numeric value parsing"""
    if not text:
        return None
    
    # Handle accounting format (parentheses for negatives)
    text = text.strip().replace('(', '-').replace(')', '')
    
    # Remove non-numeric characters except decimal point and minus sign
    cleaned = re.sub(r'[^\d.-]', '', text)
    
    try:
        return float(cleaned)
    except ValueError:
        return None

def analyze_and_visualize(financial_data):
    """Comprehensive analysis with visualizations"""
    if not financial_data or all(v is None for v in financial_data.values()):
        return "No financial data available for analysis", None
    
    analysis = []
    figs = []
    
    # 1. Balance Sheet Analysis
    if all(k in financial_data for k in ['total_assets', 'total_liabilities']):
        equity = financial_data['total_assets'] - financial_data['total_liabilities']
        
        analysis.append("## 📊 Balance Sheet Analysis")
        analysis.append(f"- **Total Assets**: ${financial_data['total_assets']:,.2f}")
        analysis.append(f"- **Total Liabilities**: ${financial_data['total_liabilities']:,.2f}")
        analysis.append(f"- **Shareholders' Equity**: ${equity:,.2f}")
        
        # Visualization
        bs_data = pd.DataFrame({
            'Category': ['Assets', 'Liabilities', 'Equity'],
            'Amount': [financial_data['total_assets'], 
                      financial_data['total_liabilities'], 
                      equity]
        })
        fig1 = px.bar(bs_data, x='Category', y='Amount', 
                     title='Balance Sheet Composition',
                     color='Category',
                     text='Amount')
        fig1.update_traces(texttemplate='$%{text:,.0f}', textposition='outside')
        fig1.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
        figs.append(fig1)
    
    # 2. Income Statement Analysis
    if all(k in financial_data for k in ['revenue', 'net_income']):
        profit_margin = (financial_data['net_income'] / financial_data['revenue']) * 100
        
        analysis.append("\n## 💰 Income Statement Analysis")
        analysis.append(f"- **Revenue**: ${financial_data['revenue']:,.2f}")
        analysis.append(f"- **Net Income**: ${financial_data['net_income']:,.2f}")
        analysis.append(f"- **Profit Margin**: {profit_margin:.2f}%")
        
        # Visualization
        is_data = pd.DataFrame({
            'Metric': ['Revenue', 'Net Income'],
            'Amount': [financial_data['revenue'], financial_data['net_income']]
        })
        fig2 = px.bar(is_data, x='Metric', y='Amount', 
                     title='Income Statement',
                     color='Metric',
                     text='Amount')
        fig2.update_traces(texttemplate='$%{text:,.0f}', textposition='outside')
        figs.append(fig2)
        
        # Profit margin gauge
        fig2a = px.pie(values=[profit_margin, 100-profit_margin],
                      names=['Profit', 'Costs'],
                      title=f'Profit Margin: {profit_margin:.1f}%',
                      hole=0.5)
        fig2a.update_traces(textinfo='none')
        figs.append(fig2a)
    
    # 3. Liquidity Analysis
    if all(k in financial_data for k in ['current_assets', 'current_liabilities']):
        current_ratio = financial_data['current_assets'] / financial_data['current_liabilities']
        
        analysis.append("\n## 💧 Liquidity Analysis")
        analysis.append(f"- **Current Assets**: ${financial_data['current_assets']:,.2f}")
        analysis.append(f"- **Current Liabilities**: ${financial_data['current_liabilities']:,.2f}")
        analysis.append(f"- **Current Ratio**: {current_ratio:.2f}")
        analysis.append(f"- **Interpretation**: {'✅ Healthy (>1.5)' if current_ratio > 1.5 else '⚠️ Caution (<1)' if current_ratio < 1 else '🟡 Moderate (1-1.5)'}")
        
        # Visualization
        fig3 = px.bar(x=['Current Ratio'], y=[current_ratio],
                     title='Liquidity Position',
                     labels={'x':'Metric', 'y':'Ratio'},
                     text=[f"{current_ratio:.2f}"])
        fig3.update_traces(textposition='outside')
        fig3.add_hline(y=1.5, line_dash="dash", line_color="green")
        fig3.add_hline(y=1, line_dash="dash", line_color="red")
        fig3.update_yaxes(range=[0, max(3, current_ratio * 1.2)])
        figs.append(fig3)
    
    # 4. Cash Position
    if 'cash' in financial_data:
        analysis.append("\n## 💵 Cash Position")
        analysis.append(f"- **Cash & Equivalents**: ${financial_data['cash']:,.2f}")
        
        if 'current_liabilities' in financial_data and financial_data['current_liabilities'] > 0:
            cash_ratio = financial_data['cash'] / financial_data['current_liabilities']
            analysis.append(f"- **Cash Ratio**: {cash_ratio:.2f}")
        
        # Visualization
        fig4 = px.bar(x=['Cash'], y=[financial_data['cash']],
                     title='Cash Position',
                     labels={'x':'', 'y':'Amount ($)'},
                     text=[f"${financial_data['cash']:,.0f}"])
        fig4.update_traces(textposition='outside')
        figs.append(fig4)
    
    return "\n".join(analysis), figs

def handle_user_query(query, financial_data):
    """Chatbot-style query handling with enhanced responses"""
    query = query.lower()
    response = ""
    
    if not financial_data:
        return "No financial data available for analysis."
    
    # Balance Sheet Questions
    if any(word in query for word in ["asset", "liabilit", "equity", "balance sheet"]):
        if 'total_assets' in financial_data:
            response = "### Balance Sheet Information\n"
            response += f"- **Total Assets**: ${financial_data['total_assets']:,.2f}\n"
            response += f"- **Total Liabilities**: ${financial_data['total_liabilities']:,.2f}\n"
            equity = financial_data['total_assets'] - financial_data['total_liabilities']
            response += f"- **Shareholders' Equity**: ${equity:,.2f}\n\n"
            
            if 'current_assets' in financial_data:
                response += f"- **Current Assets**: ${financial_data['current_assets']:,.2f}\n"
                response += f"- **Current Liabilities**: ${financial_data['current_liabilities']:,.2f}\n"
                current_ratio = financial_data['current_assets'] / financial_data['current_liabilities']
                response += f"- **Current Ratio**: {current_ratio:.2f} "
                response += "(Healthy)" if current_ratio > 1.5 else "(Caution)" if current_ratio < 1 else "(Moderate)"
        else:
            response = "Balance sheet data not available in this filing."
    
    # Income Statement Questions
    elif any(word in query for word in ["revenue", "sales", "income", "profit", "margin"]):
        if 'revenue' in financial_data:
            response = "### Income Statement Information\n"
            response += f"- **Revenue**: ${financial_data['revenue']:,.2f}\n"
            
            if 'net_income' in financial_data:
                response += f"- **Net Income**: ${financial_data['net_income']:,.2f}\n"
                margin = (financial_data['net_income'] / financial_data['revenue']) * 100
                response += f"- **Profit Margin**: {margin:.2f}% "
                response += "(Strong)" if margin > 15 else "(Average)" if margin > 5 else "(Weak)"
            
            if 'operating_income' in financial_data:
                response += f"\n- **Operating Income**: ${financial_data['operating_income']:,.2f}"
        else:
            response = "Income statement data not available in this filing."
    
    # Cash Questions
    elif any(word in query for word in ["cash", "liquidity"]):
        if 'cash' in financial_data:
            response = "### Cash Position\n"
            response += f"- **Cash & Equivalents**: ${financial_data['cash']:,.2f}\n"
            
            if 'current_liabilities' in financial_data:
                cash_ratio = financial_data['cash'] / financial_data['current_liabilities']
                response += f"- **Cash Ratio**: {cash_ratio:.2f} "
                response += "(Strong)" if cash_ratio > 0.5 else "(Low)"
        else:
            response = "Cash position data not available in this filing."
    
    # General Help
    elif any(word in query for word in ["help", "what can", "how to"]):
        response = """### How to use this analyzer:
Ask questions about:
- Revenue and profits
- Assets and liabilities
- Cash position
- Financial ratios

Example questions:
- What was the company's revenue?
- Show me the balance sheet
- What's the current ratio?
- How much cash does the company have?"""
    
    else:
        response = "I can analyze financial statements including balance sheets, income statements, and cash positions. Try asking about:\n- Revenue\n- Assets\n- Profit margin\n- Cash position"
    
    return response

def display_chat_message(role, content):
    """Display a chat message with appropriate styling"""
    if role == 'user':
        st.markdown(f"<div class='chat-message user-message'>👤 User: {content}</div>", 
                   unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='chat-message bot-message'>🤖 Analyst: {content}</div>", 
                   unsafe_allow_html=True)

def main():
   
    
    # Main app header
    st.title("📈 SEC Filing Analyzer Pro")
    st.markdown("Analyze SEC filings with comprehensive financial analysis and AI-powered insights")
    
    # Initialize session state
    if 'filings' not in st.session_state:
        st.session_state.filings = None
    if 'selected_filing' not in st.session_state:
        st.session_state.selected_filing = None
    if 'financial_data' not in st.session_state:
        st.session_state.financial_data = None
    if 'analysis_done' not in st.session_state:
        st.session_state.analysis_done = False
    
    # Sidebar for navigation
    with st.sidebar:
        st.header("Navigation")
        analysis_type = st.radio("Select Analysis Type", ["Company Filings", "Direct Filing Analysis"])
        
        if analysis_type == "Company Filings":
            st.subheader("Company Search")
            cik = st.text_input("Enter Company CIK", "790652")  # Default: ZoomInfo
            report_type = st.selectbox("Select Report Type", ["10-Q", "10-K", "8-K", "DEF 14A"])
            
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date", value=datetime(2022, 10, 1))
            with col2:
                end_date = st.date_input("End Date", value=datetime.today())
            
            if st.button("Search Filings", key="search_filings"):
                with st.spinner("Fetching SEC filings..."):
                    filings = get_company_filings(cik, report_type, start_date, end_date)
                    st.session_state.filings = filings
                    st.session_state.selected_filing = None
                    st.session_state.financial_data = None
                    st.session_state.analysis_done = False
                    
                    if filings:
                        st.success(f"Found {len(filings)} {report_type} filings")
                    else:
                        st.warning(f"No {report_type} filings found for CIK {cik}")
        
        st.markdown("---")
        st.markdown("**Tip**: After analyzing a filing, ask questions in the chat below!")
    
    # Main content area
    if analysis_type == "Company Filings" and st.session_state.filings:
        st.header("Available Filings")
        
        # Display filings in a select box
        selected_index = st.selectbox(
            "Select a filing to analyze",
            range(len(st.session_state.filings)),
            format_func=lambda x: f"{st.session_state.filings[x]['form']} - {st.session_state.filings[x]['filingDate']} - {st.session_state.filings[x].get('primaryDocDescription', '')}"
        )
        
        # Store selected filing
        st.session_state.selected_filing = st.session_state.filings[selected_index]
        
        if st.button("Analyze Selected Filing", key="analyze_filing"):
            with st.spinner("Analyzing filing..."):
                selected_filing = st.session_state.selected_filing
                filing_url = get_full_filing_url(
                    normalize_cik(cik),
                    selected_filing['accessionNumber'],
                    selected_filing['primaryDocument']
                )
                
                financial_data = extract_financial_data(filing_url)
                st.session_state.financial_data = financial_data
                st.session_state.analysis_done = True
    
    elif analysis_type == "Direct Filing Analysis":
        st.header("Direct Filing Analysis")
        filing_url = st.text_input(
            "Enter SEC Filing URL", 
            "https://www.sec.gov/ix?doc=/Archives/edgar/data/0000790652/000121390024098306/ea0220916-10q_imaging.htm"
        )
        
        if st.button("Analyze Filing", key="analyze_direct"):
            with st.spinner("Analyzing filing..."):
                financial_data = extract_financial_data(filing_url)
                st.session_state.financial_data = financial_data
                st.session_state.analysis_done = True
    
    # Display analysis results if available
    if st.session_state.analysis_done and st.session_state.financial_data:
        st.header("Comprehensive Analysis")
        
        with st.expander("View Raw Financial Data"):
            st.json(st.session_state.financial_data)
        
        analysis_text, visualizations = analyze_and_visualize(st.session_state.financial_data)
        st.markdown(analysis_text)
        
        for fig in visualizations:
            st.plotly_chart(fig, use_container_width=True)
    
    # Chat Interface
    st.header("💬 Ask Questions About This Filing")
    
    # Display chat history
    for message in st.session_state.chat_history:
        display_chat_message(message['role'], message['content'])
    
    # User query input
    user_query = st.text_input(
        "Type your question about this filing and press Enter:", 
        key="query_input",
        placeholder="e.g. What was the revenue? How much cash does the company have?"
    )
    
    if user_query:
        # Add user query to history
        st.session_state.chat_history.append({'role': 'user', 'content': user_query})
        
        # Get and display response
        if st.session_state.financial_data:
            response = handle_user_query(user_query, st.session_state.financial_data)
        else:
            response = "Please analyze a filing first to enable question answering."
        
        st.session_state.chat_history.append({'role': 'assistant', 'content': response})
        
        # Rerun to update display
        st.experimental_rerun()

if __name__ == "__main__":
    main()
