I am so sorry. I completely understand what you want now. You want the entire comprehensive README—with all the sections, all the tables, all the diagrams, everything—in one single Markdown block that you can copy and paste in one go. No splitting. No deleting content.

Here is the complete, one-piece README.md with every single detail included. Just click the copy button in the top right corner of this box, paste it into GitHub, and commit.

```markdown
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

## Why This Matters for the UAE

The UAE is a uniquely hyper-diverse country where patients arrive with names and identifiers transliterated from dozens of languages. The potential for identity collisions in platforms like **Malaffi** and **NABIDH** is immense. This tool is designed specifically for this environment, integrating UAE (DOH) region profiles and minimum data set checks to ensure the reliability of connected health systems.

## Architecture

```mermaid
flowchart TD
    subgraph Hospital_Network ["🏥 Hospital Network (On-Premise / Private Cloud)"]
        HIS[Hospital Interface Engine<br/>Mirth Connect / EMR]
        Docker[<b>Docker Container</b><br/>FastAPI + Trust Engine]
    end

    subgraph Managed_Cloud ["☁️ Managed Cloud Services"]
        DB[(PostgreSQL Database<br/>Neon / Persistent Audit Log)]
        UI[Streamlit Dashboard<br/>Data Quality & Compliance Team]
    end

    HIS -->|"HL7 v2 ADT / CSV Batch"| Docker
    Docker -->|"Scores & Routes"| DB
    DB -->|"Reads Audit Trail"| UI
    UI -.->|"Sends Test Messages"| Docker

    classDef hospital fill:#f0f4f8,stroke:#4a5568,stroke-width:2px,color:#2d3748
    classDef docker fill:#e6fffa,stroke:#319795,stroke-width:2px,color:#234e52
    classDef database fill:#fffaf0,stroke:#dd6b20,stroke-width:2px,color:#7b341e
    classDef dashboard fill:#ebf4ff,stroke:#3182ce,stroke-width:2px,color:#2a4365

    class HIS hospital
    class Docker docker
    class DB database
    class UI dashboard
```

· Hospital IT sends HL7 v2 ADT messages via MLLP or SFTP batches to the local Docker container.
· FastAPI Backend parses the message and calls the trust engine.
· Trust Engine scores the record across five dimensions and routes it.
· PostgreSQL stores every decision in a persistent, audit-ready database.
· Streamlit Dashboard provides a live view of the audit trail and flagged records.

📂 Project Structure

```text
identity-trust-assessment/
├── trust_layer/                    # Core trust assessment engine (Python package)
│   ├── __init__.py
│   ├── record.py                   # PatientRecord data structure
│   ├── validators.py               # Five dimension validators + CrossRecord
│   ├── scoring.py                  # Composite trust score calculation
│   ├── router.py                   # Decision routing logic (Auto-Link, Flag, Quarantine)
│   ├── audit.py                    # Tamper-evident audit log logic
│   └── adapters/                   # Data format parsers & regional profiles
│       ├── hl7v2.py                # HL7 v2 ADT message parser
│       ├── fhir.py                 # Generic FHIR adapter
│       ├── abdm.py                 # ABDM (India) adapter
│       ├── aucore.py               # AU Core (Australia) adapter
│       └── nphies.py               # Nphies (Saudi Arabia) adapter
├── app.py                          # FastAPI backend (API endpoints)
├── demo.py                         # Streamlit dashboard (Frontend UI)
├── database.py                     # PostgreSQL connection & audit log persistence
├── Dockerfile                      # Container definition for on-premise deployment
├── docker-compose.yml              # Multi-container orchestration for local development
├── requirements.txt                # Python dependencies
├── .env.example                    # Template for environment variables (DB URL, API Key)
├── README.md                       # Project documentation
└── examples/                       # Sample HL7, FHIR, and CSV files for testing
```

Component Overview

Component Directory/File Description
Core Engine trust_layer/ The independent, modular trust assessment logic. Can be imported into any Python backend.
API Backend app.py The FastAPI service that exposes the trust engine to the hospital's interface engine.
Dashboard demo.py The Streamlit UI used by the Health Information Management team for monitoring and sign-off.
Database database.py Handles connections to the Neon PostgreSQL database and maintains the permanent audit log.
Deployment Dockerfile & docker-compose.yml Enables the entire system to be built and run on a hospital's private on-premise servers.
Adapters trust_layer/adapters/ Pluggable parsers that normalize HL7 v2, FHIR, and regional profiles (ABDM, Nphies) into a single format.

🖥️ Dashboard Walkthrough

The Streamlit dashboard provides a complete operational view for hospital data quality teams:

· Dashboard: Live KPIs (Total Records, Auto-Linked, Flagged, Quarantined) and decision breakdown charts.
· HL7 Stream: Real-time simulation of incoming HL7 v2 ADT messages, demonstrating the routing logic.
· Batch Upload: Upload a CSV of patient records for retrospective analysis and pre-pilot proof of concept.
· Summary Report: A printable, one-page report for data quality review and clinical sign-off.
· Flagged Records: Detailed view of every record that requires manual review, with the specific trust dimension that failed.
· Coding Coherence, DRG Readiness, Data Governance: Rule-based checks for ICD validity, IR-DRG grouping, and NABIDH/Malaffi minimum data set completeness.
· Audit Trail: A permanent, tamper-evident log of every decision made by the system.

📊 Results

· Collision rejection: 96.0% Gulf, 92.6% Australia (vs. 53.4% / 30.7% for Fellegi-Sunter)
· Non-overlapping 95% confidence intervals in both contexts
· Fairness audit (n=2,000, six nationality groups): chi-squared = 7.25, p = 0.203 (no significant bias)
· Fellegi-Sunter comparator externally validated on Febrl1 benchmark (F1 = 0.862)

🚀 Deployment Options

1. Live Demo (For Portfolio & Recruiters)

· Streamlit Dashboard: https://identity-trust-assessment-ccyev5krcnjabjkd24eu5y.streamlit.app/
· FastAPI Backend (Swagger UI): https://identity-trust-api.onrender.com/docs

2. On-Premise Deployment (For Hospital IT Teams)

The system is fully containerized and can be deployed inside a hospital's private network using Docker.

```bash
# Build the container
docker build -t trust-layer:latest .

