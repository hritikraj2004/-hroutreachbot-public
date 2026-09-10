import streamlit as st
import pandas as pd
import requests
import base64
import time
import uuid
import hmac
import hashlib
import os

from datetime import datetime
from urllib.parse import urlencode

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


# =========================================================
# PAGE
# =========================================================

st.set_page_config(
    page_title="HR Outreach Bot",
    page_icon="📧",
    layout="wide"
)


# =========================================================
# TRACKER
# =========================================================

TRACKER_FILE = "outreach_tracker.csv"

TRACKER_COLUMNS = [
    "Sr No",
    "Company",
    "Email",
    "Person Name",
    "Subject",
    "Status",
    "Sent At",
    "Message ID",
    "Error"
]


def create_empty_tracker():

    return pd.DataFrame(
        columns=TRACKER_COLUMNS
    )


def normalize_tracker(df):

    for column in TRACKER_COLUMNS:

        if column not in df.columns:

            df[column] = ""


    df = df[
        TRACKER_COLUMNS
    ].copy()


    for column in TRACKER_COLUMNS:

        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
        )


    return df


def load_tracker():

    if not os.path.exists(
        TRACKER_FILE
    ):

        return create_empty_tracker()


    try:

        tracker = pd.read_csv(
            TRACKER_FILE,
            dtype=str,
            keep_default_na=False
        )

        return normalize_tracker(
            tracker
        )

    except Exception as e:

        st.warning(
            f"Tracker could not be read: {e}"
        )

        return create_empty_tracker()


def save_tracker(tracker):

    tracker = normalize_tracker(
        tracker
    )

    tracker.to_csv(
        TRACKER_FILE,
        index=False,
        encoding="utf-8-sig"
    )


def initialize_tracker(
    excel_df,
    subject
):

    tracker = load_tracker()

    df = excel_df.copy()


    # -----------------------------------------------------
    # Clean Excel data
    # -----------------------------------------------------

    for column in [
        "Email",
        "Company",
        "Person Name"
    ]:

        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )


    # Remove blank emails
    df = df[
        df["Email"] != ""
    ].copy()


    # Remove duplicate emails
    df = df.drop_duplicates(
        subset=["Email"],
        keep="first"
    )


    # -----------------------------------------------------
    # Create fresh tracker if none exists
    # -----------------------------------------------------

    if tracker.empty:

        rows = []

        for _, row in df.iterrows():

            rows.append({

                "Sr No": str(
                    row.get(
                        "Sr. No",
                        ""
                    )
                ),

                "Company": str(
                    row.get(
                        "Company",
                        ""
                    )
                ),

                "Email": str(
                    row.get(
                        "Email",
                        ""
                    )
                ),

                "Person Name": str(
                    row.get(
                        "Person Name",
                        ""
                    )
                ),

                "Subject": str(
                    subject
                ),

                "Status": "PENDING",

                "Sent At": "",

                "Message ID": "",

                "Error": ""
            })


        tracker = pd.DataFrame(
            rows,
            columns=TRACKER_COLUMNS
        )


        tracker = normalize_tracker(
            tracker
        )


        save_tracker(
            tracker
        )


        return tracker


    # -----------------------------------------------------
    # Existing tracker
    # -----------------------------------------------------

    existing_emails = set(

        tracker[
            "Email"
        ]
        .astype(str)
        .str.strip()
        .str.lower()
        .tolist()
    )


    new_rows = []


    for _, row in df.iterrows():

        email = str(
            row.get(
                "Email",
                ""
            )
        ).strip()


        if not email:

            continue


        if email.lower() in existing_emails:

            continue


        new_rows.append({

            "Sr No": str(
                row.get(
                    "Sr. No",
                    ""
                )
            ),

            "Company": str(
                row.get(
                    "Company",
                    ""
                )
            ),

            "Email": email,

            "Person Name": str(
                row.get(
                    "Person Name",
                    ""
                )
            ),

            "Subject": str(
                subject
            ),

            "Status": "PENDING",

            "Sent At": "",

            "Message ID": "",

            "Error": ""
        })


    # -----------------------------------------------------
    # Add new contacts
    # -----------------------------------------------------

    if new_rows:

        new_df = pd.DataFrame(
            new_rows,
            columns=TRACKER_COLUMNS
        )

        tracker = pd.concat(
            [
                tracker,
                new_df
            ],
            ignore_index=True
        )


    tracker = normalize_tracker(
        tracker
    )


    tracker = tracker.drop_duplicates(
        subset=["Email"],
        keep="first"
    )


    tracker = normalize_tracker(
        tracker
    )


    save_tracker(
        tracker
    )


    return tracker


