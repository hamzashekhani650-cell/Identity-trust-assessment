'''
Smart schema mapper for hospital CSV exports.

Handles inconsistent column naming from real hospital systems:
  - TrakCare (InterSystems) — the UAE hospital standard
  - Epic, Cerner — common international EMRs
  - HL7 FHIR Patient resources (flattened)
  - Generic exports with arbitrary naming

Three strategies, applied in order:
  1. Exact normalized match against synonym dictionary
  2. Fuzzy string match (threshold 0.72)
  3. Content-based inference (ID patterns, dates, coded fields)

Returns: mapping dict, unresolved columns, inferred fields with confidence.
'''
import re
from difflib import SequenceMatcher


CANONICAL_FIELDS = [
    'emirates_id', 'given_name', 'family_name', 'date_of_birth',
    'gender', 'nationality', 'source_facility', 'registration_date',
    'canonical_id', 'episode_id', 'encounter_type', 'admission_date',
    'discharge_date', 'diagnosis_code', 'procedure_code',
    'secondary_diagnoses', 'discharge_summary', 'drg_code', 'laterality',
    'consent_status', 'consent_date', 'consent_scope',
    'preauth_reference', 'preauth_valid_until',
    'triage_level', 'total_cost_aed',
]

OUTPUT_FIELD_HINTS = {
    'decision', 'trustscore', 'mdsscore', 'codingcoherence',
    'drgreadiness', 'consentstatus', 'prior' 'authorizationstatus',
    'governanceissues', 'governanceissuecount', 'identifierissue',
    'missingmdsfields', 'codingissuetype', 'drgmissinginputs',
    'parejectioncause', 'paexpirydate',
}

