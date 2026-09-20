from trust_layer.record import PatientRecord


def from_aucore_patient(fhir_json):
    """
    Convert an AU Core FHIR Patient resource (Australia) into a PatientRecord.
    AU Core uses IHI (16-digit, prefix 800360) and Medicare number.
    """
    record = PatientRecord()

    # Name
    names = fhir_json.get("name", [])
    if names:
        primary = names[0]
        given = primary.get("given", [])
        record.given_name = given[0] if given else ""
        record.family_name = primary.get("family", "")

    # DOB
    record.date_of_birth = fhir_json.get("birthDate", "")

    # Identifiers
    identifiers = fhir_json.get("identifier", [])
    for ident in identifiers:
        system = ident.get("system", "").lower()
        value = ident.get("value", "")
        if "ihi" in system or "healthcare-identifier" in system:
            record.emirates_id = value  # primary identifier slot
        elif "medicare" in system:
            record.passport_number = value  # fallback identifier slot
        elif "mrn" in system or "local" in system:
            record.local_mrn = value

    # Nationality (extension)
    extensions = fhir_json.get("extension", [])
    for ext in extensions:
        url = ext.get("url", "").lower()
        if "nationality" in url or "country-of-birth" in url:
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