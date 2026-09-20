from trust_layer.record import PatientRecord


def from_fhir_patient(fhir_json):
    """
    Convert a FHIR Patient resource (dict) into a PatientRecord.
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

    # Identifiers - loop through and assign based on system URI
    identifiers = fhir_json.get("identifier", [])
    for ident in identifiers:
        system = ident.get("system", "").lower()
        value = ident.get("value", "")
        if "emirates" in system or "ihi" in system:
            record.emirates_id = value
        elif "passport" in system:
            record.passport_number = value
        elif "medicare" in system:
            record.passport_number = value
        elif "mrn" in system or "local" in system:
            record.local_mrn = value

    # Nationality (FHIR uses an extension in most profiles)
    extensions = fhir_json.get("extension", [])
    for ext in extensions:
        url = ext.get("url", "").lower()
        if "nationality" in url:
            record.nationality = ext.get("valueString", "")
            break

    # Source facility (from meta.tag or managingOrganization)
    meta = fhir_json.get("meta", {})
    tags = meta.get("tag", [])
    for tag in tags:
        if "facility" in tag.get("system", "").lower():
            record.source_facility = tag.get("display", "")
            break

    return record