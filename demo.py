import streamlit as st
import pandas as pd
import altair as alt
from trust_layer.record import PatientRecord
from trust_layer.validators import (
    validate_completeness, validate_temporal,
    validate_identity_consistency, validate_provenance,
    CrossRecordValidator
)
from trust_layer.scoring import compute_trust_score
from trust_layer.router import route_decision_hard
from trust_layer.audit import log_decision

st.set_page_config(page_title="Identity Trust Assessment", layout="wide")
st.title("Identity Trust Assessment")
st.caption("Five-dimension trust layer for patient identity resolution in HIEs")

COLOR_OPTIONS = {
    "Blue": "#1E90FF", "Pink": "#FF69B4", "Red": "#FF0000",
    "Orange": "#FFA500", "Purple": "#800080", "Green": "#32CD32",
    "Teal": "#008080", "Magenta": "#FF00FF", "Indigo": "#4B0082",
    "Black": "#000000", "Gray": "#808080", "Gold": "#FFD700",
}

def render_dimension_bar(label, score, color):
    pct = int(score * 100)
    html = f"""
    <div style="margin-bottom: 12px;">
        <div style="display: flex; justify-content: space-between; font-family: 'Helvetica', sans-serif; font-size: 14px; margin-bottom: 4px;">
            <span style="font-weight: 600; color: #374151;">{label}</span>
            <span style="color: #6B7280;">{score:.2f}</span>
        </div>
        <div style="background-color: #E5E7EB; border-radius: 6px; height: 12px; width: 100%; overflow: hidden;">
            <div style="background-color: {color}; width: {pct}%; height: 100%; border-radius: 6px;"></div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# ============================================================
# NORMALIZATION HELPERS
# ============================================================
def normalize_text(value):
    if pd.isna(value) or value is None:
        return ""
    return str(value).strip().title()

def normalize_id(value):
    if pd.isna(value) or value is None or str(value).strip() == "":
        return None
    return str(value).strip().replace(" ", "").replace("-", "")

def normalize_date(value):
    """Convert common date formats to ISO 8601 (YYYY-MM-DD)."""
    if pd.isna(value) or value is None:
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "nat"):
        return ""
    if len(s) == 10 and s[4] == "-":
        return s
    try:
        parsed = pd.to_datetime(s, dayfirst=True, errors="coerce")
        if pd.isna(parsed):
            return s
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return s

# ============================================================
# TEMPLATE-BASED Q&A (Read-Only Explainer)
# ============================================================
def answer_question(question, results_df):
    q = question.lower().strip()
    if not q:
        return "Please type a question."

    if "help" in q or "what can" in q or "example" in q:
        return (
            "**You can ask things like:**\n"
            "- *Why was P00320 flagged?* (search by record ID)\n"
            "- *Find Noura Al Aktoum* (search by name)\n"
            "- *How many records from SSMC were flagged?* (facility counts)\n"
            "- *What is an identifier collision?* (issue definitions)\n\n"
            "**Important:** This assistant only explains decisions already made by the rule-based validators. "
            "It does not resolve, merge, or correct any records."
        )

    issue_defs = {
        "identifier collision": "An identifier collision occurs when two different patients are assigned the same Emirates ID. This is a critical safety risk because one patient's medical history can be attached to another patient's record. The record is quarantined for manual review.",
        "potential collision": "A potential collision occurs when the name and date of birth match an existing patient, but the identifier differs. This could indicate a duplicate registration or a name-based spoof attempt.",
        "missing demographics": "The record is missing required identity fields such as Emirates ID, given name, family name, or date of birth. Without these, the record cannot be reliably linked.",
        "untrusted facility": "The source facility is not in the high-trust tier. Records from untrusted sources require manual verification before linking.",
        "temporal validity": "The date of birth is either in an unrecognized format or outside a plausible range. Valid dates must be normalizable to the ISO format YYYY-MM-DD.",
        "malformed identifier": "The Emirates ID format does not match the UAE standard (784-YYYY-XXXXXXX-C).",
    }
    for key, val in issue_defs.items():
        if key in q:
            return val

    if "how many" in q:
        for fac in results_df["source_facility"].unique():
            if fac and str(fac).lower() in q:
                subset = results_df[results_df["source_facility"] == fac]
                flagged = subset[subset["decision"].isin(["LINK_WITH_FLAG", "QUARANTINE"])]
                return f"Out of **{len(subset)}** records from **{fac}**, **{len(flagged)}** were flagged or quarantined."

    for cid in results_df["canonical_id"].astype(str):
        if cid.lower() in q:
            row = results_df[results_df["canonical_id"].astype(str) == cid].iloc[0]
            return (
                f"**{row['canonical_id']}** ({row['given_name']} {row['family_name']})\n\n"
                f"- **Decision:** {row['decision']}\n"
                f"- **Trust Score:** {row['trust_score']}\n"
                f"- **Primary Issue:** {row['primary_issue']}\n"
                f"- **Forensic Detail:** {row['explanation']}"
            )

    for _, row in results_df.iterrows():
        name = f"{row['given_name']} {row['family_name']}".lower()
        if len(name) >= 5 and name in q:
            return (
                f"**{row['canonical_id']}** ({row['given_name']} {row['family_name']})\n\n"
                f"- **Decision:** {row['decision']}\n"
                f"- **Trust Score:** {row['trust_score']}\n"
                f"- **Primary Issue:** {row['primary_issue']}\n"
                f"- **Forensic Detail:** {row['explanation']}"
            )

    return "I couldn't find a match. Type **help** to see example questions."

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.subheader("Configuration")
    selected_color_name = st.selectbox("🎨 Bar Color", list(COLOR_OPTIONS.keys()))
    selected_color = COLOR_OPTIONS[selected_color_name]

    st.warning("⚠️ **Privacy Notice:** This demo uses synthetic data only. Do not upload real patient health information (PHI).")

    sample_data = pd.DataFrame({
        "emirates_id": ["784-1985-1234567-1", "", "784-1985-1234567-1"],
        "given_name": ["Ahmed", "Raj", "Fatima"],
        "family_name": ["Al-Mansoori", "Kumar", "Al-Zahra"],
        "date_of_birth": ["1985-03-15", "1990-07-22", "1992-01-01"],
        "nationality": ["UAE", "India", "UAE"],
        "source_facility": ["Cleveland Clinic Abu Dhabi", "Al Noor Hospital", "SSMC"],
        "registration_date": ["2024-01-10", "2024-02-15", "2024-03-20"],
        "canonical_id": ["P001", "P002", "P003"],
    })
    st.download_button(
        label="📄 Download Sample CSV",
        data=sample_data.to_csv(index=False).encode("utf-8"),
        file_name="sample_batch.csv", mime="text/csv", use_container_width=True,
    )
    uploaded_file = st.file_uploader("Upload patient records (CSV)", type=["csv"])

if uploaded_file is None:
    st.info("👈 Please upload a CSV file in the sidebar to begin the assessment.")
    st.stop()

# ============================================================
# SMART COLUMN MAPPING
# ============================================================
df = pd.read_csv(uploaded_file)
df.columns = [str(c).strip() for c in df.columns]

column_synonyms = {
    "emirates_id": ["emirates_id", "Emirates ID", "ID", "Identifier", "emirates id", "EmiratesID", "National ID"],
    "given_name": ["given_name", "First Name", "FirstName", "Given Name", "given name", "GivenName"],
    "family_name": ["family_name", "Last Name", "LastName", "Surname", "Family Name", "family name", "FamilyName"],
    "date_of_birth": ["date_of_birth", "DOB", "Date of Birth", "BirthDate", "Birth Date", "date of birth", "DOB "],
    "nationality": ["nationality", "Nationality", "Country"],
    "source_facility": ["source_facility", "Facility", "Hospital", "Source Facility", "source facility"],
    "registration_date": ["registration_date", "Registration Date", "Reg Date", "registration date"],
    "canonical_id": ["canonical_id", "Canonical ID", "Patient ID", "MRN", "canonical id", "PatientID"],
}
for target, options in column_synonyms.items():
    for opt in options:
        if opt in df.columns:
            df = df.rename(columns={opt: target})
            break

required_cols = ["given_name", "family_name", "date_of_birth"]
missing_cols = [c for c in required_cols if c not in df.columns]
if missing_cols:
    st.error(f"Missing required columns in CSV. Could not find columns for: {', '.join(missing_cols)}")
    st.info(f"Columns currently in your file: {', '.join(df.columns)}")
    st.stop()

# ============================================================
# PRE-CLEANING
# ============================================================
df["given_name"] = df["given_name"].apply(normalize_text)
df["family_name"] = df["family_name"].apply(normalize_text)
df["date_of_birth"] = df["date_of_birth"].apply(normalize_date)
df["source_facility"] = df["source_facility"].apply(normalize_text)
df["nationality"] = df["nationality"].apply(normalize_text)
if "emirates_id" in df.columns:
    df["emirates_id"] = df["emirates_id"].apply(normalize_id)

# ============================================================
# DATA PROFILING
# ============================================================
total_raw = len(df)
missing_ids_raw = df["emirates_id"].isna().sum() if "emirates_id" in df.columns else total_raw
missing_dob_raw = (df["date_of_birth"] == "").sum()
missing_name_raw = ((df["given_name"] == "") | (df["family_name"] == "")).sum()
duplicate_ids_raw = df["emirates_id"].duplicated().sum() if "emirates_id" in df.columns else 0

# ============================================================
# SCORING
# ============================================================
cv = CrossRecordValidator()
results = []

for index, row in df.iterrows():
    rec = PatientRecord(
        emirates_id=row.get("emirates_id") if pd.notna(row.get("emirates_id")) else None,
        given_name=row.get("given_name", ""),
        family_name=row.get("family_name", ""),
        date_of_birth=row.get("date_of_birth", ""),
        nationality=row.get("nationality", ""),
        source_facility=row.get("source_facility", ""),
        registration_date=row.get("registration_date", ""),
        canonical_id=str(row.get("canonical_id", f"ROW_{index}")),
    )
    dims = {
        "completeness": validate_completeness(rec),
        "temporal": validate_temporal(rec),
        "identity": validate_identity_consistency(rec),
        "provenance": validate_provenance(rec),
        "cross_record": cv.validate(rec),
    }
    score = compute_trust_score(**dims)
    decision = route_decision_hard(score, dims["cross_record"])
    log_decision(rec, dims, score, decision)

    explanation = "Record is clean and trusted."
    primary_issue = "None"
    if decision in ("LINK_WITH_FLAG", "QUARANTINE"):
        weakest_dim = min(dims, key=dims.get)
        weakest_val = dims[weakest_dim]
        if weakest_dim == "cross_record":
            if weakest_val == 0.0:
                colliding_id = "Unknown"
                if rec.emirates_id and rec.emirates_id in cv.identifier_index:
                    for owner_id in cv.identifier_index[rec.emirates_id]:
                        if owner_id != rec.canonical_id:
                            colliding_id = owner_id
                            break
                explanation = (f"FORENSIC COLLISION: Identifier '{rec.emirates_id}' is already registered "
                               f"to patient {colliding_id}. This record claims to be {rec.given_name} {rec.family_name} "
                               f"(DOB: {rec.date_of_birth}), which is a different identity.")
                primary_issue = "Identifier Collision"
            elif weakest_val == 0.5:
                explanation = (f"POTENTIAL COLLISION: Name ({rec.given_name} {rec.family_name}) and "
                               f"DOB ({rec.date_of_birth}) match an existing patient, but the identifier differs.")
                primary_issue = "Potential Name/DOB Collision"
        elif weakest_dim == "completeness":
            missing_fields = [f for f, v in [("Emirates ID", rec.emirates_id), ("Given Name", rec.given_name), ("Family Name", rec.family_name), ("DOB", rec.date_of_birth)] if not v]
            explanation = f"INCOMPLETE DATA: Missing required fields: {', '.join(missing_fields)}."
            primary_issue = "Missing Demographics"
        elif weakest_dim == "provenance":
            explanation = f"LOW-TRUST SOURCE: Facility '{rec.source_facility}' is not in the high-trust tier."
            primary_issue = "Untrusted Facility"
        elif weakest_dim == "temporal":
            explanation = f"TEMPORAL ERROR: The date of birth '{rec.date_of_birth}' could not be normalized to a valid ISO date (YYYY-MM-DD)."
            primary_issue = "Temporal Validity Error"
        elif weakest_dim == "identity":
            explanation = f"IDENTITY INCONSISTENCY: The Emirates ID '{rec.emirates_id}' format is malformed."
            primary_issue = "Malformed Identifier"
        else:
            explanation = f"Flagged due to low score in {weakest_dim}."
            primary_issue = f"Low {weakest_dim} Score"

    results.append({
        "canonical_id": rec.canonical_id, "given_name": rec.given_name,
        "family_name": rec.family_name, "source_facility": rec.source_facility,
        "trust_score": round(score, 3), "decision": decision,
        "explanation": explanation, "primary_issue": primary_issue,
        "dim_completeness": dims["completeness"], "dim_temporal": dims["temporal"],
        "dim_identity": dims["identity"], "dim_provenance": dims["provenance"],
        "dim_cross_record": dims["cross_record"],
    })
    cv.add_record(rec)

results_df = pd.DataFrame(results)

# ============================================================
# LAYOUT: 5 TABS
# ============================================================
tab0, tab1, tab2, tab3, tab4 = st.tabs([
    "🧹 Source Data Quality", "📊 Executive Dashboard",
    "🚩 Flagged Records", "💬 Ask About a Record", "📄 Batch Results"
])

with tab0:
    st.subheader("🧹 Source Data Quality Profile")
    st.markdown("Before assessing trust, it's important to understand the quality of the incoming file.")
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Total Records in File", total_raw)
    col_b.metric("Missing/Blank Emirates ID", missing_ids_raw)
    col_c.metric("Missing Date of Birth", missing_dob_raw)
    col_d.metric("Duplicate Emirates IDs in File", duplicate_ids_raw)
    st.divider()
    st.subheader("Top 5 Source Facilities by Volume")
    if "source_facility" in df.columns:
        fac_vol = df["source_facility"].value_counts().head(5).reset_index()
        fac_vol.columns = ["Facility", "Record Count"]
        chart_vol = alt.Chart(fac_vol).mark_bar(color="#6366F1").encode(
            x=alt.X("Record Count:Q", title="Number of Records"),
            y=alt.Y("Facility:N", sort="-x", title=""),
            tooltip=["Facility", "Record Count"],
        ).properties(height=250)
        st.altair_chart(chart_vol, use_container_width=True)
    st.info("💡 **Recommendation:** If missing IDs or duplicate IDs are high, the source hospitals need to improve their registration data entry.")

with tab1:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Records", len(results_df))
    col2.metric("✅ Auto-Linked", len(results_df[results_df["decision"] == "AUTO_LINK"]))
    col3.metric("⚠️ Flagged", len(results_df[results_df["decision"] == "LINK_WITH_FLAG"]))
    col4.metric("🚨 Quarantined", len(results_df[results_df["decision"] == "QUARANTINE"]))
    st.divider()
    st.subheader("Decision Breakdown")
    decision_counts = results_df["decision"].value_counts().reset_index()
    decision_counts.columns = ["Decision", "Count"]
    chart1 = alt.Chart(decision_counts).mark_bar(color="#4A6FA5").encode(
        x=alt.X("Count:Q", title="Number of Records"),
        y=alt.Y("Decision:N", sort="-x", title=""), tooltip=["Decision", "Count"],
    ).properties(height=250)
    st.altair_chart(chart1, use_container_width=True)
    st.subheader("Facility Risk Profile")
    flagged_df = results_df[results_df["decision"].isin(["LINK_WITH_FLAG", "QUARANTINE"])]
    if not flagged_df.empty:
        fac_counts = flagged_df["source_facility"].value_counts().reset_index()
        fac_counts.columns = ["Facility", "Flagged Count"]
        chart2 = alt.Chart(fac_counts).mark_bar(color="#C62828").encode(
            x=alt.X("Flagged Count:Q", title="Number of Flagged Records"),
            y=alt.Y("Facility:N", sort="-x", title=""), tooltip=["Facility", "Flagged Count"],
        ).properties(height=300)
        st.altair_chart(chart2, use_container_width=True)
    else:
        st.info("No records were flagged in this batch.")
    st.subheader("Dimension Scoring Averages")
    dim_means = results_df[["dim_completeness", "dim_temporal", "dim_identity", "dim_provenance", "dim_cross_record"]].mean().reset_index()
    dim_means.columns = ["Dimension", "Average Score"]
    dim_means["Dimension"] = ["Completeness", "Temporal", "Identity", "Provenance", "Cross-Record"]
    chart3 = alt.Chart(dim_means).mark_bar(color="#2E7D32").encode(
        x=alt.X("Average Score:Q", scale=alt.Scale(domain=[0, 1])),
        y=alt.Y("Dimension:N", sort="-x", title=""), tooltip=["Dimension", "Average Score"],
    ).properties(height=250)
    st.altair_chart(chart3, use_container_width=True)

with tab2:
    flagged = results_df[results_df["decision"].isin(["LINK_WITH_FLAG", "QUARANTINE"])]
    if not flagged.empty:
        st.subheader("🚩 Flagged Records for Manual Review")
        st.warning(f"{len(flagged)} record(s) require manual review.")
        for _, row in flagged.iterrows():
            with st.expander(f"{row['canonical_id']} - {row['given_name']} {row['family_name']} ({row['decision']})"):
                st.write(f"**Trust Score:** {row['trust_score']}")
                st.write(f"**Primary Issue:** {row['primary_issue']}")
                st.info(f"**Forensic Detail:** {row['explanation']}")
                st.write("**Dimension Scores:**")
                render_dimension_bar("Completeness", row["dim_completeness"], selected_color)
                render_dimension_bar("Temporal", row["dim_temporal"], selected_color)
                render_dimension_bar("Identity", row["dim_identity"], selected_color)
                render_dimension_bar("Provenance", row["dim_provenance"], selected_color)
                render_dimension_bar("Cross-Record", row["dim_cross_record"], selected_color)
        st.write("")
        st.download_button(
            label="📥 Download Flagged Records (CSV)",
            data=flagged.to_csv(index=False).encode("utf-8"),
            file_name="flagged_identity_records.csv", mime="text/csv",
        )
    else:
        st.success("All records processed cleanly. No flags raised.")

with tab3:
    st.subheader("💬 Ask About a Record")
    st.markdown(
        "Type a question about any record. This assistant **only explains decisions already made** "
        "by the rule-based validators. It does not resolve, merge, or correct any records."
    )
    question = st.text_input("Your question", placeholder="e.g., Why was P00320 flagged?")
    if st.button("Ask"):
        answer = answer_question(question, results_df)
        st.markdown(answer)

with tab4:
    st.subheader("Batch Results")
    st.markdown(results_df[["canonical_id", "given_name", "family_name", "trust_score", "decision", "primary_issue"]].to_markdown(index=False))
    st.download_button(
        label="📥 Download Full Scored Batch (CSV)",
        data=results_df.to_csv(index=False).encode("utf-8"),
        file_name="full_scored_batch.csv", mime="text/csv",
    )
