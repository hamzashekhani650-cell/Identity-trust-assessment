import re
from datetime import datetime
from trust_layer.record import PatientRecord


def validate_completeness(record: PatientRecord) -> float:
    has_emirates_id = record.emirates_id is not None and record.emirates_id.strip() != ""
    has_passport = record.passport_number is not None and record.passport_number.strip() != ""
    has_name = (record.given_name.strip() != "" and record.family_name.strip() != "")
    has_dob = record.date_of_birth.strip() != ""

    if not has_name or not has_dob:
        return 0.0
    if has_emirates_id:
        return 1.0
    elif has_passport:
        return 0.7
    else:
        return 0.0


def validate_temporal(record: PatientRecord) -> float:
    score = 1.0

    try:
        dob = datetime.strptime(record.date_of_birth, "%Y-%m-%d")
    except (ValueError, TypeError):
        return 0.0

    today = datetime.today()
    if dob > today:
        return 0.0

    age_years = (today - dob).days / 365.25
    if age_years < 0 or age_years > 130:
        return 0.0

    try:
        reg = datetime.strptime(record.registration_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        score -= 0.3

    if record.registration_date:
        try:
            reg = datetime.strptime(record.registration_date, "%Y-%m-%d")
            if reg < dob:
                score -= 0.5
        except (ValueError, TypeError):
            pass

    return max(0.0, min(1.0, score))


def validate_identity_consistency(record: PatientRecord) -> float:
    score = 1.0
    checks_performed = 0

    if record.emirates_id:
        checks_performed += 1
        emirates_pattern = r"^784-\d{4}-\d{7}-\d$"
        if not re.match(emirates_pattern, record.emirates_id):
            score -= 0.5

    if record.passport_number:
        checks_performed += 1
        passport_pattern = r"^[A-Z0-9]{6,9}$"
        if not re.match(passport_pattern, record.passport_number):
            score -= 0.3

    if record.given_name and record.family_name:
        checks_performed += 1
        if record.given_name.strip().lower() == record.family_name.strip().lower():
            score -= 0.4

    if record.nationality:
        checks_performed += 1
        if len(record.nationality.strip()) < 2:
            score -= 0.3

    if checks_performed == 0:
        return 0.5

    return max(0.0, min(1.0, score))


DOH_PROVIDER_REGISTRY = {
    "Cleveland Clinic Abu Dhabi": "high",
    "Sheikh Khalifa Medical City": "high",
    "SSMC": "high",
    "Al Noor Hospital": "medium",
    "Mediclinic Abu Dhabi": "medium",
    "NMC Royal Hospital": "medium",
    "Community Clinic Al Ain": "low",
    "Rural Health Centre Liwa": "low",
}

TIER_SCORES = {"high": 1.0, "medium": 0.7, "low": 0.4}


def validate_provenance(record: PatientRecord) -> float:
    if not record.source_facility or record.source_facility.strip() == "":
        return 0.0

    facility = record.source_facility.strip()
    if facility not in DOH_PROVIDER_REGISTRY:
        return 0.3

    tier = DOH_PROVIDER_REGISTRY[facility]
    return TIER_SCORES[tier]


class CrossRecordValidator:

    def __init__(self):
        self.identifier_index = {}
        self.name_dob_index = {}

    def add_record(self, record: PatientRecord):
        if record.emirates_id:
            self.identifier_index.setdefault(record.emirates_id, set()).add(record.canonical_id)

        key = (
            record.given_name.strip().lower(),
            record.family_name.strip().lower(),
            record.date_of_birth,
        )
        self.name_dob_index.setdefault(key, set()).add(record.canonical_id)

    def validate(self, record: PatientRecord) -> float:
        if record.emirates_id and record.emirates_id in self.identifier_index:
            owners = self.identifier_index[record.emirates_id]
            if record.canonical_id not in owners:
                return 0.0

        key = (
            record.given_name.strip().lower(),
            record.family_name.strip().lower(),
            record.date_of_birth,
        )
        if key in self.name_dob_index:
            owners = self.name_dob_index[key]
            if record.canonical_id not in owners:
                return 0.5

        return 1.0