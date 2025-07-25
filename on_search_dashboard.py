import streamlit as st
import pandas as pd
import datetime
from io import BytesIO

# Set page config
st.set_page_config("On_search data analysis dashboard", layout="wide")

# Title
st.title("On_search data analysis dashboard")
st.markdown("---")

uploaded_file = st.file_uploader("Upload the On-Search Excel File (with both dates)", type=["xlsx"])

@st.cache_data
def load_data(file):
    df = pd.read_excel(file)
    df['Searched On'] = pd.to_datetime(df['Searched On'], errors='coerce')
    df['searched_date'] = df['Searched On'].dt.strftime('%d-%m-%Y')
    df = df.dropna(subset=['searched_date', 'Outlet Name', 'Buyer App'])
    df['dedupe_key'] = df['searched_date'] + "-" + df['Outlet Name'] + "-" + df['Buyer App']
    df = df.drop_duplicates(subset='dedupe_key')
    return df

def get_latest_two_dates(df):
    dates = sorted(df['searched_date'].unique(), key=lambda x: datetime.datetime.strptime(x, '%d-%m-%Y'))
    return dates[-2:] if len(dates) >= 2 else dates

def buyer_app_summary(df, date1, date2):
    df1 = df[df['searched_date'] == date1]
    df2 = df[df['searched_date'] == date2]
    count1 = df1.groupby('Buyer App')['Outlet Name'].nunique()
    count2 = df2.groupby('Buyer App')['Outlet Name'].nunique()
    summary = pd.DataFrame({date1: count1, date2: count2}).fillna(0).astype(int)
    summary['Difference'] = summary[date2] - summary[date1]
    return summary, df1, df2

def get_missing_outlets(df1, df2):
    key1 = set(df1['Outlet Name'] + "|" + df1['Buyer App'])
    key2 = set(df2['Outlet Name'] + "|" + df2['Buyer App'])
    df1['key'] = df1['Outlet Name'] + "|" + df1['Buyer App']
    df2['key'] = df2['Outlet Name'] + "|" + df2['Buyer App']
    only_in_1 = df1[df1['key'].isin(key1 - key2)]
    only_in_2 = df2[df2['key'].isin(key2 - key1)]
    return only_in_1, only_in_2

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

def extract_reason(msg):
    msg = str(msg).lower()
    if "timeout" in msg:
        return "Timeout"
    elif "not found" in msg:
        return "No items found"
    elif "inventory" in msg:
        return "Inventory issue"
    elif "mapped" in msg:
        return "No catalog mapped"
    elif "blank" in msg:
        return "Blank response"
    elif "dropped" in msg:
        return "Provider dropped"
    else:
        return "Other"

def nack_summary(df_today):
    nack_df = df_today[df_today['Status'].str.upper() == 'NACK'].copy()
    nack_df['Reason'] = nack_df['Message'].apply(extract_reason)
    summary = nack_df.groupby(['Buyer App', 'Reason'])['Outlet Name'].nunique().reset_index()
    summary.rename(columns={'Outlet Name': 'Store Count'}, inplace=True)
    summary.insert(0, 'S.No', range(1, len(summary) + 1))  # add serial number
    total_rejected = summary['Store Count'].sum()
    return summary, nack_df, total_rejected

def color_for_value(val, higher_is_bad=True):
    """Return green/yellow/red depending on value."""
    if val == 0:
        return "black"
    if higher_is_bad:
        if val > 50:
            return "red"
        elif val > 20:
            return "orange"
        else:
            return "green"
    else:
        if val > 1000:
            return "green"
        elif val > 500:
            return "orange"
        else:
            return "red"

if uploaded_file:
    df = load_data(uploaded_file)
    dates = get_latest_two_dates(df)

    if len(dates) < 2:
        st.error("Only one date found. Please upload file with at least two different 'Searched On' dates.")
        st.stop()

    date1, date2 = dates
    st.success(f"Analyzing data for: {date1} (Yesterday) and {date2} (Today)")

    summary, df_yesterday, df_today = buyer_app_summary(df, date1, date2)
    only_yesterday, only_today = get_missing_outlets(df_yesterday, df_today)
    nack_sum, nack_df, total_nack = nack_summary(df_today)

    # KPI METRICS
    total_stores_today = df_today['Outlet Name'].nunique()
    total_buyer_apps_today = df_today['Buyer App'].nunique()
    total_nacks = total_nack
    total_stores_yesterday = df_yesterday['Outlet Name'].nunique()
    change_in_coverage = total_stores_today - total_stores_yesterday
    dropped_apps = summary[summary['Difference'] < 0].shape[0]

    colA, colB, colC, colD, colE, colF = st.columns(6)

    colA.metric("Total Stores Today", f"{total_stores_today}", help="Number of unique stores present in today's data")
    colB.metric("Total Stores Yesterday", f"{total_stores_yesterday}", help="Number of unique stores present in yesterday's data")
    colC.metric("Buyer Apps Today", f"{total_buyer_apps_today}", help="Number of unique buyer applications in today's data")
    colD.metric("Rejected Stores (NACK) - all buyer app", f"{total_nacks}", help="Total count of rejected stores (NACK) across all buyer apps")
    colE.metric("Net Change in Stores", f"{change_in_coverage}", delta=f"{change_in_coverage:+}", help="Difference between today's and yesterday's total stores")
    colF.metric("Apps with Store Drop", f"{dropped_apps}", help="Count of buyer apps with store count drop since yesterday")

    st.markdown("---")

    st.markdown("### Buyer App Store Count Comparison")
    st.dataframe(summary, use_container_width=True)
    st.download_button("Download Comparison", to_excel(summary), "buyer_app_comparison.xlsx")

    st.markdown("### Missing Store Lists")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Stores present yesterday but missing today ({len(only_yesterday)})**")
        st.dataframe(only_yesterday[['Outlet Name', 'Buyer App', 'City Code']], use_container_width=True)
        st.download_button("Download Missing Today", to_excel(only_yesterday), "missing_today.xlsx")
    with col2:
        st.markdown(f"**Stores present today but not yesterday ({len(only_today)})**")
        st.dataframe(only_today[['Outlet Name', 'Buyer App', 'City Code']], use_container_width=True)
        st.download_button("Download Missing Yesterday", to_excel(only_today), "missing_yesterday.xlsx")

    st.markdown("### Today's Rejected Stores Summary")
    st.markdown(f"**Total Rejected Stores: {total_nack}**")

    nack_sum_display = nack_sum.set_index("S.No")
    st.dataframe(nack_sum_display, use_container_width=True)
    st.download_button("Download NACKs", to_excel(nack_df), "nack_details.xlsx")