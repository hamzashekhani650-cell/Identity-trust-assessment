# Contributing

## Running locally

    pip install -r requirements.txt
    python -m pytest test_validators.py/test_validators.py -v
    python cli/assess.py --given-name "Ahmed" --family-name "Al-Mansoori" --dob "1985-03-15" --facility "Cleveland Clinic Abu Dhabi"

## Testing

Run the full test suite before submitting changes:

    python -m pytest test_validators.py/test_validators.py -v

## Adding a new FHIR adapter

1. Create a new file in trust_layer/ (e.g., myhie.py)
2. Implement a from_myhie_patient(fhir_json) function that returns a PatientRecord
3. Add a test in test_validators.py
4. Update the README's supported formats list

## Reporting issues

Open a GitHub issue with:
- The input record that triggered the problem
- The expected output
- The actual output