SYNONYMS = {
    'emirates_id': [
        'emiratesid', 'emirates', 'eid', 'nationalid', 'nationalidentifier',
        'patientid', 'patientidentifier', 'patientmrn', 'mrn', 'prn',
        'prnidentifier', 'identifier', 'id', 'uid', 'patientuid',
        'uniqueidentifier', 'primaryidentifier', 'abha', 'abhanumber',
        'aadhaar', 'aadhaarnumber', 'nhsnumber', 'nhs', 'ur', 'urnumber',
        'patientnumber', 'hospitalnumber', 'medicalrecordnumber',
        'patmrnid', 'patid', 'personid', 'personidentifier',
    ],
    'given_name': [
        'givenname', 'firstname', 'forename', 'given', 'first', 'namefirst',
        'patientfirstname', 'patientgivenname', 'firstnm', 'fname',
        'patfirstname', 'patientfirst', 'firstnm',
    ],
    'family_name': [
        'familyname', 'lastname', 'surname', 'family', 'last', 'namelast',
        'patientlastname', 'patientfamilyname', 'lastnm', 'lname',
        'patlastname', 'patientlast', 'surname1',
    ],
    'date_of_birth': [
        'dateofbirth', 'dob', 'birthdate', 'birthday', 'datebirth',
        'patientdob', 'birthdt', 'dateofbirthpatient', 'birthdate',
        'birthdtm', 'dateofbirth1',
    ],
    'gender': [
        'sex', 'patientgender', 'administrativesex', 'sexassigned',
        'genderidentity', 'sexcd', 'genderdesc',
    ],
    'nationality': [
        'country', 'countryoforigin', 'citizenship', 'nation',
        'nationalitydesc', 'countrycode', 'countryname',
    ],
    'source_facility': [
        'facility', 'hospital', 'sourcefacility', 'facilityname',
        'hospitalname', 'sourcehospital', 'providerfacility',
        'site', 'sitename', 'source', 'sendingfacility',
    ],
    'registration_date': [
        'registrationdate', 'regdate', 'regdt', 'registeredon',
        'createdon', 'createdat', 'recordcreatedon',
    ],
    'canonical_id': [
        'canonicalid', 'recordid', 'recordidentifier', 'sourcerecordid',
        'uid', 'rowid', 'internalid',
    ],
    'episode_id': [
        'episodeid', 'encounterid', 'visitid', 'visitnumber',
        'encounternumber', 'encounter', 'encntrid', 'encid', 'visitno',
        'admissionid', 'caseid',
    ],
    'encounter_type': [
        'encountertype', 'visittype', 'admissiontype', 'inpatientflag',
        'patienttype', 'encounterclass', 'visitcategory', 'admissioncategory',
        'encntrtype', 'patientclass',
    ],
    'admission_date': [
        'admissiondate', 'admitdate', 'admittedon', 'dateofadmission',
        'admitdtm', 'admdate', 'admissiondt', 'dateadmitted',
    ],
    'discharge_date': [
        'dischargedate', 'dischargedon', 'dateofdischarge', 'dischdtm',
        'dischdate', 'datedischarged', 'dischdt',
    ],
    'diagnosis_code': [
        'diagnosiscode', 'icd', 'icdcode', 'icd10', 'diagnosis',
        'primarydiagnosis', 'dxcode', 'dx', 'icd10code', 'diagnosiscd',
        'diagcode', 'principaldiagnosis',
    ],
    'procedure_code': [
        'procedurecode', 'cpt', 'cptcode', 'proc', 'proccode',
        'primaryprocedure', 'procCode', 'cpt4', 'procedurecd', 'proccd',
    ],
    'secondary_diagnoses': [
        'secondarydiagnoses', 'secondarydiagnosis', 'secondarydx',
        'otherdiagnoses', 'additionaldiagnoses', 'secondaryicd',
    ],
    'discharge_summary': [
        'dischargesummary', 'dischargeletter', 'summaryofdischarge',
        'dischargenote', 'summarydischarge',
    ],
    'drg_code': [
        'drg', 'drgcode', 'irdrg', 'irdrgcode', 'drgvalue', 'drgfinal',
    ],
    'laterality': [
        'laterality', 'side', 'bodyside', 'anatomicallaterality',
    ],
    'consent_status': [
        'consentstatus', 'consent', 'consentstate', 'consentflag',
        'sharingconsent', 'datasharingconsent',
    ],
    'consent_date': [
        'consentdate', 'dateofconsent', 'consentcapturedon',
    ],
    'consent_scope': [
        'consentscope', 'consenttype', 'consentpurpose', 'sharingscope',
    ],
    'preauth_reference': [
        'preauthreference', 'preauth', 'preauthnumber', 'panumber',
        'preauthref', 'authnumber', 'authorizationnumber', 'preref',
    ],
    'preauth_valid_until': [
        'preauthvaliduntil', 'paexpirydate', 'preauthexpiry', 'paexpiry',
        'authorizationexpirydate', 'preauthvalidto',
    ],
    'triage_level': [
        'triagelevel', 'triage', 'acuity', 'acuitylevel', 'triagescore',
        'triagedpriority',
    ],
    'total_cost_aed': [
        'totalcostaed', 'totalcost', 'amount', 'billedamount',
        'claimamount', 'cost', 'totamount', 'netamount', 'grossamount',
    ],
}


def _normalize(name):
    if name is None:
        return ''
    s = str(name).strip().lower()
    s = re.sub(r'[\s_\-\.\/]+', '', s)
    return s


