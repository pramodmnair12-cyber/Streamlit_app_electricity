import streamlit as st
import pandas as pd
import io

def process_meter_readings(billing_file, readings_file):
    # 1. Load the Data
    # Billing file has the header on the second row (index 1)
    df_billing = pd.read_csv(billing_file, header=1)
    
    # Readings file might be CSV or Excel
    try:
        df_target = pd.read_csv(readings_file)
    except:
        df_target = pd.read_excel(readings_file)

    # 2. Build Lookup Dictionary from Billing Data
    # Key: NMI (string), Value: dict of values
    billing_lookup = {}

    for index, row in df_billing.iterrows():
        # Clean NMI
        raw_nmi = row['NMI']
        if pd.isna(raw_nmi):
            continue
        
        # Ensure NMI is a string without .0
        nmi_str = str(raw_nmi)
        if nmi_str.endswith('.0'):
            nmi_str = nmi_str[:-2]
            
        billing_lookup[nmi_str] = {
            'Peak_Start': row.get('PEAK_KWH'),
            'Peak_End': row.get('PEAK_KWH.1'), # usually the closing reading
            'Avail_Qty': row.get('Availability charge Quantity')
        }

    # 3. Update the Target DataFrame
    matches_found = 0
    
    # Ensure columns exist and are float/numeric to avoid type errors
    if 'Reading From' not in df_target.columns:
        df_target['Reading From'] = None
    if 'Reading To' not in df_target.columns:
        df_target['Reading To'] = None
        
    for index, row in df_target.iterrows():
        meter_no = str(row['Meter No.'])
        
        # Check to ensure meter_no is valid
        if len(meter_no) < 2:
            continue
            
        suffix = meter_no[-1]
        nmi_base = meter_no[:-1]
        
        # Check if we have data for this NMI
        if nmi_base in billing_lookup:
            data = billing_lookup[nmi_base]
            matches_found += 1
            
            if suffix == 'P':
                # Peak: Update From and To
                p_start = data['Peak_Start']
                p_end = data['Peak_End']
                
                # Only update if values exist in billing
                if pd.notna(p_start):
                    df_target.at[index, 'Reading From'] = p_start
                if pd.notna(p_end):
                    df_target.at[index, 'Reading To'] = p_end
                    
            elif suffix == 'A':
                # Availability: Update To (as Quantity) and From (as 0)
                avail_qty = data['Avail_Qty']
                
                if pd.notna(avail_qty):
                    df_target.at[index, 'Reading From'] = 0
                    df_target.at[index, 'Reading To'] = avail_qty

    return df_target, matches_found

# --- Streamlit UI Layout ---
st.set_page_config(page_title="Meter Reading Populator")

st.title("⚡ Meter Reading Populator")
st.markdown("""
This tool populates the **Reading From** and **Reading To** columns in your Meter Readings file 
based on the data in your Quarterly Billing file.
""")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Quarterly Billing")
    billing_file = st.file_uploader("Upload Billing CSV", type=['csv'])

with col2:
    st.subheader("2. Meter Readings")
    readings_file = st.file_uploader("Upload Meter Readings File", type=['csv', 'xlsx'])

if billing_file and readings_file:
    st.divider()
    if st.button("Populate Readings", type="primary"):
        with st.spinner("Processing data..."):
            try:
                # Run the logic
                result_df, count = process_meter_readings(billing_file, readings_file)
                
                # Success Message
                st.success(f"Success! Updated {count} meter entries.")
                
                # Preview
                st.subheader("Preview of Populated Data")
                st.dataframe(result_df[['Meter No.', 'Reading From', 'Reading To']].head(10))
                
                # Convert to CSV for download
                csv = result_df.to_csv(index=False).encode('utf-8')
                
                st.download_button(
                    label="Download Populated File",
                    data=csv,
                    file_name="Populated_Meter_Readings.csv",
                    mime="text/csv",
                )
            except Exception as e:
                st.error(f"An error occurred: {e}")