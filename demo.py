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

# ============================================================
# ADDITION 1: PRIVACY WARNING BANNER
# ============================================================
st.warning("⚠️ **Privacy Notice:** This demo uses synthetic data only. Do not upload real patient health information (PHI).")

st.markdown("""
**Instructions:** Upload a CSV containing patient records. The trust layer will assess each record and flag any identity collisions or low-trust records for review.
""")

# ============================================================
# ADDITION 2: SAMPLE CSV DOWNLOAD
# ============================================================
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

        explanation = "Record is clean and trusted."
        if decision in ("LINK_WITH_FLAG", "QUARANTINE"):
            weakest_dim = min(dims, key=dims.get)
            weakest_val = dims[weakest_dim]
            
            if weakest_dim == "cross_record":
                if weakest_val == 0.0:
                    explanation = "Identifier collision detected: this record shares an identifier with a different patient already in the system."
                elif weakest_val == 0.5:
                    explanation = "Potential collision: this record's name and date of birth match an existing patient, but the identifier differs."
            elif weakest_dim == "completeness":
                explanation = "Incomplete data: missing required identity fields."
            elif weakest_dim == "temporal":
                explanation = "Temporal error: invalid or suspicious date of birth."
            elif weakest_dim == "identity":
                explanation = "Identity inconsistency: malformed identifier format."
            elif weakest_dim == "provenance":
                explanation = "Low-trust source: the facility is not in the high-trust tier."
            else:
                explanation = f"Flagged due to low score in {weakest_dim}."

        results.append({
            "canonical_id": rec.canonical_id,
            "given_name": rec.given_name,
            "family_name": rec.family_name,
            "trust_score": round(score, 3),
            "decision": decision,
            "explanation": explanation,
        })
        
        cv.add_record(rec)

    results_df = pd.DataFrame(results)

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

    st.subheader("Decision Breakdown")
    decision_counts = results_df["decision"].value_counts()
    st.bar_chart(decision_counts)

    st.divider()
    st.subheader("Batch Results")
    st.markdown(results_df[["canonical_id", "given_name", "family_name", "trust_score", "decision", "explanation"]].to_markdown(index=False))

    # ============================================================
    # ADDITION 3: DOWNLOAD FULL SCORED CSV
    # ============================================================
    st.download_button(
        label="📥 Download Full Scored Batch (CSV)",
        data=results_df.to_csv(index=False).encode('utf-8'),
        file_name='full_scored_batch.csv',
        mime='text/csv',
    )

    flagged = results_df[results_df["decision"].isin(["LINK_WITH_FLAG", "QUARANTINE"])]
    
    if not flagged.empty:
        st.divider()
        st.subheader("⚠️ Flagged Records for Review")
        st.warning(f"{len(flagged)} record(s) require manual review.")
        
        for _, row in flagged.iterrows():
            with st.expander(f"{row['canonical_id']} - {row['given_name']} {row['family_name']} ({row['decision']})"):
                st.write(f"**Trust Score:** {row['trust_score']}")
                st.write(f"**Reason:** {row['explanation']}")
        
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
