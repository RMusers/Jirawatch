import streamlit as st
from jira import JIRA
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIG ---
st.set_page_config(page_title="Jira Live Monitor", page_icon="📊", layout="wide")
st_autorefresh(interval=15 * 60 * 1000, key="jiralivedash")

# --- 2. AUTH ---
try:
    JIRA_SERVER = st.secrets["jira"]["server"].rstrip('/')
    JIRA_USER = st.secrets["jira"]["user"]
    JIRA_PASS = st.secrets["jira"]["password"]
except KeyError:
    st.error("Missing credentials in .streamlit/secrets.toml")
    st.stop()

def fetch_today_issues():
    try:
        jira = JIRA(server=JIRA_SERVER, basic_auth=(JIRA_USER, JIRA_PASS), options={'check_update': False})
        jql = "creator = currentUser() AND created >= startOfDay() ORDER BY created DESC"
        issues = jira.search_issues(jql, maxResults=100)
        
        if not issues: return pd.DataFrame(), ""

        data = []
        calendar_label = ""
        
        for issue in issues:
            status = issue.fields.status.name
            raw_type = issue.fields.issuetype.name
            
            # --- Capture Label from Calendar Event ---
            if "Calendar Event" in raw_type and not calendar_label:
                labels = getattr(issue.fields, 'labels', [])
                calendar_label = " | ".join(labels) if labels else ""

            parent_key = getattr(issue.fields, 'parent', None)
            parent_id = parent_key.key if parent_key else issue.key

            s_icon = "✅" if status.upper() in ["DONE", "RESOLVED", "CLOSED"] else "🟡" if "PROGRESS" in status.upper() else "🔵"
            is_sub = getattr(issue.fields.issuetype, 'subtask', False)
            t_prefix = "┖ " if is_sub else ""
            t_icon = "📅" if "Calendar" in raw_type else "🐞" if "Bug" in raw_type else "📖" if "Story" in raw_type else "📄"

            data.append({
                "Status Icon": s_icon,
                "Type": f"{t_prefix}{t_icon} {raw_type}",
                "Url": f"{JIRA_SERVER}/browse/{issue.key}",
                "Summary": issue.fields.summary,
                "Status": status,
                "Priority": issue.fields.priority.name,
                "_parent_id": parent_id
            })
        
        df = pd.DataFrame(data)
        
        # Sorting
        def get_status_weight(val):
            v = val.upper()
            if "RESOLVED" in v or "PROGRESS" in v: return 1
            if "OPEN" in v or "TO DO" in v or "NEW" in v: return 2
            return 3

        df['_status_sort'] = df['Status'].apply(get_status_weight)
        df = df.sort_values(by=["_status_sort", "_parent_id", "Type"])
        
        return df.drop(columns=["_status_sort", "_parent_id"]), calendar_label

    except Exception as e:
        st.error(f"Sync Error: {e}")
        return pd.DataFrame(), ""

# --- 3. STATE MANAGEMENT ---
if 'df' not in st.session_state:
    df, label = fetch_today_issues()
    st.session_state.df = df
    st.session_state.dynamic_label = label
    st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")

# --- 4. TOP BAR (Dynamic Title) ---
t_col1, t_col2 = st.columns([9, 1]) 
with t_col1:
    # Uses the label if found, else the default title
    display_title = st.session_state.dynamic_label if st.session_state.dynamic_label else "Daily Jira Monitor (Live)"
    st.markdown(f"### 📊 {display_title}")
    st.caption(f"Last sync: {st.session_state.last_refresh} | User: {JIRA_USER}")

with t_col2:
    if st.button('🔄', use_container_width=False):
        df, label = fetch_today_issues()
        st.session_state.df = df
        st.session_state.dynamic_label = label
        st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")
        st.rerun()

st.divider()

# --- 5. PANELS ---
panel_left, panel_right = st.columns([1, 4], gap="large")

with panel_left:
    st.markdown("#### 📌 Metadata")
    df = st.session_state.df
    if not df.empty:
        st.metric("Total Tasks", len(df))
        done = len(df[df['Status Icon'] == "✅"])
        st.metric("Completed", done)
        st.progress(done / len(df) if len(df) > 0 else 0)

with panel_right:
    if not df.empty:
        st.dataframe(
            df[["Status Icon", "Type", "Url", "Summary", "Status", "Priority"]],
            column_config={
                "Url": st.column_config.LinkColumn("Key", display_text=r"([A-Z]+-\d+)"),
                "Summary": st.column_config.TextColumn("Summary", width="large"),
            },
            use_container_width=True,
            hide_index=True,
            height="content" 
        )
    else:
        st.warning("Nothing logged for today.")