def update_tracker_success(
    email,
    message_id,
    subject
):

    tracker = load_tracker()

    email = str(
        email
    ).strip()


    mask = (
        tracker["Email"]
        .str.strip()
        .str.lower()
        == email.lower()
    )


    if not mask.any():

        return False


    tracker.loc[
        mask,
        "Status"
    ] = "SENT"


    tracker.loc[
        mask,
        "Sent At"
    ] = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


    tracker.loc[
        mask,
        "Message ID"
    ] = str(
        message_id
    )


    tracker.loc[
        mask,
        "Subject"
    ] = str(
        subject
    )


    tracker.loc[
        mask,
        "Error"
    ] = ""


    save_tracker(
        tracker
    )


    return True


def update_tracker_failed(
    email,
    error,
    subject
):

    tracker = load_tracker()

    email = str(
        email
    ).strip()


    mask = (
        tracker["Email"]
        .str.strip()
        .str.lower()
        == email.lower()
    )


    if not mask.any():

        return False


    tracker.loc[
        mask,
        "Status"
    ] = "FAILED"


    tracker.loc[
        mask,
        "Error"
    ] = str(
        error
    )


    tracker.loc[
        mask,
        "Subject"
    ] = str(
        subject
    )


    save_tracker(
        tracker
    )


    return True


# =========================================================
# GOOGLE OAUTH
# =========================================================

CLIENT_ID = st.secrets[
    "auth"
][
    "client_id"
]


CLIENT_SECRET = st.secrets[
    "auth"
][
    "client_secret"
]


REDIRECT_URI = (
    "https://hroutreachbot-public.streamlit.app/oauth2callback"
)


AUTHORIZATION_ENDPOINT = (
    "https://accounts.google.com/o/oauth2/v2/auth"
)


TOKEN_ENDPOINT = (
    "https://oauth2.googleapis.com/token"
)


USERINFO_ENDPOINT = (
    "https://openidconnect.googleapis.com/v1/userinfo"
)


SCOPES = [
    "openid",
    "profile",
    "email",
    "https://www.googleapis.com/auth/gmail.send"
]


# =========================================================
# SESSION STATE
# =========================================================

if "google_token" not in st.session_state:

    st.session_state.google_token = None


if "google_user" not in st.session_state:

    st.session_state.google_user = None


if "outreach_running" not in st.session_state:

    st.session_state.outreach_running = False


if "sent_this_session" not in st.session_state:

    st.session_state.sent_this_session = set()


# =========================================================
# OAUTH SECURITY
# =========================================================

def get_state_secret():

    secret = st.secrets[
        "auth"
    ][
        "cookie_secret"
    ]

    return str(
        secret
    ).encode(
        "utf-8"
    )


def create_signed_state():

    nonce = uuid.uuid4().hex

    timestamp = str(
        int(time.time())
    )


    payload = (
        f"{nonce}:{timestamp}"
    )


    signature = hmac.new(

        get_state_secret(),

        payload.encode(
            "utf-8"
        ),

        hashlib.sha256

    ).hexdigest()


    return (
        f"{payload}:{signature}"
    )


