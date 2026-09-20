from trust_layer.record import PatientRecord


def from_nphies_patient(fhir_json):
    """
    Convert a Nphies FHIR Patient resource (Saudi Arabia) into a PatientRecord.
    Nphies uses National ID / Iqama (10 digits) and an insurance member ID.
    """
    record = PatientRecord()

    names = fhir_json.get("name", [])
    if names:
        primary = names[0]
        given = primary.get("given", [])
        record.given_name = given[0] if given else ""
        record.family_name = primary.get("family", "")

    record.date_of_birth = fhir_json.get("birthDate", "")

    identifiers = fhir_json.get("identifier", [])
    for ident in identifiers:
        system = ident.get("system", "").lower()
        value = ident.get("value", "")
        if "national-id" in system or "iqama" in system:
            record.emirates_id = value
        elif "insurance" in system or "member" in system:
            record.passport_number = value
        elif "mrn" in system or "local" in system:
            record.local_mrn = value

    extensions = fhir_json.get("extension", [])
    for ext in extensions:
        url = ext.get("url", "").lower()
        if "nationality" in url:
            record.nationality = ext.get("valueString", "")
            break

    meta = fhir_json.get("meta", {})
    tags = meta.get("tag", [])
    for tag in tags:
        if "facility" in tag.get("system", "").lower():
            record.source_facility = tag.get("display", "")
            break

    return record