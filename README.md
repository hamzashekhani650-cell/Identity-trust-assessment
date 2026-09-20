# Identity Trust Assessment

A five-dimension trust assessment framework for patient identity resolution in hyper-diverse health information exchanges.

## The problem

Health information exchanges link patient records across hospitals, clinics, and labs. When two different patients share the same identifier (Emirates ID, MRN, insurance number), pairwise matchers link them incorrectly. One patient's medical history attaches to another's.

## The framework

Five dimensions evaluated before any linkage decision:

1. **Completeness** -- are required identity fields present?
2. **Temporal Validity** -- do the dates make sense?
3. **Identity Consistency** -- do identifiers agree with demographics?
4. **Provenance** -- is the source facility trusted?
5. **Cross-Record Consistency** -- does this record collide with an existing identity?

The composite score routes each record to auto-link, flag-for-review, or quarantine.

## Results

- Collision rejection: **96.0%** Gulf, **92.6%** Australia (vs. 53.4% / 30.7% for Fellegi-Sunter)
- Non-overlapping 95% confidence intervals in both contexts
- Fairness audit (n=2,000, six nationality groups): chi-squared = 7.25, p = 0.203 (no significant bias)
- Fellegi-Sunter comparator externally validated on Febrl1 benchmark (F1 = 0.862)

## Structure

    trust_layer/          Python package
      record.py           PatientRecord data structure
      validators.py       Five validators + CrossRecordValidator
      scoring.py          Composite trust score
      robust_scoring.py   Conjunctive aggregation (adversary-resistant)
      router.py           Decision routing
      costs.py            Bayes-risk thresholding
      audit.py            Hash-chained audit log
      fhir.py             Generic FHIR adapter
      abdm.py             ABDM (India) adapter
      aucore.py           AU Core (Australia) adapter
      nphies.py           Nphies (Saudi Arabia) adapter
      hl7v2.py            HL7v2 ADT message parser

    cli/assess.py         Command-line interface
    generator/generate.py Standalone synthetic population generator
    demo.py               Streamlit web demo
    app.py                Flask API
    Dockerfile            Container configuration
    examples/             Sample FHIR records

## Install

    pip install flask pytest recordlinkage rapidfuzz hypothesis streamlit

## Run the tests

    python -m pytest test_validators.py/test_validators.py -v

## Quick start (CLI)

    python cli/assess.py --given-name "Ahmed" --family-name "Al-Mansoori" --dob "1985-03-15" --facility "Cleveland Clinic Abu Dhabi"

## Supported input formats

- HL7 FHIR Patient resources
- HL7v2 ADT messages (PID segment)
- ABDM (India) FHIR profiles
- AU Core (Australia) FHIR profiles
- Nphies (Saudi Arabia) FHIR profiles

## Paper

Decoupling Record Trust from Record Linkage: A Dual-Stage Architecture for Hyper-Diverse Health Information Exchanges (preprint forthcoming)

## License

MIT

## Contact

Hamza Shekhani -- hamzashekhani650@gmail.com