def verify_signed_state(
    state
):

    try:

        parts = state.split(":")


        if len(parts) != 3:

            return False


        timestamp = parts[1]

        signature = parts[2]


        payload = (
            f"{parts[0]}:{timestamp}"
        )


        expected_signature = hmac.new(

            get_state_secret(),

            payload.encode(
                "utf-8"
            ),

            hashlib.sha256

        ).hexdigest()


        if not hmac.compare_digest(

            signature,

            expected_signature

        ):

            return False


        age = (
            int(time.time())
            - int(timestamp)
        )


        if age < 0 or age > 600:

            return False


        return True


    except Exception:

        return False


# =========================================================
# GOOGLE AUTH URL
# =========================================================

def create_google_auth_url():

    state = create_signed_state()


    params = {

        "client_id":
            CLIENT_ID,

        "redirect_uri":
            REDIRECT_URI,

        "response_type":
            "code",

        "scope":
            " ".join(
                SCOPES
            ),

        "access_type":
            "offline",

        "prompt":
            "consent",

        "state":
            state
    }


    return (

        AUTHORIZATION_ENDPOINT

        + "?"

        + urlencode(params)
    )


# =========================================================
# TOKEN EXCHANGE
# =========================================================

def exchange_code_for_token(
    code
):

    data = {

        "code":
            code,

        "client_id":
            CLIENT_ID,

        "client_secret":
            CLIENT_SECRET,

        "redirect_uri":
            REDIRECT_URI,

        "grant_type":
            "authorization_code"
    }


    response = requests.post(

        TOKEN_ENDPOINT,

        data=data,

        timeout=30
    )


    response.raise_for_status()


    token_data = (
        response.json()
    )


    if "access_token" not in token_data:

        raise Exception(
            "Google did not return "
            "an access token."
        )


    if "expires_in" in token_data:

        token_data[
            "expires_at"
        ] = (

            time.time()

            + token_data[
                "expires_in"
            ]
        )


    return token_data


# =========================================================
# GOOGLE USER
# =========================================================

def get_google_user(
    access_token
):

    response = requests.get(

        USERINFO_ENDPOINT,

        headers={

            "Authorization":
            f"Bearer {access_token}"
        },

        timeout=30
    )


    response.raise_for_status()


    return response.json()


# =========================================================
# GOOGLE CREDENTIALS
# =========================================================

def build_google_credentials():

    token_data = (
        st.session_state.google_token
    )


    if not token_data:

        return None


    access_token = (
        token_data.get(
            "access_token"
        )
    )


    refresh_token = (
        token_data.get(
            "refresh_token"
        )
    )


    if not access_token:

        return None


    credentials = Credentials(

        token=access_token,

        refresh_token=refresh_token,

        token_uri=TOKEN_ENDPOINT,

        client_id=CLIENT_ID,

        client_secret=CLIENT_SECRET,

        scopes=SCOPES
    )


    if token_data.get(
        "expires_at"
    ):

        credentials.expiry = (
            datetime.fromtimestamp(
                token_data[
                    "expires_at"
                ]
            )
        )


    # -----------------------------------------------------
    # AUTOMATIC REFRESH
    # -----------------------------------------------------

    if credentials.expired:

        if not credentials.refresh_token:

            raise Exception(
                "Access token expired but "
                "refresh token is not available."
            )


        credentials.refresh(
            Request()
        )


        st.session_state.google_token[
            "access_token"
        ] = credentials.token


        if credentials.expiry:

            st.session_state.google_token[
                "expires_at"
            ] = (
                credentials.expiry.timestamp()
            )


    return credentials


# =========================================================
# GOOGLE CALLBACK
# =========================================================

query_params = st.query_params


code = query_params.get(
    "code"
)


returned_state = query_params.get(
    "state"
)


oauth_error = query_params.get(
    "error"
)


if oauth_error:

    st.error(
        f"Google authorization failed: "
        f"{oauth_error}"
    )

    st.query_params.clear()


if (

    code

    and not st.session_state.google_token

):

    try:

        if not returned_state:

            raise Exception(
                "Missing OAuth security state."
            )


        if not verify_signed_state(
            returned_state
        ):

            raise Exception(
                "OAuth security check failed. "
                "Please login again."
            )


        with st.spinner(
            "Completing Google authorization..."
        ):

            token_data = (
                exchange_code_for_token(
                    code
                )
            )


            st.session_state.google_token = (
                token_data
            )


            st.session_state.google_user = (
                get_google_user(

                    token_data[
                        "access_token"
                    ]

                )
            )


            st.query_params.clear()


            st.rerun()


   except Exception as e:
    st.error("GOOGLE CALLBACK ERROR")
    st.exception(e)


