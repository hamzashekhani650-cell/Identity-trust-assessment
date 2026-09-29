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

PREFIXES = ["mr.", "mrs.", "ms.", "dr.", "mr ", "mrs ", "ms ", "dr "]

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
# ENHANCED NORMALIZATION
# ============================================================
def normalize_text(value):
    if pd.isna(value) or value is None:
        return ""
    s = str(value).strip()
    # Strip common honorifics
    lower = s.lower()
    for prefix in PREFIXES:
        if lower.startswith(prefix):
            s = s[len(prefix):].strip()
            break
    # Collapse internal whitespace
    s = " ".join(s.split())
    return s.title()

def normalize_id(value):
    if pd.isna(value) or value is None or str(value).strip() == "":
        return None
    # Keep only digits — strips hyphens, spaces, dots, etc.
    digits_only = "".join(c for c in str(value) if c.isdigit())
    return digits_only if digits_only else None

def normalize_date(value):
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
# PRE-CLEANING WITH CHANGE TRACKING
# ============================================================
df["_orig_given"] = df["given_name"].astype(str)
df["_orig_family"] = df["family_name"].astype(str)
df["_orig_dob"] = df["date_of_birth"].astype(str)
df["_orig_id"] = df["emirates_id"].astype(str) if "emirates_id" in df.columns else ""

df["given_name"] = df["given_name"].apply(normalize_text)
df["family_name"] = df["family_name"].apply(normalize_text)
df["date_of_birth"] = df["date_of_birth"].apply(normalize_date)
df["source_facility"] = df["source_facility"].apply(normalize_text)
df["nationality"] = df["nationality"].apply(normalize_text)
if "emirates_id" in df.columns:
    df["emirates_id"] = df["emirates_id"].apply(normalize_id)

df["_changed_name"] = (df["_orig_given"] != df["given_name"].astype(str)) | (df["_orig_family"] != df["family_name"].astype(str))
df["_changed_dob"] = df["_orig_dob"] != df["date_of_birth"].astype(str)
df["_changed_id"] = (df["_orig_id"] != df["emirates_id"].astype(str)) & (df["_orig_id"].str.strip() != "")

total_normalized = int((df["_changed_name"] | df["_changed_dob"] | df["_changed_id"]).sum())

# ============================================================
# DATA PROFILING
# ============================================================
total_raw = len(df)
missing_ids_raw = df["emirates_id"].isna().sum() if "emirates_id" in df.columns else total_raw
missing_dob_raw = (df["date_of_birth"] == "").sum()
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
# LAYOUT: 4 TABS (main simple tabs + one advanced tucked away)
# ============================================================
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Executive Dashboard",
    "🚩 Flagged Records",
    "📄 Batch Results",
    "🔧 Data Normalization Log",
])

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
    st.markdown("Which facilities produced the most flagged records?")
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
    flagged = results_df[results_df["decision"].isin(["LINK_WITH_FLAG", "QUARANTINE"])].copy()

    if flagged.empty:
        st.success("All records processed cleanly. No flags raised.")
    else:
        # Sort: QUARANTINE first (highest risk), then by trust score ascending
        priority = {"QUARANTINE": 0, "LINK_WITH_FLAG": 1}
        flagged["_priority"] = flagged["decision"].map(priority)
        flagged = flagged.sort_values(["_priority", "trust_score"]).drop(columns="_priority")

        st.subheader("🚩 Flagged Records for Manual Review")
        st.warning(f"{len(flagged)} record(s) require manual review.")

        # ============================================================
        # FILTERS
        # ============================================================
        fc1, fc2, fc3 = st.columns([2, 2, 1])
        with fc1:
            issue_options = sorted(flagged["primary_issue"].unique().tolist())
            selected_issues = st.multiselect("Filter by issue type", options=issue_options, default=issue_options)
        with fc2:
            decision_options = sorted(flagged["decision"].unique().tolist())
            selected_decisions = st.multiselect("Filter by decision", options=decision_options, default=decision_options)
        with fc3:
            st.write("")
            st.write("")

        filtered = flagged[
            (flagged["primary_issue"].isin(selected_issues)) &
            (flagged["decision"].isin(selected_decisions))
        ]

        st.caption(f"Showing {len(filtered)} of {len(flagged)} flagged records.")

        # ============================================================
        # BULK ACTION: Copy all IDs
        # ============================================================
        all_ids = "\n".join(filtered["canonical_id"].astype(str).tolist())
        with st.expander("📋 Bulk Actions"):
            st.markdown("**Copy all filtered record IDs:**")
            st.code(all_ids, language=None)

        st.divider()

        # ============================================================
        # RECORD CARDS with copy buttons
        # ============================================================
        for _, row in filtered.iterrows():
            with st.expander(f"{row['canonical_id']} — {row['given_name']} {row['family_name']} ({row['decision']})"):
                # Copy button via st.code (has built-in copy icon)
                st.markdown("**Record ID (click the copy icon):**")
                st.code(row["canonical_id"], language=None)

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
            label="📥 Download Filtered Flagged Records (CSV)",
            data=filtered.to_csv(index=False).encode("utf-8"),
            file_name="flagged_identity_records.csv", mime="text/csv",
        )

with tab3:
    st.subheader("Batch Results")
    st.markdown(results_df[["canonical_id", "given_name", "family_name", "trust_score", "decision", "primary_issue"]].to_markdown(index=False))
    st.download_button(
        label="📥 Download Full Scored Batch (CSV)",
        data=results_df.to_csv(index=False).encode("utf-8"),
        file_name="full_scored_batch.csv", mime="text/csv",
    )

with tab4:
    st.subheader("🔧 Data Normalization Log")
    st.markdown(
        "This tab shows exactly what was cleaned or reformatted before scoring. "
        "Formatting differences (whitespace, casing, date format, honorifics) do **not** "
        "trigger flags — only real trust failures do."
    )

    st.metric("Records Normalized", total_normalized, help="Records where at least one field was reformatted.")

    st.divider()

    if total_normalized == 0:
        st.info("No formatting differences were detected in this batch.")
    else:
        st.markdown("### Changes Applied")
        change_rows = []
        for index, row in df.iterrows():
            changes = []
            if row["_changed_name"]:
                changes.append(f"Name: '{row['_orig_given']} {row['_orig_family']}' → '{row['given_name']} {row['family_name']}'")
            if row["_changed_dob"]:
                changes.append(f"DOB: '{row['_orig_dob']}' → '{row['date_of_birth']}'")
            if row["_changed_id"]:
                changes.append(f"ID: '{row['_orig_id']}' → '{row['emirates_id']}'")
            if changes:
                change_rows.append({
                    "canonical_id": row.get("canonical_id", f"ROW_{index}"),
                    "Changes": " | ".join(changes),
                })

        change_df = pd.DataFrame(change_rows)
        st.dataframe(change_df, use_container_width=True)

        st.download_button(
            label="📥 Download Normalization Log (CSV)",
            data=change_df.to_csv(index=False).encode("utf-8"),
            file_name="normalization_log.csv", mime="text/csv",
        )

    st.divider()
    st.subheader("Source Data Quality Snapshot")
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total Records in File", total_raw)
    col_b.metric("Missing Emirates ID", missing_ids_raw)
    col_c.metric("Duplicate Emirates IDs", duplicate_ids_raw)
    st.info(
        "💡 **Recommendation:** High missing-ID or duplicate-ID counts indicate data entry "
        "problems at the source. Fixing this at registration prevents downstream flags."
    )
