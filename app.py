import streamlit as st
import pandas as pd
import io

# --- Configuration for Billing File Types ---
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

def process_meter_readings(billing_file, readings_file, billing_type):
    config = BILLING_CONFIG[billing_type]
    
    # 1. Load the Billing Data
    try:
        # Check if file is CSV or Excel
        if billing_file.name.endswith('.csv'):
            df_billing = pd.read_csv(billing_file, header=config["header_row"])
        else:
            df_billing = pd.read_excel(billing_file, header=config["header_row"])
    except Exception as e:
        return None, f"Error reading billing file: {e}"

    # 2. Load the Readings File
    try:
        if readings_file.name.endswith('.csv'):
            df_target = pd.read_csv(readings_file)
        else:
            df_target = pd.read_excel(readings_file)
    except Exception as e:
        return None, f"Error reading target file: {e}"

    # 3. Build Lookup Dictionary
    billing_lookup = {}
    suffixes_config = config["suffixes"]

    for index, row in df_billing.iterrows():
        raw_nmi = row[config["col_nmi"]]
        if pd.isna(raw_nmi):
            continue
        
        # Clean NMI
        nmi_str = str(raw_nmi)
        if nmi_str.endswith('.0'):
            nmi_str = nmi_str[:-2]
            
        # Store all relevant data for this NMI
        nmi_data = {}
        
        for suffix, mapping in suffixes_config.items():
            if "start" in mapping: # It's a reading range
                nmi_data[suffix] = {
                    "start": row.get(mapping["start"]),
                    "end": row.get(mapping["end"])
                }
            elif "qty" in mapping: # It's a single quantity value
                nmi_data[suffix] = {
                    "qty": row.get(mapping["qty"])
                }
        
        billing_lookup[nmi_str] = nmi_data

    # 4. Update the Target DataFrame
    matches_found = 0
    
    # Ensure columns exist
    if 'Reading From' not in df_target.columns:
        df_target['Reading From'] = None
    if 'Reading To' not in df_target.columns:
        df_target['Reading To'] = None
        
    for index, row in df_target.iterrows():
        meter_no = str(row['Meter No.'])
        
        if len(meter_no) < 2:
            continue
            
        suffix = meter_no[-1] # Extract suffix (A, P, S, O, D)
        nmi_base = meter_no[:-1]
        
        if nmi_base in billing_lookup:
            nmi_data = billing_lookup[nmi_base]
            
            # Check if this suffix is handled in our config
            if suffix in nmi_data:
                data = nmi_data[suffix]
                
                # Logic for Quantity Types (Availability, Demand)
                if "qty" in data:
                    val = data["qty"]
                    if pd.notna(val):
                        df_target.at[index, 'Reading From'] = 0
                        df_target.at[index, 'Reading To'] = val
                        matches_found += 1
                        
                # Logic for Reading Types (Peak, Shoulder, Off Peak)
                elif "start" in data:
                    start_val = data["start"]
                    end_val = data["end"]
                    
                    if pd.notna(start_val):
                        df_target.at[index, 'Reading From'] = start_val
                        matches_found += 1
                    if pd.notna(end_val):
                        df_target.at[index, 'Reading To'] = end_val

    return df_target, matches_found

# --- Streamlit UI Layout ---
st.set_page_config(page_title="Meter Reading Populator")

st.title("⚡ Meter Reading Populator")
st.markdown("""
This tool populates the **Reading From** and **Reading To** columns in your Meter Readings file.
Supports **Quarterly**, **Power Smart**, and **Load Smart** billing formats.
""")

st.divider()

# Step 1: Select Type
st.subheader("1. Select Billing Type")
billing_type = st.selectbox(
    "Choose the format of your billing file:",
    list(BILLING_CONFIG.keys())
)

col1, col2 = st.columns(2)

with col1:
    st.subheader("2. Upload Billing File")
    billing_file = st.file_uploader("Upload Billing CSV", type=['csv', 'xlsx'])

with col2:
    st.subheader("3. Upload Target File")
    readings_file = st.file_uploader("Upload Meter Readings File", type=['csv', 'xlsx'])

if billing_file and readings_file:
    st.divider()
    if st.button("Populate Readings", type="primary"):
        with st.spinner("Processing data..."):
            try:
                result_df, count_or_error = process_meter_readings(billing_file, readings_file, billing_type)
                
                if result_df is None:
                    st.error(count_or_error)
                else:
                    st.success(f"Success! Updated {count_or_error} entries.")
                    
                    st.subheader("Preview")
                    st.dataframe(result_df[['Meter No.', 'Reading From', 'Reading To']].head(10))
                    
                    csv = result_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="Download Populated File",
                        data=csv,
                        file_name="Populated_Meter_Readings.csv",
                        mime="text/csv",
                    )
            except Exception as e:
                st.error(f"An error occurred: {e}")
