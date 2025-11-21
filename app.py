import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import re
import time

# --- Page Configuration ---
st.set_page_config(
    page_title="SMS Dashboard",
    page_icon="📱",
    layout="centered"
)

# --- Helper Functions ---
def extract_sheet_id(url):
    """Extracts the Google Sheet ID from a full URL."""
    pattern = r'/d/([a-zA-Z0-9-_]+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None

def get_gspread_client():
    """Authenticates with Google Sheets using Streamlit Secrets."""
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    # st.secrets converts the TOML section to a dictionary automatically
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# --- UI Layout ---
st.title("📱 SMS Campaign Dashboard")
st.markdown("**Role:** Senior Admin | **Goal:** Send bulk SMS via Twilio & Google Sheets")
st.divider()

# --- Step 1: Load Data ---
st.header("1️⃣ Load Contacts")

sheet_url = st.text_input("Paste Google Sheet URL:", placeholder="https://docs.google.com/spreadsheets/d/...")

if sheet_url:
    sheet_id = extract_sheet_id(sheet_url)
    if not sheet_id:
        st.warning("⚠️ Invalid URL. Please paste the full link to the Google Sheet.")
    else:
        try:
            with st.spinner("Connecting to Google Sheets..."):
                client = get_gspread_client()
                sheet = client.open_by_key(sheet_id).sheet1
                data = sheet.get_all_records()
                df = pd.DataFrame(data)

            if df.empty:
                st.error("⚠️ The sheet appears to be empty.")
            else:
                st.success("✅ Data Loaded Successfully!")
                
                # --- Step 2: Data Preview & Configuration ---
                st.header("2️⃣ Preview & Configure")
                st.dataframe(df.head(), use_container_width=True)
                
                # Column Selection
                all_columns = df.columns.tolist()
                phone_col = st.selectbox("Select the column containing Phone Numbers:", all_columns, index=0)
                
                # Clean Phone Numbers (Basic logic: force string, strip spaces)
                df[phone_col] = df[phone_col].astype(str).str.strip()
                
                row_count = len(df)
                st.info(f"📊 Total Contacts: **{row_count}**")

                # --- Step 3: Compose Message ---
                st.header("3️⃣ Compose Message")
                # UPDATED: max_chars set to 160 for standard SMS limit
                message_body = st.text_area("Type your SMS content (Max 160 chars):", height=150, max_chars=160)
                
                # Real-time character counter logic is handled by Streamlit's max_chars automatically
                # but we can show remaining explicitly if needed
                char_count = len(message_body)
                st.caption(f"Characters used: {char_count}/160")

                # Cost Estimator
                estimated_cost = row_count * 0.03
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(label="Estimated Cost ($0.03/msg)", value=f"${estimated_cost:.2f}")
                with col2:
                    st.metric(label="Total Messages", value=row_count)

                # --- Step 4: Send SMS ---
                st.header("4️⃣ Launch Campaign")
                
                if st.button("🚀 Send SMS Now", type="primary"):
                    if not message_body:
                        st.warning("⚠️ Please enter a message before sending.")
                    else:
                        # Twilio Auth
                        try:
                            twilio_sid = st.secrets["twilio"]["account_sid"]
                            twilio_token = st.secrets["twilio"]["auth_token"]
                            twilio_from = st.secrets["twilio"]["from_number"]
                            twilio_client = Client(twilio_sid, twilio_token)
                        except KeyError:
                            st.error("❌ Twilio credentials missing in secrets.toml")
                            st.stop()

                        # Progress Bar & Counters
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        success_count = 0
                        fail_count = 0
                        failed_numbers = []

                        # Sending Loop
                        for index, row in df.iterrows():
                            number = row[phone_col]
                            try:
                                # Send Message
                                message = twilio_client.messages.create(
                                    body=message_body,
                                    from_=twilio_from,
                                    to=number
                                )
                                success_count += 1
                            except TwilioRestException as e:
                                fail_count += 1
                                failed_numbers.append(f"{number} ({e.msg})")
                            except Exception as e:
                                fail_count += 1
                                failed_numbers.append(f"{number} (Unknown Error)")
                            
                            # Update Progress
                            progress = (index + 1) / row_count
                            progress_bar.progress(progress)
                            status_text.text(f"Processing: {index + 1}/{row_count}")
                            time.sleep(0.1) # Slight delay to respect API rate limits nicely

                        # Final Report
                        progress_bar.empty()
                        status_text.empty()
                        
                        st.success("🎉 Campaign Completed!")
                        
                        res_col1, res_col2 = st.columns(2)
                        res_col1.metric("✅ Sent Successfully", success_count)
                        res_col2.metric("❌ Failed", fail_count)

                        if failed_numbers:
                            with st.expander("View Failed Numbers"):
                                st.write(failed_numbers)

        except gspread.exceptions.APIError:
            st.error("⚠️ Permission Denied: Please share the Google Sheet with the Service Account Email found in your secrets.")
        except gspread.exceptions.SheetNotFound:
            st.error("⚠️ Sheet Not Found: Check the URL.")
        except Exception as e:
            st.error(f"⚠️ An unexpected error occurred: {str(e)}")