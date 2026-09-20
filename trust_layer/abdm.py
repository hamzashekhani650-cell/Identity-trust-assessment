from trust_layer.record import PatientRecord


def from_abdm_patient(fhir_json):
    """
    Convert an ABDM FHIR Patient resource (India) into a PatientRecord.
    ABDM uses ABHA number (14 digits, format XX-XXXX-XXXX-XXXX) and
    Health ID as the primary identifiers.
    """
    record = PatientRecord()

    # Name
    names = fhir_json.get("name", [])
    if names:
        primary = names[0]
        given = primary.get("given", [])
        record.given_name = given[0] if given else ""
        record.family_name = primary.get("family", "")

    # Date of birth
    record.date_of_birth = fhir_json.get("birthDate", "")

    # Identifiers
    identifiers = fhir_json.get("identifier", [])
    for ident in identifiers:
        system = ident.get("system", "").lower()
        value = ident.get("value", "")
        if "abha" in system or "healthid" in system:
            record.emirates_id = value  # reuse the primary identifier slot
        elif "mrn" in system or "local" in system:
            record.local_mrn = value
        elif "passport" in system:
            record.passport_number = value

    # Nationality
    extensions = fhir_json.get("extension", [])
    for ext in extensions:
        url = ext.get("url", "").lower()
        if "nationality" in url:
            record.nationality = ext.get("valueString", "")
            break

    # Source facility
    meta = fhir_json.get("meta", {})
    tags = meta.get("tag", [])
    for tag in tags:
        if "facility" in tag.get("system", "").lower():
            record.source_facility = tag.get("display", "")
            break

    return record