def _content_hint(values, column_name=''):
    clean = [str(v).strip() for v in values if v is not None and str(v).strip() != '' and str(v).lower() not in ('nan', 'nat', 'none')]
    if not clean:
        return None, 0.0
    sample = clean[:200]
    n = len(sample)

    def frac(pred):
        return sum(1 for v in sample if pred(v)) / n

    # Emirates ID — 784 prefix, 15 digits total
    if frac(lambda v: re.match(r'^784\d{12}$', re.sub(r'[\s\-]', '', v))) > 0.8:
        return 'emirates_id', 0.95
    # Aadhaar/ABHA — 12 digits
    if frac(lambda v: re.match(r'^\d{12}$', re.sub(r'[\s\-]', '', v))) > 0.9:
        return 'emirates_id', 0.7
    # NHS number — 10 digits
    if frac(lambda v: re.match(r'^\d{10}$', re.sub(r'[\s\-]', '', v))) > 0.9:
        return 'emirates_id', 0.5
    # MRN-like: alphanumeric 6-20 chars with digits
    if frac(lambda v: re.match(r'^[A-Z0-9]{6,20}$', str(v).strip().upper()) and any(c.isdigit() for c in str(v))) > 0.9:
        return 'canonical_id', 0.4

    # ISO dates
    if frac(lambda v: re.match(r'^\d{4}-\d{2}-\d{2}', v)) > 0.85:
        years = []
        for v in sample:
            try:
                years.append(int(v[:4]))
            except (ValueError, TypeError):
                continue
        if years:
            min_y = min(years)
            max_y = max(years)
            if min_y < 1950:
                return 'date_of_birth', 0.9
            if max_y > 2030:
                return None, 0.0
            if min_y >= 2015:
                return 'admission_date', 0.5
        return None, 0.0

    # Gender
    if frac(lambda v: str(v).upper() in ('M', 'F', 'O', 'U', 'MALE', 'FEMALE')) > 0.85:
        return 'gender', 0.95

    # ICD-10 codes
    if frac(lambda v: re.match(r'^[A-Z]\d{2}(\.\d{1,2})?$', str(v).strip().upper())) > 0.8:
        return 'diagnosis_code', 0.85

    # CPT codes (5 digits)
    if frac(lambda v: re.match(r'^\d{5}$', str(v).strip())) > 0.9:
        return 'procedure_code', 0.75

    # Consent status
    if frac(lambda v: str(v).lower() in ('granted', 'denied', 'restricted', 'withdrawn', 'unknown')) > 0.85:
        return 'consent_status', 0.9

    # Numeric cost-like column
    if frac(lambda v: re.match(r'^\d{1,7}(\.\d{1,2})?$', str(v).strip())) > 0.9:
        nums = []
        for v in sample:
            try:
                nums.append(float(v))
            except (ValueError, TypeError):
                continue
        if nums and 100 <= sum(nums) / len(nums) <= 50000:
            return 'total_cost_aed', 0.5

    return None, 0.0


def _fuzzy_match(normalized_name):
    best_field = None
    best_score = 0.0
    for field, synonyms in SYNONYMS.items():
        candidates = [_normalize(field)] + synonyms
        for c in candidates:
            score = SequenceMatcher(None, normalized_name, c).ratio()
            if score > best_score:
                best_score = score
                best_field = field
    if best_score >= 0.72:
        return best_field, best_score
    return None, 0.0


def detect_output_file(df):
    '''Detect if a file looks like a scored export rather than raw input.'''
    normalized = [_normalize(c) for c in df.columns]
    hint_hits = sum(1 for n in normalized if n in OUTPUT_FIELD_HINTS)
    has_name = any(_normalize(c) in SYNONYMS['given_name'] or _normalize(c) in SYNONYMS['family_name'] for c in df.columns)
    return hint_hits >= 3 and not has_name


def map_columns(df, content_inference=True):
    mapping = {}
    inferred = []
    used_canonical = set()

    canonical_norms = {f: _normalize(f) for f in CANONICAL_FIELDS}

    for col in df.columns:
        norm = _normalize(col)
        matched = False
        for field, cn in canonical_norms.items():
            if cn == norm and field not in used_canonical:
                mapping[col] = field
                used_canonical.add(field)
                matched = True
                break
        if matched:
            continue
        for field, syns in SYNONYMS.items():
            if field in used_canonical:
                continue
            if norm in syns:
                mapping[col] = field
                used_canonical.add(field)
                matched = True
                break

    for col in df.columns:
        if col in mapping:
            continue
        norm = _normalize(col)
        field, score = _fuzzy_match(norm)
        if field and field not in used_canonical:
            mapping[col] = field
            used_canonical.add(field)

    if content_inference:
        for col in df.columns:
            if col in mapping:
                continue
            sample = df[col].dropna().astype(str).head(200).tolist()
            field, conf = _content_hint(sample, col)
            if field and field not in used_canonical:
                mapping[col] = field
                used_canonical.add(field)
                inferred.append({'column': col, 'field': field, 'confidence': conf})

    unresolved = [c for c in df.columns if c not in mapping]
    return mapping, unresolved, inferred
