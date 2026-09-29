import streamlit as st
import json
from trust_layer.fhir import from_fhir_patient
from trust_layer.validators import (
    validate_completeness, validate_temporal,
    validate_identity_consistency, validate_provenance,
    CrossRecordValidator
)
from trust_layer.scoring import compute_trust_score
from trust_layer.router import route_decision
from trust_layer.audit import log_decision

st.set_page_config(page_title="Identity Trust Assessment", layout="centered")

st.title("Identity Trust Assessment")
st.caption("Five-dimension trust layer for patient identity resolution in HIEs")

st.subheader("Input: FHIR Patient Resource")

default_record = {
    "resourceType": "Patient",
    "identifier": [
        {"system": "https://fhir.doh.gov.ae/emirates-id",
         "value": "784-1985-1234567-1"}
    ],
    "name": [{"given": ["Ahmed"], "family": "Al-Mansoori"}],
    "birthDate": "1985-03-15",
    "meta": {"tag": [{"system": "https://fhir.doh.gov.ae/facility",
                      "display": "Cleveland Clinic Abu Dhabi"}]}
}

raw = st.text_area(
    "Paste a FHIR Patient resource (JSON)",
    value=json.dumps(default_record, indent=2),
    height=280
)

if st.button("Assess"):
    try:
        fhir_json = json.loads(raw)
        record = from_fhir_patient(fhir_json)

        cv = CrossRecordValidator()
        dims = {
            "completeness": validate_completeness(record),
            "temporal": validate_temporal(record),
            "identity": validate_identity_consistency(record),
            "provenance": validate_provenance(record),
            "cross_record": cv.validate(record),
        }
        score = compute_trust_score(**dims)
        decision = route_decision(score)

        st.subheader("Result")
        st.metric("Trust Score", f"{score:.3f}")
        st.metric("Decision", decision)

        st.subheader("Dimension Breakdown")
        for name, value in dims.items():
            st.progress(value, text=f"{name}: {value:.2f}")

        log_decision(record, dims, score, decision)

    except Exception as e:
        st.error(f"Error: {e}")