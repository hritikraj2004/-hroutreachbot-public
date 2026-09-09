import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRACKER_FILE = os.path.join(BASE_DIR, "outreach_tracker.csv")

EMAIL_TO_MARK = "suraj.shylaja@g10x.com"
MESSAGE_ID = "1a086006f5a40237"

print("===================================")
print("PUBLIC TRACKER FIX")
print("===================================")
print()
print("Tracker file:")
print(TRACKER_FILE)
print()


if not os.path.exists(TRACKER_FILE):

    print("❌ ERROR")
    print("outreach_tracker.csv nahi mila.")
    print()
    print("Pehle public app mein Excel upload karo.")
    input("\nPress Enter to exit...")
    raise SystemExit


# Read tracker as text
df = pd.read_csv(
    TRACKER_FILE,
    dtype=str,
    keep_default_na=False
)


print(
    f"Tracker loaded: {len(df)} rows"
)
print()


# Clean email column
df["Email"] = (
    df["Email"]
    .fillna("")
    .astype(str)
    .str.strip()
)


# Find Suraj
mask = (
    df["Email"].str.lower()
    == EMAIL_TO_MARK.lower()
)


print(
    f"Searching for: {EMAIL_TO_MARK}"
)
print()


if not mask.any():

    print("❌ SURaj email tracker mein nahi mila.")
    print()

    print("First 10 emails:")
    print(
        df["Email"].head(10).to_string(
            index=False
        )
    )

    input("\nPress Enter to exit...")
    raise SystemExit


# Show current status
print("FOUND CONTACT:")
print(
    df.loc[
        mask,
        [
            "Company",
            "Email",
            "Person Name",
            "Status"
        ]
    ].to_string(index=False)
)

print()


# Mark SENT
df.loc[
    mask,
    "Status"
] = "SENT"


# Add message ID
df.loc[
    mask,
    "Message ID"
] = MESSAGE_ID


# Clear error
df.loc[
    mask,
    "Error"
] = ""


# Keep Sent At blank.
# We don't guess the exact timestamp.


# Save exact public tracker
df.to_csv(
    TRACKER_FILE,
    index=False,
    encoding="utf-8-sig"
)


# =========================================================
# VERIFY AFTER SAVING
# =========================================================

print("Saving tracker...")
print()


check_df = pd.read_csv(
    TRACKER_FILE,
    dtype=str,
    keep_default_na=False
)


check_df["Email"] = (
    check_df["Email"]
    .astype(str)
    .str.strip()
)


check_mask = (
    check_df["Email"].str.lower()
    == EMAIL_TO_MARK.lower()
)


print("AFTER SAVE:")
print(
    check_df.loc[
        check_mask,
        [
            "Company",
            "Email",
            "Person Name",
            "Status",
            "Sent At",
            "Message ID",
            "Error"
        ]
    ].to_string(index=False)
)

print()


current_status = (
    check_df.loc[
        check_mask,
        "Status"
    ].iloc[0]
)


if current_status == "SENT":

    print("===================================")
    print("✅ SUCCESS")
    print("===================================")
    print()
    print(
        "Suraj ko PUBLIC tracker mein SENT mark kar diya."
    )
    print()
    print(
        "Personal bot ko touch nahi kiya."
    )

else:

    print("===================================")
    print("❌ SAVE VERIFICATION FAILED")
    print("===================================")


print()
input("Press Enter to exit...")