# Changelog

All notable changes to this project are documented here.

## [0.2.0] - 2026-09-18

### Added
- HL7v2 ADT message parser (PID segment extraction)
- Four FHIR adapters: generic FHIR, ABDM (India), AU Core (Australia), Nphies (Saudi Arabia)
- Bayesian-risk thresholding module (`costs.py`) replacing hard-coded thresholds
- Conjunctive robust aggregation (`robust_scoring.py`) resistant to single-dimension spoofing
- Tamper-evident hash-chained audit log
- Property-based tests with Hypothesis (400 random inputs)
- Integration test covering the full pipeline (record → validators → scoring → router)
- Fairness audit across six nationality groups (χ² = 7.25, p = 0.203, no significant bias)
- External validation of Fellegi-Sunter on Febrl1 benchmark (F1 = 0.862)
- Collision-injection validation on the Febrl population
- Sample records for testing
- MIT License

### Changed
- Replaced Flask-facing sample model with a Streamlit demo UI
- Updated architecture to separate concerns: `trust_layer/` package + adapters + tools

## [0.1.0] - 2026-09-15

### Added
- Initial five-dimension trust framework
- Validators: completeness, temporal, identity, provenance, cross-record
- Composite scoring and decision router
- Synthetic population generators (Gulf and Australian)
- Baseline evaluation: exact-match, Fellegi-Sunter, Trust-Soft, Trust-Hard, Hybrid v3/v4
- Bootstrap confidence intervals, Monte Carlo stability, adversarial robustness testing
