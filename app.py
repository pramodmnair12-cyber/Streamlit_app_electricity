import streamlit as st
import pandas as pd
import io

# --- Configuration ---
BILLING_CONFIG = {
    "Quarterly Billing": {
        "header_row": 1,
        "col_nmi": "NMI",
        "suffixes": {
            "P": {"start": "PEAK_KWH", "end": "PEAK_KWH.1"},
            "A": {"qty": "Availability charge Quantity"}
        }
    },
    "Power Smart Billing": {
        "header_row": 1,
        "col_nmi": "NMI",
        "suffixes": {
            "P": {"start": "Peak kWh reading", "end": "Peak kWh reading.1"},
            "S": {"start": "Shoulder kWh reading", "end": "Shoulder kWh reading.1"},
            "O": {"start": "Off peak kWh reading", "end": "Off peak kWh reading.1"},
            "A": {"qty": "Availability"}
        }
    },
    "Load Smart Billing": {
        "header_row": 1,
        "col_nmi": "NMI",
        "suffixes": {
            "P": {"start": "Peak kWh reading", "end": "Peak kWh reading.1"},
            "S": {"start": "Shoulder kWh reading", "end": "Shoulder kWh reading.1"},
            "O": {"start": "Off peak kWh reading", "end": "Off peak kWh reading.1"},
            "D": {"qty": "DEMAND"},
            "A": {"qty": "Availability"}
        }
    }
}

def clean_nmi(val):
    """Robust cleaner for NMI strings."""
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s

def process_dataframes(df_billing, df_target, billing_type):
    """
    Core logic to map billing dataframe to target dataframe.
    Returns: (Result DataFrame, Match Count, Error Message)
    """
    config = BILLING_CONFIG[billing_type]
    
    # 1. Verify NMI column exists in Billing
    if config["col_nmi"] not in df_billing.columns:
         return None, 0, f"Missing '{config['col_nmi']}' column in billing data."

    # 2. Verify Target Columns
    if 'Meter No.' not in df_target.columns:
        return None, 0, "Target data must have 'Meter No.' column."

    # 3. Build Lookup
    billing_lookup = {}
    suffixes_config = config["suffixes"]

    for index, row in df_billing.iterrows():
        nmi_val = row.get(config["col_nmi"])
        nmi_clean = clean_nmi(nmi_val)
        if not nmi_clean: continue
            
        nmi_data = {}
        for suffix, mapping in suffixes_config.items():
            if "start" in mapping:
                nmi_data[suffix] = {
                    "start": row.get(mapping["start"]),
                    "end": row.get(mapping["end"])
                }
            elif "qty" in mapping:
                nmi_data[suffix] = {
                    "qty": row.get(mapping["qty"])
                }
        billing_lookup[nmi_clean] = nmi_data

    # 4. Update Target
    matches_found = 0
    # Ensure columns exist
    if 'Reading From' not in df_target.columns: df_target['Reading From'] = None
    if 'Reading To' not in df_target.columns: df_target['Reading To'] = None

    for index, row in df_target.iterrows():
        meter_val = row.get('Meter No.')
        meter_clean = clean_nmi(meter_val)
        
        if len(meter_clean) < 2: continue
            
        suffix = meter_clean[-1]
        nmi_base = meter_clean[:-1]
        
        if nmi_base in billing_lookup:
            nmi_data = billing_lookup[nmi_base]
            if suffix in nmi_data:
                data = nmi_data[suffix]
                
                # Qty Logic
                if "qty" in data:
                    val = data["qty"]
                    if pd.notna(val):
                        df_target.at[index, 'Reading From'] = 0
                        df_target.at[index, 'Reading To'] = val
                        matches_found += 1
                        
                # Reading Logic
                elif "start" in data:
                    s_val = data["start"]
                    e_val = data["end"]
                    updated = False
                    if pd.notna(s_val):
                        df_target.at[index, 'Reading From'] = s_val
                        updated = True
                    if pd.notna(e_val):
                        df_target.at[index, 'Reading To'] = e_val
                        updated = True
                    if updated:
                        matches_found += 1
                        
    return df_target, matches_found, None

def load_file(uploaded_file, header=0):
    """Helper to load csv or excel"""
    try:
        if uploaded_file.name.endswith('.csv'):
            return pd.read_csv(uploaded_file, header=header)
        else:
            return pd.read_excel(uploaded_file, header=header)
    except Exception as e:
        return None

# --- UI ---
st.set_page_config(page_title="Meter Mapper", layout="wide")
st.title("⚡ Meter Reading Populator")

# Create Tabs
tab_single, tab_batch = st.tabs(["📂 Single File Mode", "📚 Batch Mode (Workbook)"])

