# Integration with Existing Interface Engines

The trust layer does not replace your existing interface engine (Mirth Connect, Rhapsody, Cloverleaf, or a vendor EMR). It sits **downstream** of the engine and **upstream** of the MPI or matcher.

The HL7v2 parser in this project handles the PID segment of standard ADT messages. This is the primary integration format used by TrakCare and similar hospital information systems. The parser has been tested against synthetic HL7v2 ADT messages; validation against a live or de-identified TrakCare export is pending Phase 3.

## Architecture

    Source systems
         |
         v
    [Interface engine]  -- Mirth, Rhapsody, Cloverleaf
         |
         v  (normalized HL7v2 or FHIR)
    [Trust layer]       -- this project
         |
         v
    [Existing matcher]  -- Fellegi-Sunter, NextGate, Verato, or custom
         |
         v
    Master Patient Index

## Why this positioning

Hospitals already run an interface engine. Asking them to replace it is a non-starter.
The trust layer consumes what the engine already produces:

- HL7v2 ADT messages (PID segments)
- HL7 FHIR Patient resources
- Any other format the engine normalizes

## Deployment modes

1. **Shadow mode** -- the trust layer scores incoming records and logs decisions without affecting production linkage.
2. **Gate mode** -- the trust layer intercepts records before the matcher. Records routed to quarantine do not reach the matcher until human review.
3. **Audit mode** -- the trust layer scores records in parallel with the existing matcher and flags disagreements for review.

## What it does not require

- No replacement of the existing interface engine
- No changes to source EMR systems
- No new identity infrastructure
- No patient-facing changes

## What it requires

- Read access to the normalized output stream from the interface engine
- A writable audit log location
- A quarantine review workflow (existing quality team can be reused)
