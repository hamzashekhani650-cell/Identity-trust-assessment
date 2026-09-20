
import sys, os, csv, json
sys.path.insert(0, '/content')

from trust_layer.record import PatientRecord
from trust_layer.validators import (
    validate_completeness, validate_temporal,
    validate_identity_consistency, validate_provenance,
    CrossRecordValidator,
)
from trust_layer.scoring import compute_trust_score
from trust_layer.router import route_decision_hard
from trust_layer.audit import log_decision


def process_csv(input_path, output_path, log_path="batch_audit.jsonl"):
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    if not rows:
        raise ValueError("Input CSV is empty")

    def get(row, key):
        for k, v in row.items():
            if k and k.strip().lower() == key:
                return (v or "").strip()
        return ""

    # Single-pass: register each record AFTER scoring it.
    # This makes the MPI state grow incrementally, so a collision
    # between record N and record M (M > N) is caught when M arrives,
    # because only records 1..N-1 are in the index at that point.
    cv = CrossRecordValidator()

    out_fieldnames = fieldnames + [
        "trust_score", "decision",
        "dim_completeness", "dim_temporal", "dim_identity",
        "dim_provenance", "dim_cross_record",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames)
        writer.writeheader()
        for i, row in enumerate(rows):
            rec = PatientRecord(
                emirates_id=get(row, "emirates_id") or None,
                given_name=get(row, "given_name"),
                family_name=get(row, "family_name"),
                date_of_birth=get(row, "date_of_birth"),
                nationality=get(row, "nationality"),
                source_facility=get(row, "source_facility"),
                registration_date=get(row, "registration_date"),
                canonical_id=get(row, "canonical_id") or "ROW_" + str(i),
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
            log_decision(rec, dims, score, decision, log_path)

            out = dict(row)
            out["trust_score"] = score
            out["decision"] = decision
            out["dim_completeness"] = dims["completeness"]
            out["dim_temporal"] = dims["temporal"]
            out["dim_identity"] = dims["identity"]
            out["dim_provenance"] = dims["provenance"]
            out["dim_cross_record"] = dims["cross_record"]
            writer.writerow(out)

            # Register AFTER scoring — this is the fix
            cv.add_record(rec)

    return {
        "input": input_path,
        "output": output_path,
        "records": len(rows),
        "audit_log": log_path,
    }
