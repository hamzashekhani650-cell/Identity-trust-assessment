'''
HL7 v2.x message structure validation for UAE HIE submissions.
Standalone module. Validates the message envelope — MSH header, required
segments, mandatory field presence, encoding characters, message type.

Does NOT replace trust_layer/hl7v2.py — that extracts clinical fields.
This module checks whether the message would be accepted or rejected by
an HIE interface engine (NABIDH, Malaffi).
'''
import re


VALID_ENCODING_CHARS_DEFAULT = '^~\\&'

VALID_VERSION_IDS = {'2.3', '2.3.1', '2.4', '2.5', '2.5.1', '2.6', '2.7', '2.8'}
VALID_PROCESSING_IDS = {'P', 'T', 'D'}

SEGMENT_MIN_FIELDS = {
    'MSH': 12,
    'PID': 11,
    'EVN': 2,
    'PV1': 3,
    'OBR': 4,
    'OBX': 5,
}

REQUIRED_SEGMENTS_BY_TYPE = {
    'ADT^A01': ['MSH', 'EVN', 'PID', 'PV1'],
    'ADT^A03': ['MSH', 'EVN', 'PID', 'PV1'],
    'ADT^A04': ['MSH', 'EVN', 'PID', 'PV1'],
    'ADT^A08': ['MSH', 'EVN', 'PID', 'PV1'],
    'ORU^R01': ['MSH', 'PID', 'OBR', 'OBX'],
}


def _split_segments(msg):
    return [s for s in re.split(r'[\r\n]+', msg.strip()) if s.strip()]


def _get_message_type(msh):
    fields = msh.split('|')
    if len(fields) < 9:
        return None
    parts = fields[8].split('^')
    return f'{parts[0]}^{parts[1]}' if len(parts) >= 2 else fields[8]


def _validate_msh(msh):
    issues = []
    fields = msh.split('|')

    if len(fields) < SEGMENT_MIN_FIELDS['MSH']:
        issues.append(f'MSH: only {len(fields)} fields (expected at least {SEGMENT_MIN_FIELDS["MSH"]})')

    if len(fields) >= 2 and (not fields[1] or len(fields[1]) < 4):
        issues.append('MSH-2: encoding characters missing or malformed')

    msg_type = _get_message_type(msh)
    if not msg_type:
        issues.append('MSH-9: message type missing or unparseable')

    if len(fields) < 10 or not fields[9].strip():
        issues.append('MSH-10: message control ID missing')

    if len(fields) >= 11:
        proc = fields[10].strip().upper()
        if proc and proc not in VALID_PROCESSING_IDS:
            issues.append(f'MSH-11: processing ID {proc!r} not recognised')

    if len(fields) >= 12:
        ver = fields[11].strip()
        if ver and ver not in VALID_VERSION_IDS:
            issues.append(f'MSH-12: version ID {ver!r} not recognised')

    return issues, msg_type


def _validate_pid(pid):
    issues = []
    fields = pid.split('|')

    if len(fields) < SEGMENT_MIN_FIELDS['PID']:
        issues.append(f'PID: only {len(fields)} fields (expected at least {SEGMENT_MIN_FIELDS["PID"]})')

    if len(fields) < 4 or not fields[3].strip():
        issues.append('PID-3: patient identifier missing')
    if len(fields) < 6 or not fields[5].strip():
        issues.append('PID-5: patient name missing')
    if len(fields) < 8 or not fields[7].strip():
        issues.append('PID-7: date of birth missing')
    if len(fields) < 9 or not fields[8].strip():
        issues.append('PID-8: administrative sex missing')

    return issues


def validate_hl7_message(msg):
    segments = _split_segments(msg)
    if not segments:
        return {'structure_score': 0.0, 'issues': ['empty message'],
                'message_type': None, 'segments_present': []}

    issues = []
    if not segments[0].startswith('MSH'):
        issues.append('first segment is not MSH')

    seg_dict = {}
    for seg in segments:
        seg_type = seg.split('|')[0].split('^')[0].strip()
        if seg_type:
            seg_dict.setdefault(seg_type, []).append(seg)

    msg_type = None
    if 'MSH' in seg_dict:
        msh_issues, msg_type = _validate_msh(seg_dict['MSH'][0])
        issues.extend(msh_issues)
    else:
        issues.append('MSH segment missing')

    if 'PID' in seg_dict:
        issues.extend(_validate_pid(seg_dict['PID'][0]))
    else:
        issues.append('PID segment missing')

    if msg_type and msg_type in REQUIRED_SEGMENTS_BY_TYPE:
        for required in REQUIRED_SEGMENTS_BY_TYPE[msg_type]:
            if required not in seg_dict:
                issues.append(f'required segment {required} missing for {msg_type}')

    score = max(0.0, 1.0 - 0.1 * len(issues))
    return {
        'structure_score': round(score, 3),
        'issues': issues,
        'message_type': msg_type,
        'segments_present': sorted(seg_dict.keys()),
    }
