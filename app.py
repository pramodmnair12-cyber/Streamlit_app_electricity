import streamlit as st
import pandas as pd
import io

# --- Configuration ---
# Only defining Power Smart logic here as requested, 
# but keeping structure expandable.
BILLING_CONFIG = {
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
    # Kept for compatibility if needed later
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
    },
     "Quarterly Billing": {
        "header_row": 1,
        "col_nmi": "NMI",
        "suffixes": {
            "P": {"start": "PEAK_KWH", "end": "PEAK_KWH.1"},
            "A": {"qty": "Availability charge Quantity"}
        }
    }
}

def clean_nmi(val):
    """Robust cleaner for NMI strings."""
    if pd.isna(val):
        return ""
    # Convert to string
    s = str(val).strip()
    # Remove decimal .0 if it exists (common in Excel imports)
    if s.endswith(".0"):
        s = s[:-2]
    return s

def process_meter_readings(billing_file, readings_file, billing_type):
    config = BILLING_CONFIG[billing_type]
    
    # 1. Load Billing Data
    try:
        if billing_file.name.endswith('.csv'):
            df_billing = pd.read_csv(billing_file, header=config["header_row"])
        else:
            df_billing = pd.read_excel(billing_file, header=config["header_row"])
    except Exception as e:
        return None, f"Error reading billing file: {e}"

    # 2. Load Target File
    try:
        if readings_file.name.endswith('.csv'):
            df_target = pd.read_csv(readings_file)
        else:
            df_target = pd.read_excel(readings_file)
    except Exception as e:
        return None, f"Error reading target file: {e}"

    # 3. Build Lookup Dictionary
    # Key = Clean NMI, Value = Data Dictionary
    billing_lookup = {}
    suffixes_config = config["suffixes"]

    for index, row in df_billing.iterrows():
        nmi_val = row.get(config["col_nmi"])
        nmi_clean = clean_nmi(nmi_val)
        
        if not nmi_clean:
            continue
            
        # Store data for this NMI
        nmi_data = {}
        for suffix, mapping in suffixes_config.items():
            if "start" in mapping: # Reading Range
                nmi_data[suffix] = {
                    "start": row.get(mapping["start"]),
                    "end": row.get(mapping["end"])
                }
            elif "qty" in mapping: # Quantity
                nmi_data[suffix] = {
                    "qty": row.get(mapping["qty"])
                }
        
        billing_lookup[nmi_clean] = nmi_data

    # 4. Update Target
    matches_found = 0
    
    # Ensure columns exist
    if 'Reading From' not in df_target.columns:
        df_target['Reading From'] = None
    if 'Reading To' not in df_target.columns:
        df_target['Reading To'] = None
        
    for index, row in df_target.iterrows():
        meter_val = row.get('Meter No.')
        meter_clean = clean_nmi(meter_val)
        
        if len(meter_clean) < 2:
            continue
            
        # Extract NMI and Suffix
        # Logic: Suffix is the last character. NMI is everything before it.
        suffix = meter_clean[-1]
        nmi_base = meter_clean[:-1]
        
        # Check if we have data for this NMI
        if nmi_base in billing_lookup:
            nmi_data = billing_lookup[nmi_base]
            
            # Check if we have data for this Suffix (A, P, S, O, etc.)
            if suffix in nmi_data:
                data = nmi_data[suffix]
                
                # Apply Quantity Logic (Avail/Demand)
                if "qty" in data:
                    val = data["qty"]
                    if pd.notna(val):
                        df_target.at[index, 'Reading From'] = 0
                        df_target.at[index, 'Reading To'] = val
                        matches_found += 1
                        
                # Apply Reading Logic (Peak/Shoulder/OffPeak)
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

    return df_target, matches_found

# --- UI ---
st.set_page_config(page_title="Meter Mapper")
st.title("⚡ Meter Reading Populator")

st.markdown("Matches billing data NMI to target file Meter No (NMI + Suffix).")

billing_type = st.selectbox("Select Billing Type", list(BILLING_CONFIG.keys()))

col1, col2 = st.columns(2)
billing_file = col1.file_uploader("Billing File", type=['csv', 'xlsx'])
readings_file = col2.file_uploader("Target Readings File", type=['csv', 'xlsx'])

if billing_file and readings_file:
    if st.button("Populate"):
        with st.spinner("Processing..."):
            res_df, count = process_meter_readings(billing_file, readings_file, billing_type)
            
            if res_df is None:
                st.error(count) # Error message
            else:
                st.success(f"Done! Updated {count} rows.")
                st.dataframe(res_df.head())
                
                csv = res_df.to_csv(index=False).encode('utf-8')
                st.download_button("Download CSV", csv, "Populated_Readings.csv", "text/csv")
