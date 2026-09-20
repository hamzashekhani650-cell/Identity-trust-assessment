import sys
import os
sys.path.insert(0, os.getcwd())

from trust_layer.record import PatientRecord
from trust_layer.validators import (
    validate_completeness,
    validate_temporal,
    validate_identity_consistency,
    validate_provenance,
    CrossRecordValidator,
)
from trust_layer.scoring import compute_trust_score
from trust_layer.router import route_decision


def test_completeness_full():
    r = PatientRecord(
        emirates_id="784-1985-1234567-1",
        given_name="Ahmed",
        family_name="Al-Mansoori",
        date_of_birth="1985-03-15",
    )
    assert validate_completeness(r) == 1.0


def test_completeness_passport_fallback():
    r = PatientRecord(
        passport_number="AB1234567",
        given_name="Raj",
        family_name="Kumar",
        date_of_birth="1990-07-22",
    )
    assert validate_completeness(r) == 0.7


def test_completeness_missing_all():
    r = PatientRecord(
        given_name="Maria",
        family_name="Santos",
        date_of_birth="1992-11-03",
    )
    assert validate_completeness(r) == 0.0


def test_temporal_valid():
    r = PatientRecord(
        given_name="Ahmed",
        family_name="Al-Mansoori",
        date_of_birth="1985-03-15",
        registration_date="2024-01-10",
    )
    assert validate_temporal(r) == 1.0


def test_temporal_future_dob():
    r = PatientRecord(
        given_name="Test",
        family_name="Patient",
        date_of_birth="2030-01-01",
        registration_date="2024-01-10",
    )
    assert validate_temporal(r) == 0.0


def test_identity_valid_emirates():
    r = PatientRecord(
        emirates_id="784-1985-1234567-1",
        given_name="Ahmed",
        family_name="Al-Mansoori",
        nationality="UAE",
    )
    assert validate_identity_consistency(r) == 1.0


def test_identity_malformed_emirates():
    r = PatientRecord(
        emirates_id="123-4567-890",
        given_name="Raj",
        family_name="Kumar",
        nationality="IN",
    )
    assert validate_identity_consistency(r) == 0.5


def test_provenance_known_high_tier():
    r = PatientRecord(source_facility="Cleveland Clinic Abu Dhabi")
    assert validate_provenance(r) == 1.0


def test_provenance_unknown_facility():
    r = PatientRecord(source_facility="Some Unknown Clinic")
    assert validate_provenance(r) == 0.3


def test_cross_record_no_conflict():
    cv = CrossRecordValidator()
    r1 = PatientRecord(
        emirates_id="784-1985-1111111-1",
        given_name="Ahmed", family_name="Al-Mansoori",
        date_of_birth="1985-03-15", canonical_id="A",
    )
    cv.add_record(r1)
    r2 = PatientRecord(
        emirates_id="784-1985-1111111-1",
        given_name="Ahmed", family_name="Al-Mansoori",
        date_of_birth="1985-03-15", canonical_id="A",
    )
    assert cv.validate(r2) == 1.0


def test_cross_record_direct_collision():
    cv = CrossRecordValidator()
    r1 = PatientRecord(
        emirates_id="784-1985-1111111-1",
        given_name="Ahmed", family_name="Al-Mansoori",
        date_of_birth="1985-03-15", canonical_id="A",
    )
    cv.add_record(r1)
    r2 = PatientRecord(
        emirates_id="784-1985-1111111-1",
        given_name="Fatima", family_name="Al-Zahra",
        date_of_birth="1992-01-01", canonical_id="B",
    )
    assert cv.validate(r2) == 0.0


def test_composite_score_high():
    score = compute_trust_score(1.0, 1.0, 1.0, 1.0, 1.0)
    assert score == 1.0


def test_composite_score_with_collision():
    score = compute_trust_score(1.0, 1.0, 0.85, 1.0, 0.0)
    assert score < 0.85
    assert score > 0.5


def test_router_auto_link():
    assert route_decision(0.95) == "AUTO_LINK"


def test_router_flag():
    assert route_decision(0.70) == "LINK_WITH_FLAG"


def test_router_quarantine():
    assert route_decision(0.30) == "QUARANTINE"

def test_hl7v2_parsing():
    import sys, os
    sys.path.insert(0, '/content')
    from trust_layer.hl7v2 import from_hl7v2_message

    msg = (
        "MSH|^~\\&|HIS|CLEVELAND|MALAFFI|DOH|20240110120000||ADT^A04|MSG0001|P|2.5\r"
        "PID|1||784-1985-1234567-1^^^DOH^MR||Al-Mansoori^Ahmed||19850315|M|||Abu Dhabi^^UAE\r"
        "PV1|1|O"
    )

    rec = from_hl7v2_message(msg, canonical_id="HL7_TEST", facility="Cleveland Clinic Abu Dhabi")
    assert rec.emirates_id == "784-1985-1234567-1"
    assert rec.given_name == "Ahmed"
    assert rec.family_name == "Al-Mansoori"
    assert rec.date_of_birth == "1985-03-15"
