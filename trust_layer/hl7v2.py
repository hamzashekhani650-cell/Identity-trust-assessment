from trust_layer.record import PatientRecord


def _parse_hl7_pid(segment):
    """
    Parse an HL7v2 PID segment into a dict of fields.
    PID-3: Patient Identifier List
    PID-5: Patient Name
    PID-7: Date/Time of Birth
    PID-8: Administrative Sex
    PID-11: Patient Address
    """
    fields = segment.split("|")
    return {
        "identifier_list": fields[3] if len(fields) > 3 else "",
        "name": fields[5] if len(fields) > 5 else "",
        "dob": fields[7] if len(fields) > 7 else "",
        "sex": fields[8] if len(fields) > 8 else "",
        "address": fields[11] if len(fields) > 11 else "",
    }


def _parse_name(name_field):
    """
    HL7v2 name: family^given^middle^suffix^prefix
    """
    parts = name_field.split("^")
    family = parts[0] if len(parts) > 0 else ""
    given = parts[1] if len(parts) > 1 else ""
    return given.strip(), family.strip()


def _parse_dob(dob_field):
    """
    HL7v2 DOB: YYYYMMDD or YYYYMMDDHHMMSS.
    """
    if not dob_field:
        return ""
    dob_str = dob_field.split("^")[0].strip()
    if len(dob_str) >= 8 and dob_str[:8].isdigit():
        return f"{dob_str[:4]}-{dob_str[4:6]}-{dob_str[6:8]}"
    return ""


def _parse_identifier(id_list):
    """
    HL7v2 identifier list: id^^^system^type~id2^^^system2^type2
    Returns the first identifier found.
    """
    if not id_list:
        return None
    first = id_list.split("~")[0]
    parts = first.split("^")
    return parts[0].strip() if parts else None


def from_hl7v2_message(message, canonical_id="", facility=""):
    """
    Parse an HL7v2 ADT message (A01/A04/A08) into a PatientRecord.
    Extracts the PID segment and maps fields into the canonical schema.
    """
    record = PatientRecord(canonical_id=canonical_id)

    for segment in message.split("\r"):
        if segment.startswith("PID"):
            parsed = _parse_hl7_pid(segment)

            record.emirates_id = _parse_identifier(parsed["identifier_list"])
            record.given_name, record.family_name = _parse_name(parsed["name"])
            record.date_of_birth = _parse_dob(parsed["dob"])
            record.nationality = ""

            if facility:
                record.source_facility = facility
            break

    return record
    