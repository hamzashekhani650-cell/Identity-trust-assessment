'''
HL7 v2.x ADT message → canonical record bridge.

Takes a raw HL7 v2 message (as a string) and returns a dict with the same
canonical field names the CSV pipeline uses. This is the integration point
between a hospital's interface engine and the trust assessment engine.

Supports the common ADT triggers:
  A01 — Admit
  A03 — Discharge
  A04 — Register (outpatient)
  A08 — Update

Extracts:
  MSH-3  → source_facility (sending application)
  MSH-4  → source_facility (sending facility, preferred)
  MSH-9  → message_type
  MSH-10 → message_control_id
  PID-3  → emirates_id (first identifier in the list)
  PID-5  → given_name + family_name
  PID-7  → date_of_birth (HL7 format YYYYMMDD → ISO)
  PID-8  → gender (M/F/O/U)
  PV1-2  → encounter_type (I=inpatient, O=outpatient, E=emergency)
  PV1-44 → admission_date
  PV1-45 → discharge_date
  EVN-2  → event_date (fallback for registration_date)

The function never raises on a missing field — it fills the canonical
field with an empty string. The trust engine treats empty strings the
same way it treats blank CSV cells.
'''
import re


FIELD_SEP = '|'
COMPONENT_SEP = '^'
REPETITION_SEP = '~'
ESCAPE_CHAR = '\\'
SUBCOMPONENT_SEP = '&'


def _split_segments(msg):
    '''Split an HL7 message into segments on \r, \n, or \r\n.'''
    raw = msg.replace('\r\n', '\r').replace('\n', '\r')
    return [s.strip() for s in raw.split('\r') if s.strip()]


def _fields(segment):
    return segment.split(FIELD_SEP)


def _component(field, index=0):
    '''Extract a component from a field, e.g. PID-5.1.'''
    if not field:
        return ''
    parts = field.split(COMPONENT_SEP)
    if index < len(parts):
        return parts[index].strip()
    return ''


def _hl7_date_to_iso(hl7_date):
    '''Convert YYYYMMDD or YYYYMMDDHHMMSS to YYYY-MM-DD.'''
    if not hl7_date:
        return ''
    s = str(hl7_date).strip()
    if len(s) >= 8 and s[:8].isdigit():
        return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    return ''


def _extract_name(pid_5):
    '''
    PID-5 Patient Name. Format: family^given^middle^suffix^prefix
    In practice, UAE systems often send given^family instead.
    We take the first two components: first is family, second is given.
    If only one component is present, treat it as family name.
    '''
    if not pid_5:
        return '', ''
    parts = pid_5.split(COMPONENT_SEP)
    if len(parts) >= 2:
        family = parts[0].strip()
        given = parts[1].strip()
        return given, family
    if len(parts) == 1:
        return parts[0].strip(), ''
    return '', ''


def _extract_first_identifier(pid_3):
    '''
    PID-3 Patient Identifier List. Format: ID^^^authority^type~ID2^^^...
    We take the first identifier in the first repetition.
    '''
    if not pid_3:
        return ''
    first_rep = pid_3.split(REPETITION_SEP)[0]
    return _component(first_rep, 0)


def _extract_segment(segments, seg_type):
    for seg in segments:
        if seg.startswith(seg_type + FIELD_SEP) or seg == seg_type:
            return seg
    return None


