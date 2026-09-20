import sys
import os
import json
import argparse

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


def main():
    parser = argparse.ArgumentParser(
        description="Assess trust score for a patient record."
    )
    parser.add_argument("--emirates-id", required=False)
    parser.add_argument("--given-name", required=True)
    parser.add_argument("--family-name", required=True)
    parser.add_argument("--dob", required=True)
    parser.add_argument("--nationality", required=False, default="")
    parser.add_argument("--facility", required=False, default="")
    parser.add_argument("--registration-date", required=False, default="")

    args = parser.parse_args()

    record = PatientRecord(
        emirates_id=args.emirates_id,
        given_name=args.given_name,
        family_name=args.family_name,
        date_of_birth=args.dob,
        nationality=args.nationality,
        source_facility=args.facility,
        registration_date=args.registration_date,
    )

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

    output = {
        "trust_score": score,
        "decision": decision,
        "dimensions": dims,
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()