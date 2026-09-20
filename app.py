
import os
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from trust_layer.record import PatientRecord
from trust_layer.validators import (
    validate_completeness, validate_temporal,
    validate_identity_consistency, validate_provenance,
    CrossRecordValidator,
)
from trust_layer.scoring import compute_trust_score
from trust_layer.router import route_decision_hard


API_KEY = os.environ.get("TRUST_LAYER_API_KEY", "dev-key-change-in-production")
CONFIG_VERSION = "v0.2.0"


app = FastAPI(
    title="Identity Trust Assessment API",
    description="Five-dimension trust assessment for patient identity resolution in HIEs.",
    version=CONFIG_VERSION,
)

cross_validator = CrossRecordValidator()


class PatientInput(BaseModel):
    emirates_id: Optional[str] = None
    given_name: str = ""
    family_name: str = ""
    date_of_birth: str = ""
    nationality: str = ""
    source_facility: str = ""
    registration_date: str = ""
    canonical_id: str = ""


def check_auth(x_api_key: Optional[str]):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/health")
def health():
    return {"status": "ok", "config_version": CONFIG_VERSION}


@app.post("/assess")
def assess(payload: PatientInput, x_api_key: Optional[str] = Header(None)):
    check_auth(x_api_key)
    record = PatientRecord(**payload.dict())

    dims = {
        "completeness": validate_completeness(record),
        "temporal": validate_temporal(record),
        "identity": validate_identity_consistency(record),
        "provenance": validate_provenance(record),
        "cross_record": cross_validator.validate(record),
    }
    score = compute_trust_score(**dims)
    decision = route_decision_hard(score, dims["cross_record"])

    return {
        "trust_score": score,
        "decision": decision,
        "dimensions": dims,
        "config_version": CONFIG_VERSION,
    }


@app.post("/register")
def register(payload: PatientInput, x_api_key: Optional[str] = Header(None)):
    check_auth(x_api_key)
    record = PatientRecord(**payload.dict())
    cross_validator.add_record(record)
    return {"registered": record.canonical_id, "config_version": CONFIG_VERSION}
