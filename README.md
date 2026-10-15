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

    %% Data Flow
    HIS -->|"HL7 v2 ADT / CSV Batch"| Docker
    Docker -->|"Scores & Routes"| DB
    DB -->|"Reads Audit Trail"| UI
    UI -.->|"Sends Test Messages"| Docker

    %% Styling
    classDef hospital fill:#f0f4f8,stroke:#4a5568,stroke-width:2px,color:#2d3748
    classDef docker fill:#e6fffa,stroke:#319795,stroke-width:2px,color:#234e52
    classDef database fill:#fffaf0,stroke:#dd6b20,stroke-width:2px,color:#7b341e
    classDef dashboard fill:#ebf4ff,stroke:#3182ce,stroke-width:2px,color:#2a4365

    class HIS hospital
    class Docker docker
    class DB database
    class UI dashboard
