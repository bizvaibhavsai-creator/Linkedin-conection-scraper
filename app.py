import csv
import io
import os
import re

import streamlit as st

from linkedin_scraper.scraper import run

# Detect if running on a server (no display)
IS_SERVER = not os.environ.get("DISPLAY") and os.name != "nt" and not os.environ.get("__CFBundleIdentifier")

st.set_page_config(page_title="LinkedIn Connection Scraper", layout="centered")

st.title("LinkedIn Connection Scraper")
st.caption("Scrape visible connections from any LinkedIn profile.")

# --- Input Section ---
profile_url = st.text_input(
    "LinkedIn Profile URL",
    placeholder="https://www.linkedin.com/in/username",
)

if IS_SERVER:
    auth_method = "Cookie Import"
    st.info("Running on server — cookie import is the only auth method available.")
else:
    auth_method = st.radio(
        "Authentication Method",
        options=["Browser Login", "Cookie Import"],
        help="Browser Login opens a Chromium window for you to log in manually. Cookies are saved for reuse.",
    )

cookie_string = None
if auth_method == "Cookie Import":
    cookie_string = st.text_area(
        "Cookie String",
        placeholder='li_at=AQEDAx...; JSESSIONID="ajax:987..."',
        help="Paste your LinkedIn cookies from browser dev tools (Application > Cookies).",
    )

# --- Scrape Button ---
if st.button("Start Scraping", type="primary", use_container_width=True):
    # Validate URL
    if not profile_url or not re.search(r"linkedin\.com/in/[^/?#]+", profile_url):
        st.error("Please enter a valid LinkedIn profile URL (e.g. https://www.linkedin.com/in/username).")
    elif auth_method == "Cookie Import" and not cookie_string:
        st.error("Please provide a cookie string for cookie-based authentication.")
    else:
        status_container = st.status("Scraping connections...", expanded=True)
        count_placeholder = status_container.empty()

        def on_progress(count):
            count_placeholder.write(f"Found **{count}** connections so far...")

        try:
            count_placeholder.write("Launching browser and authenticating...")

            connections = run(
                profile_url=profile_url,
                auth_method="cookies" if auth_method == "Cookie Import" else "browser",
                cookie_string=cookie_string,
                headless=IS_SERVER,
                progress_callback=on_progress,
            )

            status_container.update(label="Scraping complete!", state="complete")
            st.session_state["connections"] = connections

        except PermissionError as e:
            status_container.update(label="Failed", state="error")
            st.error(str(e))
        except ValueError as e:
            status_container.update(label="Failed", state="error")
            st.error(str(e))
        except TimeoutError as e:
            status_container.update(label="Timed out", state="error")
            st.error(str(e))
        except Exception as e:
            status_container.update(label="Error", state="error")
            st.error(f"Scraping failed: {e}")

# --- Results Section ---
if "connections" in st.session_state and st.session_state["connections"]:
    connections = st.session_state["connections"]

    st.divider()
    st.metric("Connections Found", len(connections))
    st.dataframe(
        connections,
        use_container_width=True,
        column_config={
            "name": "Name",
            "headline": "Headline",
            "profile_url": st.column_config.LinkColumn("Profile URL", display_text="View"),
            "location": "Location",
        },
    )

    # Build CSV for download
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["name", "headline", "profile_url", "location"])
    writer.writeheader()
    writer.writerows(connections)
    csv_data = output.getvalue()

    st.download_button(
        label="Download CSV",
        data=csv_data,
        file_name="linkedin_connections.csv",
        mime="text/csv",
        use_container_width=True,
    )
elif "connections" in st.session_state:
    st.warning("No connections found. The profile may have no visible connections.")