def parse_hl7_message(msg):
    '''
    Parse an HL7 v2 ADT message and return a canonical record dict.
    Never raises on missing fields — fills them with empty strings.
    '''
    record = {
        'emirates_id': '',
        'given_name': '',
        'family_name': '',
        'gender': '',
        'date_of_birth': '',
        'nationality': '',
        'source_facility': '',
        'registration_date': '',
        'canonical_id': '',
        'episode_id': '',
        'encounter_type': '',
        'admission_date': '',
        'discharge_date': '',
        'diagnosis_code': '',
        'procedure_code': '',
        'secondary_diagnoses': '',
        'discharge_summary': '',
        'drg_code': '',
        'laterality': '',
        'consent_status': '',
        'consent_date': '',
        'consent_scope': '',
        'preauth_reference': '',
        'preauth_valid_until': '',
        'triage_level': '',
        'total_cost_aed': '',
        '_parse_errors': [],
    }

    segments = _split_segments(msg)
    if not segments:
        record['_parse_errors'].append('empty message')
        return record

    if not segments[0].startswith('MSH'):
        record['_parse_errors'].append('first segment is not MSH')

    # MSH
    msh = _extract_segment(segments, 'MSH')
    if msh:
        fields = _fields(msh)
        # fields[0] = 'MSH', fields[1] = encoding chars, fields[2] = sending app
        if len(fields) >= 6:
            record['source_facility'] = fields[5].strip() or (fields[3].strip() if len(fields) >= 4 else '')
        if len(fields) >= 10:
            record['canonical_id'] = fields[9].strip()
        if len(fields) >= 9:
            msg_type = fields[8]
            record['episode_id'] = ''
    else:
        record['_parse_errors'].append('MSH segment missing')

    # EVN
    evn = _extract_segment(segments, 'EVN')
    if evn:
        fields = _fields(evn)
        if len(fields) >= 3:
            record['registration_date'] = _hl7_date_to_iso(fields[2])

    # PID
    pid = _extract_segment(segments, 'PID')
    if pid:
        fields = _fields(pid)
        if len(fields) >= 4:
            record['emirates_id'] = _extract_first_identifier(fields[3])
        if len(fields) >= 6:
            given, family = _extract_name(fields[5])
            record['given_name'] = given
            record['family_name'] = family
        if len(fields) >= 8:
            record['date_of_birth'] = _hl7_date_to_iso(fields[7])
        if len(fields) >= 9:
            g = fields[8].strip().upper()
            record['gender'] = g if g in ('M', 'F', 'O', 'U') else ''
        if len(fields) >= 11:
            record['nationality'] = _component(fields[10], 0)
    else:
        record['_parse_errors'].append('PID segment missing')

    # PV1
    pv1 = _extract_segment(segments, 'PV1')
    if pv1:
        fields = _fields(pv1)
        if len(fields) >= 3:
            pt_class = fields[2].strip().upper()
            # HL7 PV1-2 patient class: I=inpatient, O=outpatient, E=emergency
            if pt_class == 'I':
                record['encounter_type'] = '3'  # canonical inpatient marker
            elif pt_class == 'O':
                record['encounter_type'] = '1'  # canonical outpatient marker
            elif pt_class == 'E':
                record['encounter_type'] = '2'  # emergency
            else:
                record['encounter_type'] = pt_class
        if len(fields) >= 45:
            record['admission_date'] = _hl7_date_to_iso(fields[44])
        if len(fields) >= 46:
            record['discharge_date'] = _hl7_date_to_iso(fields[45])
        if len(fields) >= 20 and not record['episode_id']:
            record['episode_id'] = fields[19].strip()

    return record


def validate_hl7_structure(msg):
    '''
    Lightweight structural check. Returns (is_valid, list_of_issues).
    Complements parse_hl7_message — this is a sanity check, not a full
    conformance test.
    '''
    issues = []
    segments = _split_segments(msg)
    if not segments:
        return False, ['empty message']
    if not segments[0].startswith('MSH'):
        issues.append('first segment is not MSH')
    msh = _extract_segment(segments, 'MSH')
    if msh:
        fields = _fields(msh)
        if len(fields) < 12:
            issues.append(f'MSH has only {len(fields)} fields (expected >= 12)')
        msg_type = fields[8] if len(fields) >= 9 else ''
        if not msg_type:
            issues.append('MSH-9 message type missing')
        if len(fields) < 10 or not fields[9].strip():
            issues.append('MSH-10 message control ID missing')
    if not _extract_segment(segments, 'PID'):
        issues.append('PID segment missing')
    return len(issues) == 0, issues