# =========================================================
# HEADER
# =========================================================

st.title(
    "📧 HR Outreach Bot"
)


st.write(
    "Personalized recruiter outreach "
    "using Gmail API."
)


# =========================================================
# LOGIN
# =========================================================

if not st.session_state.google_token:

    st.info(
        "Login with Google to authorize "
        "Gmail sending."
    )


    auth_url = (
        create_google_auth_url()
    )


    st.markdown(

        f"""
        <a href="{auth_url}"
           target="_self"
           style="
               display:inline-block;
               padding:0.65rem 1rem;
               border:1px solid #555;
               border-radius:0.5rem;
               text-decoration:none;
               font-weight:600;
               color:inherit;
           ">
            🔐 Login with Google
        </a>
        """,

        unsafe_allow_html=True
    )


    st.stop()


# =========================================================
# LOGGED-IN USER
# =========================================================

user_email = (
    "Google Account"
)


if st.session_state.google_user:

    user_email = (
        st.session_state.google_user.get(
            "email",
            "Google Account"
        )
    )


st.success(
    f"Logged in as: {user_email}"
)


# =========================================================
# LOGOUT
# =========================================================

if st.button(
    "Logout"
):

    st.session_state.google_token = None

    st.session_state.google_user = None

    st.session_state.sent_this_session = set()

    st.rerun()


# =========================================================
# GMAIL AUTH
# =========================================================

try:

    gmail_credentials = (
        build_google_credentials()
    )


    if not gmail_credentials:

        st.error(
            "Gmail authorization unavailable."
        )

        st.stop()


    st.success(
        "✅ Gmail authorization active"
    )


except Exception as e:

    st.error(
        f"Gmail authorization error: {e}"
    )

    st.stop()


# =========================================================
# REFRESH TOKEN
# =========================================================

has_refresh_token = bool(

    st.session_state.google_token.get(
        "refresh_token"
    )
)


if has_refresh_token:

    st.success(
        "🔄 Refresh token available"
    )

else:

    st.error(
        "❌ Refresh token NOT available"
    )


# =========================================================
# TOKEN REFRESH TEST
# =========================================================

st.divider()

st.subheader(
    "🔄 Token Refresh Test"
)


if has_refresh_token:

    if st.button(
        "🔄 Test Automatic Token Refresh"
    ):

        try:

            # Force token expiry
            st.session_state.google_token[
                "expires_at"
            ] = (
                time.time()
                - 10
            )


            refreshed_credentials = (
                build_google_credentials()
            )


            if (

                refreshed_credentials

                and refreshed_credentials.token

            ):

                st.success(
                    "🎉 Automatic token refresh SUCCESSFUL!"
                )


                st.write(
                    "Fresh access token obtained."
                )


        except Exception as e:

            st.error(
                f"❌ Token refresh failed: {e}"
            )


# =========================================================
# EXCEL
# =========================================================

st.divider()

st.subheader(
    "1️⃣ Upload Recruiter Database"
)


excel_file = st.file_uploader(

    "Upload Excel file",

    type=["xlsx"]
)


df = None


