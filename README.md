# Identity Trust Assessment

**A production-ready pre-submission trust gate for patient identity resolution in hyper-diverse health information exchanges.**

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://identity-trust-assessment-ccyev5krcnjabjkd24eu5y.streamlit.app/)
[![FastAPI Docs](https://img.shields.io/badge/API-Docs-009688)](https://identity-trust-api.onrender.com/docs)

---

## The Problem

Health information exchanges link patient records across hospitals, clinics, and labs. When two different patients share the same identifier (Emirates ID, MRN, insurance number), pairwise matchers link them incorrectly. One patient's medical history attaches to another's. This is a silent data corruption that can have severe clinical and financial consequences.

## The Solution

A five-dimension trust assessment framework that scores every incoming patient record **before** any linkage decision is made. The composite score routes each record to **Auto-Link**, **Flag-for-Review**, or **Quarantine**, with a plain-language reason for every decision.

The framework is deployed as a **FastAPI backend** for hospital integration and a **Streamlit dashboard** for data quality teams.

### The Five Dimensions

1.  **Completeness** – are required identity fields present?
2.  **Temporal Validity** – do the dates make sense?
3.  **Identity Consistency** – do identifiers agree with demographics?
4.  **Provenance** – is the source facility trusted?
5.  **Cross-Record Consistency** – does this record collide with an existing identity?

## Architecture

┌─────────────┐      ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Hospital   │      │   FastAPI       │      │   Trust Engine  │      │   PostgreSQL    │
│  Interface  │─────▶│   Backend       │─────▶│   (5-Dimension  │─────▶│   (Neon)        │
│  Engine     │      │   (Render)      │      │   Scoring)      │      │   Audit Log     │
└─────────────┘      └─────────────────┘      └─────────────────┘      └─────────────────┘
                            ▲
                            │
                     ┌─────────────┐
                     │  Streamlit  │
                     │  Dashboard  │
                     │  (Cloud)    │
                     └─────────────┘

- **Hospital IT** sends HL7 v2 ADT messages via MLLP or SFTP batches.
- **FastAPI Backend** parses the message and calls the trust engine.
- **Trust Engine** scores the record across five dimensions and routes it.
- **PostgreSQL** stores every decision in a persistent, audit-ready database.
- **Streamlit Dashboard** provides a live view of the audit trail and flagged records.

## Results

- Collision rejection: **96.0%** Gulf, **92.6%** Australia (vs. 53.4% / 30.7% for Fellegi-Sunter)
- Non-overlapping 95% confidence intervals in both contexts
- Fairness audit (n=2,000, six nationality groups): chi-squared = 7.25, p = 0.203 (no significant bias)
- Fellegi-Sunter comparator externally validated on Febrl1 benchmark (F1 = 0.862)

## Live Deployments

- **Streamlit Dashboard**: [https://identity-trust-assessment-ccyev5krcnjabjkd24eu5y.streamlit.app/](https://identity-trust-assessment-ccyev5krcnjabjkd24eu5y.streamlit.app/)
- **FastAPI Backend (Swagger UI)**: [https://identity-trust-api.onrender.com/docs](https://identity-trust-api.onrender.com/docs)

## Project Structure

trust_layer/ Python package
├── record.py PatientRecord data structure
├── validators.py Five validators + CrossRecordValidator
├── scoring.py Composite trust score
├── router.py Decision routing
├── audit.py Hash-chained audit log
├── hl7v2.py HL7v2 ADT message parser
├── fhir.py Generic FHIR adapter
├── abdm.py ABDM (India) adapter
├── aucore.py AU Core (Australia) adapter
├── nphies.py Nphies (Saudi Arabia) adapter
app.py FastAPI backend
demo.py Streamlit dashboard
database.py PostgreSQL connection & audit log
Dockerfile Container configuration
docker-compose.yml Full-stack local deployment
requirements.txt Python dependencies
examples/ Sample HL7 and FHIR records

## Installation

pip install -r requirements.txt

## Running Locally

1.  Start the FastAPI backend:
    ```bash
    uvicorn app:app --reload --host 0.0.0.0 --port 8000
    ```
2.  Start the Streamlit dashboard:
    ```bash
    streamlit run demo.py
    ```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check and configuration |
| `/metrics` | GET | Prometheus metrics |
| `/assess` | POST | Assess a single patient record (JSON) |
| `/assess-hl7` | POST | Assess an HL7 v2 ADT message |
| `/assess-batch` | POST | Assess a batch of records (CSV/JSON) |
| `/reset` | POST | Reset the in-memory state |

## Supported Input Formats

- HL7 FHIR Patient resources
- HL7 v2 ADT messages (PID segment)
- ABDM (India) FHIR profiles
- AU Core (Australia) FHIR profiles
- Nphies (Saudi Arabia) FHIR profiles

## Paper & Recognition

This project is based on the research paper:

> **Decoupling Record Trust from Record Linkage: A Dual-Stage Architecture for Hyper-Diverse Health Information Exchanges**
> 
> Published as a preprint on Zenodo: [https://zenodo.org/records/22770188](https://zenodo.org/records/22770188)
> 
> Selected as a **top-15 finalist (out of 120+ submissions)** at the AIMed26 Abstract Competition.

## License

MIT

## Contact

**Hamza Shekhani** – [hamzashekhani650@gmail.com](mailto:hamzashekhani650@gmail.com)
