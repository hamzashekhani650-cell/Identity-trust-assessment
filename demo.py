import streamlit as st
import pandas as pd
import os
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

st.warning("⚠️ **Privacy Notice:** This demo uses synthetic data only. Do not upload real patient health information (PHI).")

st.markdown("""
**Instructions:** Upload a CSV containing patient records. The trust layer will assess each record and flag any identity collisions or low-trust records for review.
""")

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
    label="📄 Download Sample CSV to Test",
    data=sample_data.to_csv(index=False).encode('utf-8'),
    file_name='sample_batch.csv',
    mime='text/csv',
)

uploaded_file = st.file_uploader("Upload patient records (CSV)", type=["csv"])

if uploaded_file is not None:
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

        # ============================================================
        # UPGRADED: GRANULAR, FORENSIC EXPLANATIONS
        # ============================================================
        explanation = "Record is clean and trusted."
        primary_issue = "None"
        
        if decision in ("LINK_WITH_FLAG", "QUARANTINE"):
            weakest_dim = min(dims, key=dims.get)
            weakest_val = dims[weakest_dim]
            
            if weakest_dim == "cross_record":
                if weakest_val == 0.0:
                    # Find exactly who owns this ID to make the explanation forensic
                    colliding_id = "Unknown"
                    colliding_patient = "Unknown"
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
                missing_fields = []
                if not rec.emirates_id: missing_fields.append("Emirates ID")
                if not rec.given_name: missing_fields.append("Given Name")
                if not rec.family_name: missing_fields.append("Family Name")
                if not rec.date_of_birth: missing_fields.append("Date of Birth")
                explanation = f"INCOMPLETE DATA: Missing required fields: {', '.join(missing_fields)}."
                primary_issue = "Missing Demographics"
            elif weakest_dim == "provenance":
                explanation = (f"LOW-TRUST SOURCE: Facility '{rec.source_facility}' is not in the high-trust tier. "
                               f"Records from this source require manual verification.")
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
    # DASHBOARD & ANALYTICS
    # ============================================================
    st.divider()
    total = len(results_df)
    auto = len(results_df[results_df["decision"] == "AUTO_LINK"])
    flag = len(results_df[results_df["decision"] == "LINK_WITH_FLAG"])
    quar = len(results_df[results_df["decision"] == "QUARANTINE"])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Records", total)
    col2.metric("✅ Auto-Linked", auto)
    col3.metric("⚠️ Flagged", flag)
    col4.metric("🚨 Quarantined", quar)

    st.subheader("📊 Deep Dive Analytics")
    tab1, tab2, tab3 = st.tabs(["Decision Breakdown", "Root Cause Analysis", "Facility Risk Profile"])
    
    with tab1:
        st.markdown("**Distribution of Routing Decisions**")
        decision_counts = results_df["decision"].value_counts()
        st.bar_chart(decision_counts)
        
    with tab2:
        st.markdown("**Top Reasons for Flagging/Quarantine**")
        issue_counts = results_df[results_df["primary_issue"] != "None"]["primary_issue"].value_counts()
        if not issue_counts.empty:
            st.bar_chart(issue_counts)
        else:
            st.info("No records were flagged in this batch.")
            
    with tab3:
        st.markdown("**Flagged/Quarantined Records by Source Facility**")
        flagged_df = results_df[results_df["decision"].isin(["LINK_WITH_FLAG", "QUARANTINE"])]
        if not flagged_df.empty:
            facility_counts = flagged_df["source_facility"].value_counts()
            st.bar_chart(facility_counts)
        else:
            st.info("No records were flagged in this batch.")

    # ============================================================
    # DIMENSION SCORING DISTRIBUTION
    # ============================================================
    st.subheader("📉 Dimension Scoring Averages")
    st.markdown("Where is the data quality failing across the five dimensions?")
    dim_means = results_df[["dim_completeness", "dim_temporal", "dim_identity", "dim_provenance", "dim_cross_record"]].mean()
    dim_means.index = ["Completeness", "Temporal", "Identity", "Provenance", "Cross-Record"]
    st.bar_chart(dim_means)

    # ============================================================
    # BATCH RESULTS TABLE
    # ============================================================
    st.divider()
    st.subheader("Batch Results")
    st.markdown(results_df[["canonical_id", "given_name", "family_name", "trust_score", "decision", "primary_issue"]].to_markdown(index=False))

    st.download_button(
        label="📥 Download Full Scored Batch (CSV)",
        data=results_df.to_csv(index=False).encode('utf-8'),
        file_name='full_scored_batch.csv',
        mime='text/csv',
    )

    # ============================================================
    # FLAGGED RECORDS SECTION
    # ============================================================
    flagged = results_df[results_df["decision"].isin(["LINK_WITH_FLAG", "QUARANTINE"])]
    
    if not flagged.empty:
        st.divider()
        st.subheader("🔍 Flagged Records for Review")
        st.warning(f"{len(flagged)} record(s) require manual review.")
        
        for _, row in flagged.iterrows():
            with st.expander(f"{row['canonical_id']} - {row['given_name']} {row['family_name']} ({row['decision']})"):
                st.write(f"**Trust Score:** {row['trust_score']}")
                st.write(f"**Primary Issue:** {row['primary_issue']}")
                st.info(f"**Forensic Detail:** {row['explanation']}")
                st.write("**Dimension Scores:**")
                st.progress(row['dim_completeness'], text=f"Completeness: {row['dim_completeness']:.2f}")
                st.progress(row['dim_temporal'], text=f"Temporal: {row['dim_temporal']:.2f}")
                st.progress(row['dim_identity'], text=f"Identity: {row['dim_identity']:.2f}")
                st.progress(row['dim_provenance'], text=f"Provenance: {row['dim_provenance']:.2f}")
                st.progress(row['dim_cross_record'], text=f"Cross-Record: {row['dim_cross_record']:.2f}")

        st.write("")
        csv = flagged.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Flagged Records for Review",
            data=csv,
            file_name='flagged_identity_records.csv',
            mime='text/csv',
        )
    else:
        st.success("All records processed cleanly. No flags raised.")

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
                            label="📥 Download PDF",
                            data=f,
                            file_name="Identity_Trust_Report.pdf",
                            mime="application/pdf"
                        )
                except Exception as e:
                    st.error(f"Could not generate PDF: {e}")