if excel_file:

    try:

        df = pd.read_excel(

            excel_file,

            header=2
        )


        required_columns = [

            "Email",

            "Company",

            "Person Name"
        ]


        missing_columns = [

            column

            for column in required_columns

            if column not in df.columns
        ]


        if missing_columns:

            st.error(

                "Missing columns: "

                + ", ".join(
                    missing_columns
                )
            )

            st.stop()


        # Clean
        for column in [
            "Email",
            "Company",
            "Person Name"
        ]:

            df[column] = (

                df[column]

                .fillna("")

                .astype(str)

                .str.strip()
            )


        df = df[
            df["Email"] != ""
        ].copy()


        df = df.drop_duplicates(

            subset=["Email"],

            keep="first"
        )


        st.success(

            f"Excel loaded: "
            f"{len(df)} valid contacts"
        )


        st.dataframe(

            df.head(10),

            use_container_width=True
        )


        # -------------------------------------------------
        # Tracker
        # -------------------------------------------------

        tracker = initialize_tracker(

            df,

            subject=(
                "Referral Request – "
                "Entry-Level QA Analyst Opportunity"
            )
        )


        st.success(

            f"Permanent tracker ready: "
            f"{len(tracker)} contacts"
        )


        # Stats
        sent_total = int(

            (
                tracker["Status"]
                == "SENT"
            ).sum()
        )


        pending_total = int(

            (
                tracker["Status"]
                == "PENDING"
            ).sum()
        )


        failed_total = int(

            (
                tracker["Status"]
                == "FAILED"
            ).sum()
        )


        c1, c2, c3 = st.columns(3)


        with c1:

            st.metric(
                "✅ SENT",
                sent_total
            )


        with c2:

            st.metric(
                "⏳ PENDING",
                pending_total
            )


        with c3:

            st.metric(
                "❌ FAILED",
                failed_total
            )


    except Exception as e:

        st.error(
            f"Could not read Excel: {e}"
        )

        st.stop()


# =========================================================
# RESUME
# =========================================================

st.divider()

st.subheader(
    "2️⃣ Upload Resume"
)


resume_file = st.file_uploader(

    "Upload your PDF resume",

    type=["pdf"]
)


resume_bytes = None


if resume_file:

    resume_bytes = (
        resume_file.read()
    )


    st.success(

        f"Resume loaded: "
        f"{resume_file.name}"
    )


# =========================================================
# EMAIL SETTINGS
# =========================================================

st.divider()

st.subheader(
    "3️⃣ Email Settings"
)


subject = st.text_input(

    "Email Subject",

    value=(
        "Referral Request – "
        "Entry-Level QA Analyst Opportunity"
    )
)


default_body = """Hi {person_name},

I hope you are doing well.

My name is Hritik Raj, and I am a QA Analyst / Manual Tester with a BCA background.

I am currently looking for entry-level QA opportunities and wanted to reach out regarding opportunities at {company}.

If there is any suitable QA opening or if you could refer me to the appropriate opportunity, I would really appreciate it.

I have attached my resume for your reference.

Thank you for your time.

Best regards,
Hritik Raj
QA Analyst | Manual Tester
"""


email_template = st.text_area(

    "Email Body",

    value=default_body,

    height=300
)


# =========================================================
# PREVIEW
# =========================================================

if df is not None and len(df) > 0:

    st.divider()

    st.subheader(
        "4️⃣ Email Preview"
    )


    tracker = load_tracker()


    pending = tracker[

        tracker["Status"]
        == "PENDING"

    ]


    if not pending.empty:

        preview_row = pending.iloc[0]

    else:

        preview_row = df.iloc[0]


    preview_email = str(

        preview_row.get(
            "Email",
            ""
        )

    ).strip()


    preview_person = str(

        preview_row.get(
            "Person Name",
            ""
        )

    ).strip()


    preview_company = str(

        preview_row.get(
            "Company",
            ""
        )

    ).strip()


    preview_body = (

        email_template

        .replace(
            "{person_name}",
            preview_person
        )

        .replace(
            "{company}",
            preview_company
        )
    )


    st.write(
        f"**To:** {preview_email}"
    )


    st.write(
        f"**Subject:** {subject}"
    )


    st.text_area(

        "Preview",

        value=preview_body,

        height=300,

        disabled=True
    )


# =========================================================
# OUTREACH SETTINGS
# =========================================================

st.divider()

st.subheader(
    "5️⃣ Outreach Settings"
)


col1, col2 = st.columns(2)


with col1:

    daily_limit = st.number_input(

        "Emails per session",

        min_value=1,

        max_value=100,

        value=1,

        step=1
    )


