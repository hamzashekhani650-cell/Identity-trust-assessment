# app.py
import os
from typing import List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

from trust_engine import TrustEngine
from trust_layer.hl7_ingest import parse_hl7_message, validate_hl7_structure

API_KEY = os.environ.get('TRUST_LAYER_API_KEY', '')
REGION_PROFILE = os.environ.get('REGION_PROFILE', 'UAE (DOH)')
THRESHOLD_AUTO = float(os.environ.get('THRESHOLD_AUTO', '0.75'))
THRESHOLD_QUAR = float(os.environ.get('THRESHOLD_QUAR', '0.45'))

# Initialize the Engine
engine = TrustEngine(
    region_profile=REGION_PROFILE,
    auto_threshold=THRESHOLD_AUTO,
    quar_threshold=THRESHOLD_QUAR
)

# Initialize Prometheus Metrics
TRUST_DECISIONS = Counter(
    'trust_gate_decisions_total', 
    'Total number of routing decisions made', 
    ['decision_type']
)

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
    weighted_sum: float
    min_dimension: float
    decision: str
    routing_reason: str
    dimensions: dict
    primary_issue: str
    explanation: str
    config_version: str
    thresholds: dict

app = FastAPI(
    title='Identity Trust Assessment API',
    description='Pre-submission record trust gate for patient identity resolution and claim readiness in HIEs.',
    version='v0.7.0',
)

def _check_auth(x_api_key):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail='Invalid or missing API key')

@app.get('/health')
def health():
    return {
        'status': 'ok',
        'region': engine.region_profile,
        'thresholds': {'auto': engine.threshold_auto, 'quarantine': engine.threshold_quar},
        'config_version': 'v0.7.0',
        'auth_required': bool(API_KEY),
    }

@app.get('/metrics')
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post('/assess', response_model=Decision)
def assess(payload: PatientInput, x_api_key: Optional[str] = Header(None)):
    _check_auth(x_api_key)
    # Convert Pydantic model to plain dict for the engine
    result = engine.assess_record(payload.model_dump())
    
    # Click the Prometheus tally
    TRUST_DECISIONS.labels(decision_type=result['decision']).inc()
    
    return result

@app.post('/assess-hl7', response_model=Decision)
def assess_hl7(payload: HL7Input, x_api_key: Optional[str] = Header(None)):
    _check_auth(x_api_key)
    ok, issues = validate_hl7_structure(payload.message)
    if not ok:
        raise HTTPException(status_code=400, detail=f'Invalid HL7 message: {"; ".join(issues)}')
    
    parsed = parse_hl7_message(payload.message)
    
    # Map HL7 parsed output to the dictionary the engine expects
    record_dict = {
        'emirates_id': parsed.get('emirates_id'),
        'given_name': parsed.get('given_name', ''),
        'family_name': parsed.get('family_name', ''),
        'date_of_birth': parsed.get('date_of_birth', ''),
        'gender': parsed.get('gender', ''),
        'nationality': parsed.get('nationality', ''),
        'source_facility': parsed.get('source_facility', ''),
        'registration_date': parsed.get('registration_date', ''),
        'canonical_id': parsed.get('canonical_id', ''),
    }
    
    result = engine.assess_record(record_dict)
    
    # Click the Prometheus tally
    TRUST_DECISIONS.labels(decision_type=result['decision']).inc()
    
    return result

@app.post('/assess-batch')
def assess_batch(payloads: List[PatientInput], x_api_key: Optional[str] = Header(None)):
    _check_auth(x_api_key)
    results = []
    for p in payloads:
        res = engine.assess_record(p.model_dump())
        
        # Click the Prometheus tally for each record
        TRUST_DECISIONS.labels(decision_type=res['decision']).inc()
        
        results.append(res)
    return results

@app.post('/reset')
def reset_state(x_api_key: Optional[str] = Header(None)):
    _check_auth(x_api_key)
    engine.reset()
    return {'status': 'reset'}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
    @app.get("/decisions")
def get_decisions(limit: int = 500):
    """Fetches recent audit log entries for the Streamlit dashboard."""
    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(os.environ.get("DATABASE_URL"), sslmode='require')
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(f"SELECT * FROM decisions ORDER BY id DESC LIMIT {limit}")
        records = cur.fetchall()
        cur.close()
        conn.close()
        return records
    except Exception as e:
        return {"error": str(e)}