# ==========================================
# TAB 1: SINGLE FILE MODE
# ==========================================
with tab_single:
    st.markdown("### Process a single pair of files")
    st.info("Select the billing type, upload one billing file, and one target file.")
    
    # 1. Configuration
    b_type = st.selectbox("Select Billing Type", list(BILLING_CONFIG.keys()), key="single_type")
    
    col1, col2 = st.columns(2)
    
    # 2. Uploads
    with col1:
        st.subheader("Billing File")
        bill_file = st.file_uploader("Upload CSV/Excel", type=['csv', 'xlsx'], key="single_bill")
        
    with col2:
        st.subheader("Target Template")
        target_file = st.file_uploader("Upload Readings File", type=['csv', 'xlsx'], key="single_target")
        
    # 3. Process
    if bill_file and target_file:
        st.divider()
        if st.button("Populate Single File", type="primary"):
            with st.spinner("Processing..."):
                try:
                    # Load Data
                    # Note: Use config header row for billing
                    df_b = load_file(bill_file, header=BILLING_CONFIG[b_type]["header_row"])
                    df_t = load_file(target_file)
                    
                    if df_b is None or df_t is None:
                        st.error("Error reading one of the files. Please check format.")
                    else:
                        # Process
                        res, count, err = process_dataframes(df_b, df_t, b_type)
                        
                        if err:
                            st.error(f"Error: {err}")
                        else:
                            st.success(f"Success! Updated {count} rows.")
                            
                            # Preview
                            st.dataframe(res[['Meter No.', 'Reading From', 'Reading To']].head())
                            
                            # Download
                            csv = res.to_csv(index=False).encode('utf-8')
                            fname = f"Populated_{b_type.replace(' ', '_')}.csv"
                            st.download_button(f"Download {fname}", csv, fname, "text/csv")
                            
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")

# ==========================================
# TAB 2: BATCH MODE
# ==========================================
with tab_batch:
    st.markdown("### Process multiple types from one Workbook")
    st.info("Upload ONE Billing Workbook (with multiple sheets) and THREE Target Templates.")

    # 1. Billing Input
    st.subheader("1. Input Data (Billing Source)")
    wb_billing = st.file_uploader("Upload Billing Workbook (Excel)", type=['xlsx'], key="batch_wb")

    # 2. Templates Input
    st.subheader("2. Output Templates (Files to Populate)")
    col_q, col_p, col_l = st.columns(3)
    t_quart = col_q.file_uploader("Quarterly Template", type=['csv', 'xlsx'], key="batch_t_q")
    t_power = col_p.file_uploader("Power Smart Template", type=['csv', 'xlsx'], key="batch_t_p")
    t_load  = col_l.file_uploader("Load Smart Template", type=['csv', 'xlsx'], key="batch_t_l")

    # 3. Mapping & Processing
    if wb_billing and (t_quart or t_power or t_load):
        try:
            # Read Sheet Names
            xl_billing = pd.ExcelFile(wb_billing)
            b_sheets = xl_billing.sheet_names
            
            st.divider()
            st.subheader("3. Map Sheets & Process")
            
            # Container for jobs
            jobs = []

            # --- Job 1: Quarterly ---
            if t_quart:
                with st.expander("Quarterly Billing Settings", expanded=True):
                    s_q = st.selectbox("Select Billing Sheet for Quarterly:", b_sheets, key="sheet_q")
                    jobs.append({
                        "type": "Quarterly Billing",
                        "sheet": s_q,
                        "template": t_quart
                    })

            # --- Job 2: Power Smart ---
            if t_power:
                with st.expander("Power Smart Settings", expanded=True):
                    s_p = st.selectbox("Select Billing Sheet for Power Smart:", b_sheets, key="sheet_p")
                    jobs.append({
                        "type": "Power Smart Billing",
                        "sheet": s_p,
                        "template": t_power
                    })

            # --- Job 3: Load Smart ---
            if t_load:
                with st.expander("Load Smart Settings", expanded=True):
                    s_l = st.selectbox("Select Billing Sheet for Load Smart:", b_sheets, key="sheet_l")
                    jobs.append({
                        "type": "Load Smart Billing",
                        "sheet": s_l,
                        "template": t_load
                    })
            
            # Run Button
            if st.button("Process All Templates", type="primary"):
                st.divider()
                
                for job in jobs:
                    btype = job["type"]
                    sheet_name = job["sheet"]
                    template_file = job["template"]
                    
                    st.markdown(f"**Processing {btype}...**")
                    
                    try:
                        # Load Billing Sheet
                        df_bill = pd.read_excel(wb_billing, sheet_name=sheet_name, header=BILLING_CONFIG[btype]["header_row"])
                        
                        # Load Template
                        df_temp = load_file(template_file)
                        
                        if df_bill is None or df_temp is None:
                            st.error(f"Failed to read files for {btype}")
                            continue
                            
                        # Process
                        res, count, err = process_dataframes(df_bill, df_temp, btype)
                        
                        if err:
                            st.error(f"❌ {btype}: {err}")
                        else:
                            st.success(f"✅ {btype}: Updated {count} rows.")
                            
                            # Download Button
                            csv = res.to_csv(index=False).encode('utf-8')
                            fname = f"Populated_{btype.replace(' ', '_')}.csv"
                            st.download_button(f"Download {fname}", csv, fname, "text/csv", key=f"dl_{btype}")
                            
                    except Exception as e:
                        st.error(f"Error processing {btype}: {e}")

        except Exception as e:
            st.error(f"Error reading Billing Workbook: {e}")

    elif not wb_billing:
        st.info("Please upload the Billing Workbook to start Batch Mode.")