with col2:

    delay_seconds = st.number_input(

        "Delay between emails",

        min_value=10,

        max_value=3600,

        value=30,

        step=10
    )


stop_after_current = st.checkbox(

    "🛑 Stop after the current email",

    value=False
)


st.caption(
    "For testing, keep the limit at 1. "
    "Increase gradually only after confirming "
    "the workflow is working correctly."
)


# =========================================================
# SEND EMAIL
# =========================================================

def send_email(

    credentials,

    to_email,

    subject,

    body,

    resume_bytes,

    resume_filename

):

    service = build(

        "gmail",

        "v1",

        credentials=credentials,

        cache_discovery=False
    )


    message = MIMEMultipart()


    message["To"] = to_email

    message["Subject"] = subject


    # Body
    message.attach(

        MIMEText(

            body,

            "plain",

            "utf-8"
        )
    )


    # Resume
    if resume_bytes:

        attachment = MIMEApplication(

            resume_bytes,

            _subtype="pdf"
        )


        attachment.add_header(

            "Content-Disposition",

            "attachment",

            filename=resume_filename
        )


        message.attach(
            attachment
        )


    # Encode
    raw_message = (

        base64.urlsafe_b64encode(

            message.as_bytes()

        ).decode()
    )


    # Gmail send
    result = (

        service.users()

        .messages()

        .send(

            userId="me",

            body={
                "raw": raw_message
            }

        )

        .execute()
    )


    return result.get(
        "id"
    )


# =========================================================
# START OUTREACH
# =========================================================

st.divider()

st.subheader(
    "6️⃣ Start Outreach"
)


if df is None:

    st.warning(
        "Upload recruiter Excel first."
    )


elif resume_file is None:

    st.warning(
        "Upload PDF resume first."
    )


elif not has_refresh_token:

    st.warning(
        "Please login again."
    )