# Run the container (ensure you pass your database URL)
docker run -p 8000:8000 \
  -e TRUST_LAYER_API_KEY=your-secret-key \
  -e REGION_PROFILE="UAE (DOH)" \
  -e DATABASE_URL="postgresql://user:password@host/dbname?sslmode=require" \
  trust-layer:latest
```

📋 API Endpoints

Endpoint Method Description
/health GET Health check and configuration
/metrics GET Prometheus metrics
/assess POST Assess a single patient record (JSON)
/assess-hl7 POST Assess an HL7 v2 ADT message
/assess-batch POST Assess a batch of records (CSV/JSON)
/reset POST Reset the in-memory state

📥 Supported Input Formats

· HL7 FHIR Patient resources
· HL7 v2 ADT messages (PID segment)
· ABDM (India) FHIR profiles
· AU Core (Australia) FHIR profiles
· Nphies (Saudi Arabia) FHIR profiles

⚠️ Limitations & Future Roadmap

Current Limitations:

· The prototype is validated on synthetic data only. A real-world pilot would require re-deriving thresholds using the methodology from the published paper.
· The demo thresholds (Trust-Hard variant) differ from the paper's validated thresholds (Trust-Soft variant) to generate realistic flag rates for demonstration purposes.

Future Roadmap:

□ Integration with real-world UAE data (Malaffi/NABIDH sandbox).
□ Migration to FHIR-native parsing (currently HL7 v2 focused).
□ Single Sign-On (SSO) integration for hospital Active Directory.
□ Arabic language localization for the Streamlit dashboard.
□ Formal publication of the expanded framework in a peer-reviewed journal.

📄 Paper & Recognition

This project is based on the research paper:

Decoupling Record Trust from Record Linkage: A Dual-Stage Architecture for Hyper-Diverse Health Information Exchanges

Published as a preprint on Zenodo: https://zenodo.org/records/22770188

Selected as a top-15 finalist (out of 120+ submissions) at the AIMed26 Abstract Competition.

📜 License

MIT

📬 Contact

Hamza Shekhani – hamzashekhani650@gmail.com

```

This is the full, complete README in one single block. No missing sections. Copy and paste it. You're done.
```
