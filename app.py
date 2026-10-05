'''
Identity Trust Assessment — FastAPI service.

Exposes the trust engine as a REST API. A hospital interface engine
(Mirth Connect, Rhapsody, Cloverleaf) calls /assess with a patient
record and receives a routing decision in return.

Endpoints:
  GET  /health              — liveness check
  POST /assess              — accept a JSON patient record, return decision
  POST /assess-hl7          — accept a raw HL7 v2 message, return decision
  POST /assess-batch        — accept a list of JSON records, return decisions

Auth:
  X-API-Key header. In production, set TRUST_LAYER_API_KEY env var.
  If unset, the service runs in open mode (development only).

Configuration:
  REGION_PROFILE — 'UAE (DOH)' or 'India (ABDM)'. Default UAE.
  THRESHOLD_AUTO — auto-link threshold. Default 0.75.
  THRESHOLD_QUAR — quarantine threshold. Default 0.45.

Deployment:
  This service is intended to run inside the hospital's infrastructure
  via Docker. No patient data should ever leave the hospital network.
'''
import os
import re
from typing import List, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from trust_layer.scoring import compute_trust_score
from trust_layer.router import route_decision_hard
from trust_layer.validators import CrossRecordValidator
from trust_layer.hl7_ingest import parse_hl7_message, validate_hl7_structure


API_KEY = os.environ.get('TRUST_LAYER_API_KEY', '')
REGION_PROFILE = os.environ.get('REGION_PROFILE', 'UAE (DOH)')
THRESHOLD_AUTO = float(os.environ.get('THRESHOLD_AUTO', '0.75'))
THRESHOLD_QUAR = float(os.environ.get('THRESHOLD_QUAR', '0.45'))


REGION_CONFIG = {
    'UAE (DOH)': {
        'id_label': 'Emirates ID',
        'id_pattern': r'^784\d{12}$',
        'trusted_facilities': {
            'Cleveland Clinic Abu Dhabi', 'Ssmc', 'Al Noor Hospital',
            'Tawam Hospital', 'Sheikh Khalifa Medical City',
        },
        'required_fields': ['emirates_id', 'given_name', 'family_name', 'date_of_birth'],
    },
    'India (ABDM)': {
        'id_label': 'ABHA / Aadhaar',
        'id_pattern': r'^\d{12}$',
        'trusted_facilities': {
            'Manipal Hospital', 'Apollo Hospital', 'Fortis Healthcare',
            'Max Healthcare', 'Aiims', 'Aiims Delhi', 'Narayana Health',
        },
        'required_fields': ['emirates_id', 'given_name', 'family_name', 'date_of_birth'],
    },
}


class PatientInput(BaseModel):
    emirates_id: Optional[str] = None
    given_name: str = ''
    family_name: str = ''
    date_of_birth: str = ''
    gender: str = ''
    nationality: str = ''
    source_facility: str = ''
    registration_date: str = ''
    canonical_id: str = ''


class HL7Input(BaseModel):
    message: str


class Decision(BaseModel):
    canonical_id: str
    trust_score: float
    decision: str
    dimensions: dict
    primary_issue: str
    explanation: str
    config_version: str
    thresholds: dict


app = FastAPI(
    title='Identity Trust Assessment API',
    description='Pre-submission record trust gate for patient identity resolution and claim readiness in HIEs.',
    version='v0.6.0',
)

# Single-process stateful validator. In production with multiple workers,
# this should be backed by Redis or a shared MPI service. For a shadow-mode
# pilot on a single instance, this is sufficient.
_cross_validator = CrossRecordValidator()


def _check_auth(x_api_key):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail='Invalid or missing API key')


def _normalize_text(value):
    if not value:
        return ''
    s = str(value).strip()
    if s.lower() in ('nan', 'nat', 'none'):
        return ''
    return ' '.join(s.split()).title()


def _normalize_id(value):
    if not value:
        return None
    digits = ''.join(c for c in str(value) if c.isdigit())
    return digits if digits else None