else:

    tracker = load_tracker()


    pending_contacts = tracker[

        tracker["Status"]
        == "PENDING"

    ].copy()


    st.info(

        f"Pending contacts available: "
        f"{len(pending_contacts)}"
    )


    if pending_contacts.empty:

        st.success(
            "🎉 No pending contacts remaining."
        )


    else:

        if st.button(

            "🚀 Start Outreach",

            type="primary",

            disabled=(
                st.session_state.outreach_running
            )

        ):

            st.session_state.outreach_running = True


            progress = st.progress(
                0
            )


            status_box = st.empty()


            sent_count = 0

            failed_count = 0


            rows_to_process = (

                pending_contacts.head(

                    int(daily_limit)

                )
            )


            total = len(
                rows_to_process
            )


            # =================================================
            # SEND LOOP
            # =================================================

            for _, row in rows_to_process.iterrows():

                to_email = str(

                    row.get(
                        "Email",
                        ""
                    )

                ).strip()


                try:

                    # -----------------------------------------
                    # Contact data
                    # -----------------------------------------

                    person_name = str(

                        row.get(
                            "Person Name",
                            ""
                        )

                    ).strip()


                    company = str(

                        row.get(
                            "Company",
                            ""
                        )

                    ).strip()


                    # -----------------------------------------
                    # Validate
                    # -----------------------------------------

                    if (

                        not to_email

                        or "@"
                        not in to_email

                    ):

                        raise Exception(
                            "Invalid email address."
                        )


                    # -----------------------------------------
                    # Session duplicate protection
                    # -----------------------------------------

                    if (

                        to_email

                        in
                        st.session_state.sent_this_session

                    ):

                        status_box.warning(

                            f"Skipped duplicate: "
                            f"{to_email}"
                        )

                        continue


                    # -----------------------------------------
                    # Personalize
                    # -----------------------------------------

                    personalized_body = (

                        email_template

                        .replace(

                            "{person_name}",

                            person_name

                        )

                        .replace(

                            "{company}",

                            company

                        )
                    )


                    # -----------------------------------------
                    # Credentials
                    # -----------------------------------------

                    credentials = (
                        build_google_credentials()
                    )


                    if not credentials:

                        raise Exception(
                            "Gmail authorization unavailable."
                        )


                    # -----------------------------------------
                    # Send
                    # -----------------------------------------

                    status_box.info(

                        f"📤 Sending to "
                        f"{to_email}..."
                    )


                    message_id = send_email(

                        credentials=credentials,

                        to_email=to_email,

                        subject=subject,

                        body=personalized_body,

                        resume_bytes=resume_bytes,

                        resume_filename=(
                            resume_file.name
                        )
                    )


                    # -----------------------------------------
                    # Tracker
                    # -----------------------------------------

                    tracker_updated = (

                        update_tracker_success(

                            email=to_email,

                            message_id=message_id,

                            subject=subject

                        )
                    )


                    if not tracker_updated:

                        raise Exception(
                            "Email was sent but "
                            "tracker update failed."
                        )


                    # -----------------------------------------
                    # Success
                    # -----------------------------------------

                    sent_count += 1


                    st.session_state.sent_this_session.add(
                        to_email
                    )


                    status_box.success(

                        f"✅ Sent to "
                        f"{to_email}"
                    )


                    st.write(

                        f"Message ID: "
                        f"{message_id}"
                    )


                    # -----------------------------------------
                    # Progress
                    # -----------------------------------------

                    progress.progress(

                        min(

                            (

                                sent_count
                                + failed_count

                            ) / total,

                            1.0
                        )
                    )


                    # -----------------------------------------
                    # Stop after current
                    # -----------------------------------------

                    if stop_after_current:

                        status_box.info(

                            "🛑 Stopped after "
                            "the current email."
                        )

                        break


                    # -----------------------------------------
                    # Delay
                    # -----------------------------------------

                    if (

                        sent_count
                        + failed_count

                        < total

                    ):

                        status_box.info(

                            f"⏳ Waiting "
                            f"{int(delay_seconds)} "
                            f"seconds before next email..."
                        )


                        time.sleep(

                            int(
                                delay_seconds
                            )
                        )


                except Exception as e:

                    failed_count += 1


                    try:

                        update_tracker_failed(

                            email=to_email,

                            error=str(e),

                            subject=subject

                        )

                    except Exception:

                        pass


                    status_box.error(

                        f"❌ Failed: "
                        f"{to_email} — {e}"
                    )


                    progress.progress(

                        min(

                            (

                                sent_count
                                + failed_count

                            ) / total,

                            1.0
                        )
                    )


            # =================================================
            # FINISH
            # =================================================

            st.session_state.outreach_running = False


            st.success(

                "Outreach finished. "

                f"Successfully sent: "
                f"{sent_count}"
            )


            if failed_count:

                st.warning(

                    f"Failed: "
                    f"{failed_count}"
                )


# =========================================================
# PERMANENT TRACKER
# =========================================================

st.divider()

st.subheader(
    "📊 Permanent Outreach Tracker"
)


tracker = load_tracker()


if not tracker.empty:

    sent_total = int(

        (
            tracker["Status"]
            == "SENT"
        ).sum()
    )


    pending_total = int(

        (
            tracker["Status"]
            == "PENDING"
        ).sum()
    )


    failed_total = int(

        (
            tracker["Status"]
            == "FAILED"
        ).sum()
    )


    c1, c2, c3 = st.columns(3)


    with c1:

        st.metric(
            "✅ Sent",
            sent_total
        )


    with c2:

        st.metric(
            "⏳ Pending",
            pending_total
        )


    with c3:

        st.metric(
            "❌ Failed",
            failed_total
        )


    st.dataframe(

        tracker.head(100),

        use_container_width=True
    )


    # -----------------------------------------------------
    # Tracker download
    # -----------------------------------------------------

    tracker_csv = tracker.to_csv(

        index=False,

        encoding="utf-8-sig"
    )


    st.download_button(

        "⬇️ Download Tracker Backup",

        data=tracker_csv,

        file_name="outreach_tracker.csv",

        mime="text/csv"
    )


else:

    st.info(
        "Tracker will appear after Excel upload."
    )
