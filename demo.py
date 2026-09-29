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

try:
    from batch.report import generate_report
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

st.set_page_config(page_title="Identity Trust Assessment", layout="wide")
st.title("Identity Trust Assessment")
st.caption("Five-dimension trust layer for patient identity resolution in HIEs")

# ============================================================
# COLOR THEMES
# ============================================================
theme_colors = {
    "Default": {
        "high": "#10B981",      # Green
        "medium": "#F59E0B",    # Orange
        "low": "#8B5CF6",       # Purple
        "critical": "#EF4444"   # Red
    },
    "Pink & Red": {
        "high": "#EC4899",      # Pink
        "medium": "#F43F5E",    # Rose
        "low": "#E11D48",       # Deep Pink
        "critical": "#881337"   # Dark Red
    },
    "Purple & Orange": {
        "high": "#A855F7",      # Purple
        "medium": "#F97316",    # Orange
        "low": "#8B5CF6",       # Violet
        "critical": "#EF4444"   # Red
    }
}

# ============================================================
# CUSTOM PROGRESS BAR FUNCTION
# ============================================================
def render_dimension_bar(label, score, palette):
    if score >= 0.8:
        color = palette["high"]
    elif score >= 0.6:
        color = palette["medium"]
    elif score >= 0.4:
        color = palette["low"]
    else:
        color = palette["critical"]
        
    pct = int(score * 100)
    html = f"""
    <div style="margin-bottom: 12px;">
        <div style="display: flex; justify-content: space-between; font-family: 'Helvetica', sans-serif; font-size: 14px; margin-bottom: 4px;">
            <span style="font-weight: 600; color: #374151;">{label}</span>
            <span style="color: #6B7280;">{score:.2f}</span>
        </div>
        <div style="background-color: #E5E7EB; border-radius: 6px; height: 12px; width: 100%; overflow: hidden;">
            <div style="background-color: {color}; width: {pct}%; height: 100%; border-radius: 6px; transition: width 0.5s ease-in-out;"></div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# ============================================================
# SIDEBAR: INPUTS AND WARNINGS
# ============================================================
with st.sidebar:
    st.subheader("Configuration")
    
    # THE NEW COLOR PICKER DROPDOWN
    selected_theme = st.selectbox("🎨 Color Theme", list(theme_colors.keys()))
    palette = theme_colors[selected_theme]
    
    st.warning("⚠️ **Privacy Notice:** This demo uses synthetic data only. Do not upload real patient health information (PHI).")
    
    sample_data = pd.DataFrame({
        "emirates_id": ["784-1985-1234567-1", "", "784-1985-1234567-1"],
        "given_name": ["Ahmed", "Raj", "Fatima"],
        "family_name": ["Al-Mansoori", "Kumar", "Al-Zahra"],
        "date_of_birth": ["1985-03-15", "1990-07-22", "1992-01-01"],
        "nationality": ["UAE", "India", "UAE"],
        "source_facility": ["Cleveland Clinic Abu Dhabi", "Al Noor Hospital", "SSMC"],
        "registration_date": ["2024-01-10", "2024-02-15", "2024-03-20"],
        "canonical_id": ["P001", "P002", "P003"]
    })
    st.download_button(
        label="📄 Download Sample CSV",
        data=sample_data.to_csv(index=False).encode('utf-8'),
        file_name='sample_batch.csv',
        mime='text/csv',
        use_container_width=True
    )

    uploaded_file = st.file_uploader("Upload patient records (CSV)", type=["csv"])

if uploaded_file is None:
    st.info("👈 Please upload a CSV file in the sidebar to begin the assessment.")
    st.stop()

# ============================================================
# DATA PROCESSING
# ============================================================
df = pd.read_csv(uploaded_file)
required_cols = ["given_name", "family_name", "date_of_birth"]
missing_cols = [c for c in required_cols if c not in df.columns]
if missing_cols:
    st.error(f"Missing required columns in CSV: {missing_cols}")
    st.stop()

cv = CrossRecordValidator()
results = []

for index, row in df.iterrows():
    rec = PatientRecord(
        emirates_id=str(row.get('emirates_id', '')).strip() if pd.notna(row.get('emirates_id')) else None,
        given_name=str(row.get('given_name', '')).strip(),
        family_name=str(row.get('family_name', '')).strip(),
        date_of_birth=str(row.get('date_of_birth', '')).strip(),
        nationality=str(row.get('nationality', '')).strip(),
        source_facility=str(row.get('source_facility', '')).strip(),
        registration_date=str(row.get('registration_date', '')).strip(),
        canonical_id=str(row.get('canonical_id', f'ROW_{index}')).strip()
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
            explanation = f"TEMPORAL ERROR: The date of birth '{rec.date_of_birth}' is invalid or implausible."
            primary_issue = "Temporal Validity Error"
        elif weakest_dim == "identity":
            explanation = f"IDENTITY INCONSISTENCY: The Emirates ID '{rec.emirates_id}' format is malformed."
            primary_issue = "Malformed Identifier"
        else:
            explanation = f"Flagged due to low score in {weakest_dim}."
            primary_issue = f"Low {weakest_dim} Score"

    results.append({
        "canonical_id": rec.canonical_id,
        "given_name": rec.given_name,
        "family_name": rec.family_name,
        "source_facility": rec.source_facility,
        "trust_score": round(score, 3),
        "decision": decision,
        "explanation": explanation,
        "primary_issue": primary_issue,
        "dim_completeness": dims["completeness"],
        "dim_temporal": dims["temporal"],
        "dim_identity": dims["identity"],
        "dim_provenance": dims["provenance"],
        "dim_cross_record": dims["cross_record"],
    })
    
    cv.add_record(rec)

results_df = pd.DataFrame(results)

# ============================================================
# MAIN LAYOUT: TABS
# ============================================================
tab1, tab2, tab3 = st.tabs(["📊 Executive Dashboard", "🚩 Flagged Records", "📄 Regulatory Audit"])

with tab1:
    total = len(results_df)
    auto = len(results_df[results_df["decision"] == "AUTO_LINK"])
    flag = len(results_df[results_df["decision"] == "LINK_WITH_FLAG"])
    quar = len(results_df[results_df["decision"] == "QUARANTINE"])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Records", total)
    col2.metric("✅ Auto-Linked", auto)
    col3.metric("⚠️ Flagged", flag)
    col4.metric("🚨 Quarantined", quar)

    st.divider()
    
    st.subheader("Decision Breakdown")
    decision_counts = results_df["decision"].value_counts().reset_index()
    decision_counts.columns = ["Decision", "Count"]
    chart1 = alt.Chart(decision_counts).mark_bar(color="#4A6FA5").encode(
        x=alt.X("Count:Q", title="Number of Records"),
        y=alt.Y("Decision:N", sort="-x", title=""),
        tooltip=["Decision", "Count"]
    ).properties(height=250)
    st.altair_chart(chart1, use_container_width=True)

    st.subheader("Facility Risk Profile")
    st.markdown("Which hospitals are sending the most problematic data?")
    flagged_df = results_df[results_df["decision"].isin(["LINK_WITH_FLAG", "QUARANTINE"])]
    if not flagged_df.empty:
        fac_counts = flagged_df["source_facility"].value_counts().reset_index()
        fac_counts.columns = ["Facility", "Flagged Count"]
        chart2 = alt.Chart(fac_counts).mark_bar(color="#C62828").encode(
            x=alt.X("Flagged Count:Q", title="Number of Flagged Records"),
            y=alt.Y("Facility:N", sort="-x", title=""),
            tooltip=["Facility", "Flagged Count"]
        ).properties(height=300)
        st.altair_chart(chart2, use_container_width=True)
    else:
        st.info("No records were flagged in this batch.")

    st.subheader("Dimension Scoring Averages")
    st.markdown("Where is data quality failing across the five dimensions?")
    dim_means = results_df[["dim_completeness", "dim_temporal", "dim_identity", "dim_provenance", "dim_cross_record"]].mean().reset_index()
    dim_means.columns = ["Dimension", "Average Score"]
    dim_means["Dimension"] = ["Completeness", "Temporal", "Identity", "Provenance", "Cross-Record"]
    chart3 = alt.Chart(dim_means).mark_bar(color="#2E7D32").encode(
        x=alt.X("Average Score:Q", scale=alt.Scale(domain=[0, 1])),
        y=alt.Y("Dimension:N", sort="-x", title=""),
        tooltip=["Dimension", "Average Score"]
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
                
                # Pass the selected palette to the bar renderer
                render_dimension_bar("Completeness", row['dim_completeness'], palette)
                render_dimension_bar("Temporal", row['dim_temporal'], palette)
                render_dimension_bar("Identity", row['dim_identity'], palette)
                render_dimension_bar("Provenance", row['dim_provenance'], palette)
                render_dimension_bar("Cross-Record", row['dim_cross_record'], palette)

        st.write("")
        csv_flagged = flagged.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Flagged Records (CSV)",
            data=csv_flagged,
            file_name='flagged_identity_records.csv',
            mime='text/csv',
        )
    else:
        st.success("All records processed cleanly. No flags raised.")

with tab3:
    st.subheader("Batch Results")
    st.markdown(results_df[["canonical_id", "given_name", "family_name", "trust_score", "decision", "primary_issue"]].to_markdown(index=False))

    st.download_button(
        label="📥 Download Full Scored Batch (CSV)",
        data=results_df.to_csv(index=False).encode('utf-8'),
        file_name='full_scored_batch.csv',
        mime='text/csv',
    )

    if PDF_AVAILABLE:
        st.divider()
        st.subheader("📄 Regulatory Audit Trail")
        st.write("Generate a PDF report mapping flagged records to DOH Standard clauses.")
        
        if st.button("Generate PDF Audit Report"):
            with st.spinner("Generating PDF..."):
                temp_csv_path = "temp_scored_batch.csv"
                results_df.to_csv(temp_csv_path, index=False)
                pdf_path = "trust_report.pdf"
                
                try:
                    generate_report(temp_csv_path, pdf_path, title="Identity Trust Batch Report")
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            label="📥 Download PDF Report",
                            data=f,
                            file_name="Identity_Trust_Report.pdf",
                            mime="application/pdf"
                        )
                except Exception as e:
                    st.error(f"Could not generate PDF: {e}")