def _score_record(payload):
    cfg = REGION_CONFIG[REGION_PROFILE]

    # Normalize inputs the same way the CSV pipeline does
    given = _normalize_text(payload.given_name)
    family = _normalize_text(payload.family_name)
    dob = str(payload.date_of_birth).strip()[:10]
    eid = _normalize_id(payload.emirates_id)
    facility = _normalize_text(payload.source_facility)
    canonical_id = payload.canonical_id or 'UNKNOWN'

    # Dimension 1: Completeness
    present = 0
    required = cfg['required_fields']
    fields = {
        'emirates_id': eid,
        'given_name': given,
        'family_name': family,
        'date_of_birth': dob,
    }
    for f in required:
        if fields.get(f):
            present += 1
    completeness = round(present / len(required), 2) if required else 1.0

    # Dimension 2: Temporal validity
    try:
        year = int(dob[:4])
        temporal = 1.0 if 1900 <= year <= 2025 else 0.3
    except (ValueError, TypeError):
        temporal = 0.0

    # Dimension 3: Identity consistency
    if not eid:
        identity = 0.0
    elif re.match(cfg['id_pattern'], eid):
        identity = 1.0
    else:
        identity = 0.3

    # Dimension 4: Provenance
    if not facility:
        provenance = 0.0
    elif facility in cfg['trusted_facilities']:
        provenance = 1.0
    else:
        provenance = 0.7

    # Dimension 5: Cross-record consistency
    class _Rec:
        pass
    rec = _Rec()
    rec.emirates_id = eid
    rec.given_name = given
    rec.family_name = family
    rec.date_of_birth = dob
    rec.canonical_id = canonical_id

    cross_record = _cross_validator.validate(rec)

    dims = {
        'completeness': completeness,
        'temporal': temporal,
        'identity': identity,
        'provenance': provenance,
        'cross_record': cross_record,
    }
    score = compute_trust_score(**dims)
    decision = route_decision_hard(score, cross_record, THRESHOLD_AUTO, THRESHOLD_QUAR)

    # Explanation
    explanation = 'Record is clean and trusted.'
    primary_issue = 'None'
    if decision in ('LINK_WITH_FLAG', 'QUARANTINE'):
        weakest = min(dims, key=dims.get)
        if weakest == 'cross_record':
            if cross_record == 0.0:
                explanation = f'Identifier collision: {cfg["id_label"]} {eid} is already registered to a different patient.'
                primary_issue = 'Identifier Collision'
            elif cross_record == 0.5:
                explanation = 'Name and DOB match an existing patient, but the identifier differs.'
                primary_issue = 'Potential Name/DOB Collision'
        elif weakest == 'completeness':
            missing = [f for f in required if not fields.get(f)]
            explanation = f'Missing required fields: {", ".join(missing)}.'
            primary_issue = 'Missing Demographics'
        elif weakest == 'provenance':
            explanation = f'Facility "{facility}" is not in the trusted tier.'
            primary_issue = 'Untrusted Facility'
        elif weakest == 'temporal':
            explanation = f'Date of birth "{dob}" is invalid or outside the plausible range.'
            primary_issue = 'Temporal Validity Error'
        elif weakest == 'identity':
            explanation = f'{cfg["id_label"]} format does not match region standard.'
            primary_issue = 'Malformed Identifier'

    # Register for future collision detection
    _cross_validator.add_record(rec)

    return {
        'canonical_id': canonical_id,
        'trust_score': round(score, 3),
        'decision': decision,
        'dimensions': dims,
        'primary_issue': primary_issue,
        'explanation': explanation,
        'config_version': 'v0.6.0',
        'thresholds': {'auto': THRESHOLD_AUTO, 'quarantine': THRESHOLD_QUAR},
    }


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'region': REGION_PROFILE,
        'thresholds': {'auto': THRESHOLD_AUTO, 'quarantine': THRESHOLD_QUAR},
        'config_version': 'v0.6.0',
        'auth_required': bool(API_KEY),
    }


@app.post('/assess', response_model=Decision)
def assess(payload: PatientInput, x_api_key: Optional[str] = Header(None)):
    _check_auth(x_api_key)
    return _score_record(payload)


@app.post('/assess-hl7', response_model=Decision)
def assess_hl7(payload: HL7Input, x_api_key: Optional[str] = Header(None)):
    _check_auth(x_api_key)
    ok, issues = validate_hl7_structure(payload.message)
    if not ok:
        raise HTTPException(status_code=400, detail=f'Invalid HL7 message: {"; ".join(issues)}')
    parsed = parse_hl7_message(payload.message)
    patient = PatientInput(
        emirates_id=parsed.get('emirates_id'),
        given_name=parsed.get('given_name', ''),
        family_name=parsed.get('family_name', ''),
        date_of_birth=parsed.get('date_of_birth', ''),
        gender=parsed.get('gender', ''),
        nationality=parsed.get('nationality', ''),
        source_facility=parsed.get('source_facility', ''),
        registration_date=parsed.get('registration_date', ''),
        canonical_id=parsed.get('canonical_id', ''),
    )
    return _score_record(patient)


@app.post('/assess-batch')
def assess_batch(payloads: List[PatientInput], x_api_key: Optional[str] = Header(None)):
    _check_auth(x_api_key)
    return [_score_record(p) for p in payloads]


@app.post('/reset')
def reset_state(x_api_key: Optional[str] = Header(None)):
    '''Clear the in-memory cross-record validator. Useful for tests.'''
    _check_auth(x_api_key)
    global _cross_validator
    _cross_validator = CrossRecordValidator()
    return {'status': 'reset'}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
