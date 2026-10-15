# Identity Trust Assessment

**A production-ready pre-submission trust gate for patient identity resolution in hyper-diverse health information exchanges.**

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://identity-trust-assessment-ccyev5krcnjabjkd24eu5y.streamlit.app/)
[![FastAPI Docs](https://img.shields.io/badge/API-Docs-009688)](https://identity-trust-api.onrender.com/docs)

---

Health information exchanges link patient records across hospitals, clinics, and labs. When two different patients share the same identifier (Emirates ID, MRN, insurance number), pairwise matchers link them incorrectly. One patient's medical history attaches to another's. This is a silent data corruption that can have severe clinical and financial consequences.

The Identity Trust Assessment framework solves this by scoring every incoming patient record **before** any linkage decision is made. It evaluates five dimensions—Completeness, Temporal Validity, Identity Consistency, Provenance, and Cross-Record Consistency—and routes each record to **Auto-Link**, **Flag-for-Review**, or **Quarantine**, with a plain-language reason for every decision.

This is particularly critical for the UAE, a hyper-diverse country where patients arrive with names and identifiers transliterated from dozens of languages. The potential for identity collisions in platforms like **Malaffi** and **NABIDH** is immense, making this tool not just helpful, but necessary for the reliability of connected health systems.

### Architecture & Data Flow

The system operates as a secure middleware layer. Hospital IT systems send HL7 v2 ADT messages or CSV batches to a local Docker container. The FastAPI backend parses these messages, calls the trust engine, and writes every decision to a persistent PostgreSQL database. A separate Streamlit dashboard then reads from this database to provide a live view of the audit trail and flagged records.

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
