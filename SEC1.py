import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
from datetime import datetime
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
from urllib.parse import urljoin

# Configuration
SEC_API = "https://data.sec.gov/submissions"
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
    """Extract financial data from filing document"""
    try:
        # First try to get the actual document URL from the index page
        if '/ix?doc=' in filing_url:
            response = requests.get(filing_url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            iframe = soup.find('iframe', {'id': 'edgar-iframe'})
            if iframe and iframe.get('src'):
                filing_url = urljoin(BASE_URL, iframe.get('src'))
        
        response = requests.get(filing_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        content = response.content
        
        # Try XBRL first
        xbrl_data = parse_xbrl_filing(content)
        if xbrl_data:
            return xbrl_data
            
        # Fall back to HTML parsing
        html_data = parse_html_filing(content)
        if html_data:
            return html_data
            
        return None
        
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
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'meta', 'link', 'nav', 'header', 'footer']):
            element.decompose()
        
        financial_data = {}
        
        # Try to find consolidated financial statements
        consolidated_text = soup.find_all(string=re.compile(r'consolidated', re.IGNORECASE))
        if consolidated_text:
            parent = consolidated_text[0].find_parent()
            tables = parent.find_all_next('table', limit=5)
        else:
            tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    value = cells[-1].get_text(strip=True)
                    
                    # Improved financial term detection
                    if 'total assets' in label:
                        financial_data['total_assets'] = parse_numeric_value(value)
                    elif 'current assets' in label:
                        financial_data['current_assets'] = parse_numeric_value(value)
                    elif 'total liabilities' in label:
                        financial_data['total_liabilities'] = parse_numeric_value(value)
                    elif 'current liabilities' in label:
                        financial_data['current_liabilities'] = parse_numeric_value(value)
                    elif 'total revenue' in label or 'sales' in label:
                        financial_data['revenue'] = parse_numeric_value(value)
                    elif 'net income' in label or 'net profit' in label:
                        financial_data['net_income'] = parse_numeric_value(value)
                    elif 'operating income' in label:
                        financial_data['operating_income'] = parse_numeric_value(value)
                    elif 'cash and cash equivalents' in label:
                        financial_data['cash'] = parse_numeric_value(value)
        
        return financial_data if financial_data else None
        
    except Exception as e:
        st.error(f"HTML parsing error: {str(e)}")
        return None

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
        
        # Method 1: Try to find direct XBRL data
        xbrl_url = filing_url.replace('.htm', '.xml').replace('.html', '.xml')
        xbrl_response = requests.get(xbrl_url, headers=HEADERS, timeout=10)
        if xbrl_response.status_code == 200:
            xbrl_data = parse_xbrl_filing(xbrl_response.content)
            if xbrl_data:
                return xbrl_data
        
        # Method 2: Improved HTML table parsing
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
        
        # Method 3: Search for specific financial terms
        if not financial_data:
            term_mapping = {
                'total assets': 'total_assets',
                'current assets': 'current_assets',
                'total liabilities': 'total_liabilities',
                'current liabilities': 'current_liabilities',
                'revenue': 'revenue',
                'net income': 'net_income',
                'cash and cash equivalents': 'cash'
            }
            
            for term, key in term_mapping.items():
                elements = soup.find_all(string=re.compile(term, re.IGNORECASE))
                for element in elements:
                    parent = element.find_parent()
                    if parent:
                        siblings = parent.find_next_siblings()
                        for sibling in siblings[:3]:  # Check next 3 siblings
                            value = parse_numeric_value(sibling.get_text(strip=True))
                            if value is not None and key not in financial_data:
                                financial_data[key] = value
        
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

