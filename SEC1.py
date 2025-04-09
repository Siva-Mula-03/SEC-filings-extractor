def main():
    st.title("🔍 SEC Filing Analyzer Pro")
    
    # Initialize session state
    if 'selected_filing' not in st.session_state:
        st.session_state.selected_filing = None
    if 'analysis_done' not in st.session_state:
        st.session_state.analysis_done = False

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
                
                if filings:
                    st.success(f"Found {len(filings)} {report_type} filings")
                    
                    # Display filings in an interactive table
                    df = pd.DataFrame(filings)
                    df['Filing Date'] = pd.to_datetime(df['filingDate']).dt.date
                    
                    # Create proper URLs
                    df['URL'] = df.apply(
                        lambda row: get_full_filing_url(cik, row['accessionNumber'], row['primaryDocument']), 
                        axis=1
                    )
                    
                    # Display selectable table
                    st.dataframe(
                        df[['form', 'Filing Date', 'reportDate', 'primaryDocDescription']],
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    # Store filings in session state
                    st.session_state.filings = df.to_dict('records')
                    
                    # Let user select a filing to analyze
                    selected_index = st.selectbox(
                        "Select a filing to analyze",
                        range(len(filings)),
                        format_func=lambda x: f"{filings[x]['form']} - {filings[x]['filingDate']} - {filings[x].get('primaryDocDescription', '')}"
                    )
                    
                    # Store selected filing in session state
                    st.session_state.selected_filing = filings[selected_index]
                    st.session_state.analysis_done = False

        # Analysis section (only shown when a filing is selected)
        if st.session_state.selected_filing and not st.session_state.analysis_done:
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
                        st.session_state.analysis_done = False
    
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
                    analysis = analyze_financials(financial_data, {'form': 'Direct Filing'})
                    st.markdown(analysis)
                    
                    st.subheader("Visualizations")
                    figs = visualize_financials(financial_data)
                    for fig in figs:
                        st.pyplot(fig)
                else:
                    st.error("Could not extract financial data from this filing")