def extract_financial_data(filing_url):
    """Extract financial data from filing document with better error handling"""
    try:
        # First try to get the actual document URL from the index page
        if '/ix?doc=' in filing_url:
            response = requests.get(filing_url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            iframe = soup.find('iframe', {'id': 'edgar-iframe'})
            if iframe and iframe.get('src'):
                filing_url = urljoin(BASE_URL, iframe.get('src'))
        
        response = requests.get(filing_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        content = response.content
        
        # Try XBRL first
        xbrl_data = parse_xbrl_filing(content)
        if xbrl_data and any(xbrl_data.values()):
            return xbrl_data
            
        # Fall back to HTML parsing with improved table detection
        html_data = parse_html_filing(content)
        if html_data and any(html_data.values()):
            return html_data
            
        # If we still haven't found data, try to find financial statements links
        soup = BeautifulSoup(content, 'html.parser')
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
                if stmt_data and any(stmt_data.values()):
                    return stmt_data
            except:
                continue
                
        st.warning("Could not automatically extract financial data from this filing. Please check the filing manually.")
        return None
        
    except Exception as e:
        st.error(f"Error processing filing: {str(e)}")
        return None

def analyze_financials(financial_data, filing_info):
    """Generate financial analysis with robust error handling"""
    if not financial_data:
        return "⚠️ No financial data available for analysis"
    
    # Validate and clean the financial data
    cleaned_data = {}
    for key, value in financial_data.items():
        if value is not None:
            # Convert to absolute value for certain metrics
            if key in ['cash', 'current_assets', 'total_assets']:
                cleaned_data[key] = abs(float(value))
            else:
                cleaned_data[key] = float(value)
    
    analysis = []
    analysis.append("### Key Financial Metrics")
    
    try:
        # Basic metrics with validation
        if 'revenue' in cleaned_data and cleaned_data['revenue'] > 0:
            analysis.append(f"- **Revenue**: ${cleaned_data['revenue']:,.2f}")
        
        if 'net_income' in cleaned_data:
            analysis.append(f"- **Net Income**: ${cleaned_data['net_income']:,.2f}")
        
        if 'operating_income' in cleaned_data:
            analysis.append(f"- **Operating Income**: ${cleaned_data['operating_income']:,.2f}")
        
        # Balance Sheet Analysis with validation
        if ('total_assets' in cleaned_data and 
            'total_liabilities' in cleaned_data and
            cleaned_data['total_assets'] > 0):
            
            if cleaned_data['total_liabilities'] > cleaned_data['total_assets']:
                analysis.append("\n⚠️ Warning: Liabilities exceed total assets - data may need verification")
            
            equity = cleaned_data['total_assets'] - cleaned_data['total_liabilities']
            analysis.append("\n### Balance Sheet Analysis")
            analysis.append(f"- **Total Assets**: ${cleaned_data['total_assets']:,.2f}")
            analysis.append(f"- **Total Liabilities**: ${cleaned_data['total_liabilities']:,.2f}")
            analysis.append(f"- **Shareholders' Equity**: ${equity:,.2f}")
            
            if equity > 0:  # Only calculate ratio if equity is positive
                debt_to_equity = cleaned_data['total_liabilities'] / equity
                analysis.append(f"- **Debt-to-Equity Ratio**: {debt_to_equity:.2f}")
        
        # Liquidity Analysis with validation
        if ('current_assets' in cleaned_data and 
            'current_liabilities' in cleaned_data and
            cleaned_data['current_liabilities'] > 0):
            
            current_ratio = cleaned_data['current_assets'] / cleaned_data['current_liabilities']
            analysis.append("\n### Liquidity Analysis")
            analysis.append(f"- **Current Ratio**: {current_ratio:.2f}")
            
            if 'cash' in cleaned_data:
                quick_ratio = cleaned_data['cash'] / cleaned_data['current_liabilities']
                analysis.append(f"- **Quick Ratio**: {quick_ratio:.2f}")
        
        # Profitability Analysis with validation
        if ('revenue' in cleaned_data and 
            'net_income' in cleaned_data and
            cleaned_data['revenue'] > 0):
            
            profit_margin = (cleaned_data['net_income'] / cleaned_data['revenue']) * 100
            analysis.append("\n### Profitability Analysis")
            analysis.append(f"- **Profit Margin**: {profit_margin:.2f}%")
        
        if len(analysis) == 1:  # Only has the header
            return "⚠️ Found financial data but couldn't generate meaningful analysis"
        
        return "\n".join(analysis)
    
    except Exception as e:
        return f"⚠️ Error in analysis: Some calculated values may be invalid. Original data: {cleaned_data}"
def visualize_financials(financial_data):
    """Create visualizations of financial data"""
    figs = []
    
    # Balance Sheet Visualization
    if 'total_assets' in financial_data and 'total_liabilities' in financial_data:
        fig1, ax1 = plt.subplots(figsize=(8, 4))
        equity = financial_data['total_assets'] - financial_data['total_liabilities']
        ax1.barh(['Assets', 'Liabilities', 'Equity'], 
                [financial_data['total_assets'], financial_data['total_liabilities'], equity],
                color=['#1f77b4', '#ff7f0e', '#2ca02c'])
        ax1.set_title('Balance Sheet Composition')
        ax1.set_xlabel('Amount ($)')
        figs.append(fig1)
    
    # Income Statement Visualization
    if all(k in financial_data for k in ['revenue', 'operating_income', 'net_income']):
        fig2, ax2 = plt.subplots(figsize=(8, 4))
        ax2.bar(['Revenue', 'Operating Income', 'Net Income'],
               [financial_data['revenue'], financial_data['operating_income'], financial_data['net_income']],
               color=['#1f77b4', '#ff7f0e', '#2ca02c'])
        ax2.set_title('Income Statement')
        ax2.set_ylabel('Amount ($)')
        figs.append(fig2)
    
    return figs

def main():
    st.set_page_config(page_title="SEC Filing Analyzer", layout="wide")
    st.title("🔍 SEC Filing Analyzer Pro")
    
    # Initialize session state
    if 'selected_filing' not in st.session_state:
        st.session_state.selected_filing = None
    if 'analysis_done' not in st.session_state:
        st.session_state.analysis_done = False
    if 'filings' not in st.session_state:
        st.session_state.filings = None

    # Sidebar for navigation
    st.sidebar.header("Navigation")
    analysis_type = st.sidebar.radio("Select Analysis Type", ["Company Filings", "Direct Filing Analysis"])
    
    if analysis_type == "Company Filings":
        st.header("📄 Company Filings Search")
        
        col1, col2 = st.columns(2)
        with col1:
            cik = st.text_input("Enter Company CIK", "790652")  # ZoomInfo Technologies
        with col2:
            report_type = st.selectbox("Select Report Type", ["10-Q", "10-K", "8-K", "DEF 14A"])
        
        col3, col4 = st.columns(2)
        with col3:
            start_date = st.date_input("Start Date", value=datetime(2022, 10, 1))
        with col4:
            end_date = st.date_input("End Date", value=datetime.today())
        
        if st.button("Search Filings"):
            if not cik or not cik.strip().isdigit():
                st.error("Please enter a valid CIK number")
                return
                
            with st.spinner("Fetching SEC filings..."):
                filings = get_company_filings(cik, report_type, start_date, end_date)
                st.session_state.filings = filings
                st.session_state.selected_filing = None
                st.session_state.analysis_done = False
                
                if filings:
                    st.success(f"Found {len(filings)} {report_type} filings")
                else:
                    st.warning(f"No {report_type} filings found for CIK {cik} between {start_date} and {end_date}")

        if st.session_state.filings:
            st.subheader("Available Filings")
            
            # Display filings in a table
            df = pd.DataFrame(st.session_state.filings)
            df['Filing Date'] = pd.to_datetime(df['filingDate']).dt.date
            
            # Create a selection box
            selected_index = st.selectbox(
                "Select a filing to analyze",
                range(len(st.session_state.filings)),
                format_func=lambda x: f"{st.session_state.filings[x]['form']} - {st.session_state.filings[x]['filingDate']} - {st.session_state.filings[x].get('primaryDocDescription', '')}"
            )
            
            # Store selected filing
            st.session_state.selected_filing = st.session_state.filings[selected_index]
            
            if st.button("Analyze Selected Filing"):
                with st.spinner("Analyzing filing..."):
                    selected_filing = st.session_state.selected_filing
                    filing_url = get_full_filing_url(cik, selected_filing['accessionNumber'], selected_filing['primaryDocument'])
                    
                    financial_data = extract_financial_data(filing_url)
                    
                    if financial_data:
                        st.subheader("Financial Data")
                        st.json(financial_data)
                        
                        st.subheader("Financial Analysis")
                        analysis = analyze_financials(financial_data, selected_filing)
                        st.markdown(analysis)
                        
                        st.subheader("Visualizations")
                        figs = visualize_financials(financial_data)
                        for fig in figs:
                            st.pyplot(fig)
                        
                        st.session_state.analysis_done = True
                    else:
                        st.error("Could not extract financial data from this filing")
    
    elif analysis_type == "Direct Filing Analysis":
        st.header("📑 Direct Filing Analysis")
        filing_url = st.text_input("Enter SEC Filing URL", "https://www.sec.gov/ix?doc=/Archives/edgar/data/0000790652/000121390024098306/ea0220916-10q_imaging.htm")
        
        if st.button("Analyze Filing") and filing_url:
            with st.spinner("Analyzing filing..."):
                financial_data = extract_financial_data(filing_url)
                
                if financial_data:
                    st.subheader("Financial Data")
                    st.json(financial_data)
                    
                    st.subheader("Financial Analysis")
                    analysis = analyze_financials(financial_data, {'form': 'Direct Filing'})
                    st.markdown(analysis)
                    
                    st.subheader("Visualizations")
                    figs = visualize_financials(financial_data)
                    for fig in figs:
                        st.pyplot(fig)
                else:
                    st.error("Could not extract financial data from this filing")

if __name__ == "__main__":
    main()
