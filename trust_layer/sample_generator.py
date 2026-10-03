'''
Sample generator for the demo.

Produces a realistic 100-record synthetic UAE or India dataset on demand.
Each call generates a fresh batch with injected problems so the demo
shows every feature (identity trust, coding, DRG, MDS, consent, prior-auth).
'''
import random
from datetime import datetime, timedelta


UAE_GIVEN_M = ['Ahmed', 'Khalid', 'Omar', 'Saeed', 'Mohamed', 'Rashid', 'Hamdan', 'Sultan']
UAE_GIVEN_F = ['Maryam', 'Fatima', 'Layla', 'Noura', 'Aisha', 'Hessa', 'Shamma', 'Alia']
UAE_FAMILY = ['Al-Mansoori', 'Al-Zahra', 'Al-Falasi', 'Al-Mazrouei', 'Al-Ketbi', 'Al-Shamsi', 'Al-Nuaimi']
UAE_TRUSTED = ['Cleveland Clinic Abu Dhabi', 'SSMC', 'Al Noor Hospital', 'Tawam Hospital', 'Sheikh Khalifa Medical City']
UAE_UNTRUSTED = ['Community Clinic Al Ain', 'Rural Health Centre Liwa']

IND_GIVEN_M = ['Raj', 'Amit', 'Arjun', 'Vikram', 'Sanjay', 'Deepak', 'Ravi', 'Karan']
IND_GIVEN_F = ['Priya', 'Anjali', 'Divya', 'Kavita', 'Neha', 'Pooja', 'Meera', 'Sneha']
IND_FAMILY = ['Kumar', 'Sharma', 'Patel', 'Reddy', 'Iyer', 'Singh', 'Gupta', 'Nair', 'Verma', 'Joshi']
IND_TRUSTED = ['Manipal Hospital', 'Apollo Hospital', 'Fortis Healthcare', 'Max Healthcare', 'Narayana Health']
IND_UNTRUSTED = ['Rural Clinic Karnataka', 'PHC Bihar']

EXPAT_NAMES = [
    ('Raj', 'Kumar', 'M'), ('Priya', 'Sharma', 'F'), ('Arjun', 'Patel', 'M'),
    ('Maria', 'Santos', 'F'), ('Jose', 'Reyes', 'M'),
    ('Wei', 'Zhang', 'M'), ('Mei', 'Wang', 'F'),
    ('Mohamed', 'Hassan', 'M'), ('Layla', 'Ibrahim', 'F'),
]

ICD_CODES = ['E11', 'I10', 'J45', 'K21', 'M54', 'F41', 'J06', 'N39', 'I25', 'E78']
CPT_FOR_ICD = {
    'E11': ['83036', '82947', '99213'],
    'I10': ['99213', '93000'],
    'J45': ['94010', '99214'],
    'K21': ['43239', '99213'],
    'M54': ['97110', '99213'],
    'F41': ['90834', '99214'],
    'J06': ['99213', '87880'],
    'N39': ['81002', '99213'],
    'I25': ['93000', '93306'],
    'E78': ['80061', '99214'],
}
ALL_CPT = ['99213', '99214', '99215', '83036', '82947', '93000', '94010',
           '43239', '97110', '90834', '81002', '87880', '93306', '80061',
           '27447', '47562', '99283']
MALFORMED_ICD = ['X99', 'ZZ7', 'ABCD', '1234', 'Q99.99', 'ZZZZ']
DRG_FOR_ICD = {
    'E11': 'K64B', 'E78': 'K64A', 'I10': 'F62B', 'I25': 'F60A',
    'J45': 'E69B', 'J06': 'E75A', 'K21': 'G67B', 'M54': 'I68B',
    'F41': 'T64B', 'N39': 'L63B',
}
MALFORMED_DRG = ['INVALID', 'XYZ', 'A1', '12345', 'Z99']
ORTHO_PROCEDURES = ['0SRC0J9', '0SRD0J9', '0SBC0ZZ', '0SBD0ZZ', '0PBC0ZZ', '0PBD0ZZ']
DISCHARGE_SUMMARIES = [
    'Patient admitted for management of chronic condition. Discharged in stable condition with follow-up scheduled.',
    'Acute episode resolved. Vitals stable at discharge. Medication review completed.',
    'Admitted for evaluation and treatment. Symptoms resolved. Discharged with outpatient follow-up.',
    'Patient responded well to treatment. No complications observed during stay.',
]
CONSENT_SCOPES = [
    'direct care only', 'direct care and care coordination',
    'direct care, care coordination, and research', 'emergency care only',
]


def _emirates_id():
    year = random.randint(1950, 2010)
    mid = random.randint(1000000, 9999999)
    return f'784-{year}-{mid}-{random.randint(0,9)}'


def _aadhaar():
    return ''.join(str(random.randint(0, 9)) for _ in range(12))


def _dob():
    year = random.randint(1950, 2010)
    return f'{year}-{random.randint(1,12):02d}-{random.randint(1,28):02d}'


def _episode_dates():
    admit = datetime(2024, random.randint(1, 12), random.randint(1, 28))
    stay = random.randint(1, 14)
    discharge = admit + timedelta(days=stay)
    return admit.strftime('%Y-%m-%d'), discharge.strftime('%Y-%m-%d')


def _triage_cost():
    triage = random.choices([1, 2, 3, 4, 5], weights=[5, 15, 30, 30, 20])[0]
    if triage <= 2:
        cost = random.randint(5000, 40000)
    elif triage == 3:
        cost = random.randint(800, 8000)
    else:
        cost = random.randint(100, 1500)
    if random.random() < 0.06:
        if triage <= 2:
            cost = random.randint(100, 400)
        else:
            cost = random.randint(15000, 30000)
    return triage, cost


def _pa_reference():
    return 'PA' + ''.join(str(random.randint(0, 9)) for _ in range(8))


def generate_sample(region_name, n=100, seed=None):
    '''Return a pandas DataFrame with n synthetic records for the given region.'''
    import pandas as pd

    if seed is None:
        seed = random.randint(1, 999999)
    random.seed(seed)

    is_uae = 'UAE' in region_name or 'DOH' in region_name
    is_india = 'India' in region_name or 'ABDM' in region_name

    if is_uae:
        trusted = UAE_TRUSTED
        untrusted = UAE_UNTRUSTED
        make_id = _emirates_id
    elif is_india:
        trusted = IND_TRUSTED
        untrusted = IND_UNTRUSTED
        make_id = _aadhaar
    else:
        trusted = UAE_TRUSTED
        untrusted = UAE_UNTRUSTED
        make_id = _emirates_id

    records = []
    for i in range(n):
        # Identity
        if is_india:
            g = random.choice(IND_GIVEN_M + IND_GIVEN_F)
            f = random.choice(IND_FAMILY)
            gender = 'M' if g in IND_GIVEN_M else 'F'
            nationality = 'India'
        elif is_uae:
            is_expat = random.random() < 0.6
            if is_expat:
                g, f, gender = random.choice(EXPAT_NAMES)
                nationality = random.choice(['India', 'Pakistan', 'Philippines', 'Egypt', 'UK'])
            else:
                gender = random.choice(['M', 'F'])
                g = random.choice(UAE_GIVEN_M if gender == 'M' else UAE_GIVEN_F)
                f = random.choice(UAE_FAMILY)
                nationality = 'UAE'
        else:
            g = random.choice(UAE_GIVEN_M + UAE_GIVEN_F)
            f = random.choice(UAE_FAMILY)
            gender = random.choice(['M', 'F'])
            nationality = 'UAE'

        eid = make_id()
        d = _dob()
        admit, discharge = _episode_dates()
        facility = random.choice(trusted + untrusted)
        icd_orig = random.choice(ICD_CODES)
        cpt = random.choice(CPT_FOR_ICD[icd_orig])
        triage, cost = _triage_cost()

        is_inpatient = random.random() < 0.80
        encounter_type = '3' if is_inpatient else '1'

        # DRG fields
        secondary = ''
        discharge_summary = ''
        drg_code = ''
        laterality = ''
        if is_inpatient:
            if random.random() > 0.15:
                secondary = random.choice([c for c in ICD_CODES if c != icd_orig])
            if random.random() > 0.10:
                discharge_summary = random.choice(DISCHARGE_SUMMARIES)
            if random.random() < 0.10:
                drg_code = random.choice(MALFORMED_DRG)
            else:
                drg_code = DRG_FOR_ICD.get(icd_orig, 'Z99Z')
            if random.random() < 0.15:
                cpt = random.choice(ORTHO_PROCEDURES)
                if random.random() < 0.80:
                    laterality = random.choice(['L', 'R', 'B'])

        # Prior-auth
        pa_prefixes = ('0S', '0P', '0T', '0L', '0B', '0C', '0D', '0F', '0G')
        pa_codes = {'27447', '27446', '27445', '47562', '47563', '47564',
                    '43239', '43235', '43236', '93000', '93306'}
        proc_upper = str(cpt).upper().replace('.', '')
        needs_pa = proc_upper in pa_codes or (len(proc_upper) >= 2 and proc_upper[:2] in pa_prefixes)

        preauth_reference = ''
        preauth_valid_until = ''
        if needs_pa:
            roll = random.random()
            if roll < 0.75:
                preauth_reference = _pa_reference()
                preauth_valid_until = datetime(2024, random.randint(6, 12), random.randint(1, 28)).strftime('%Y-%m-%d')
            elif roll < 0.88:
                preauth_reference = _pa_reference()
                preauth_valid_until = datetime(2023, random.randint(1, 6), random.randint(1, 28)).strftime('%Y-%m-%d')
            elif roll < 0.94:
                preauth_reference = 'SHORT'
                preauth_valid_until = '2024-06-30'

        # Consent
        c_roll = random.random()
        if c_roll < 0.80:
            consent_status = 'granted'
        elif c_roll < 0.88:
            consent_status = 'restricted'
        elif c_roll < 0.92:
            consent_status = 'denied'
        elif c_roll < 0.95:
            consent_status = 'withdrawn'
        elif c_roll < 0.97:
            consent_status = 'unknown'
        else:
            consent_status = ''

        consent_date = ''
        if consent_status:
            dr = random.random()
            if dr < 0.90:
                consent_date = datetime(2023, random.randint(1, 12), random.randint(1, 28)).strftime('%Y-%m-%d')
            elif dr < 0.95:
                consent_date = ''
            elif dr < 0.98:
                consent_date = datetime(2027, random.randint(1, 6), random.randint(1, 28)).strftime('%Y-%m-%d')
            else:
                consent_date = '01/01/2024'

        consent_scope = ''
        if consent_status == 'restricted' and random.random() < 0.70:
            consent_scope = random.choice(CONSENT_SCOPES)

        # Injected problems
        icd = icd_orig
        if random.random() < 0.08:
            icd = random.choice(MALFORMED_ICD)
        if random.random() < 0.15:
            eid = ''
        if random.random() < 0.10 and len(g) > 2:
            g = g[:-1] + random.choice(['x', 'z', 'b'])
        if random.random() < 0.05:
            d = '00-00-0000'
        if random.random() < 0.10:
            facility = random.choice(untrusted)
        if random.random() < 0.10 and icd in CPT_FOR_ICD and cpt not in ORTHO_PROCEDURES:
            cpt = random.choice([c for c in ALL_CPT if c not in CPT_FOR_ICD.get(icd, [])])
        if random.random() < 0.05:
            admit, discharge = discharge, admit
        if random.random() < 0.08:
            gender = ''

        records.append({
            'emirates_id': eid,
            'given_name': g,
            'family_name': f,
            'gender': gender,
            'date_of_birth': d,
            'nationality': nationality,
            'source_facility': facility,
            'registration_date': '2024-01-15',
            'canonical_id': f'SAMPLE{i+1:04d}',
            'episode_id': f'EP{i+1:05d}',
            'encounter_type': encounter_type,
            'admission_date': admit,
            'discharge_date': discharge,
            'diagnosis_code': icd,
            'procedure_code': cpt,
            'secondary_diagnoses': secondary,
            'discharge_summary': discharge_summary,
            'drg_code': drg_code,
            'laterality': laterality,
            'consent_status': consent_status,
            'consent_date': consent_date,
            'consent_scope': consent_scope,
            'preauth_reference': preauth_reference,
            'preauth_valid_until': preauth_valid_until,
            'triage_level': triage,
            'total_cost_aed': cost,
        })

    # Identifier collisions
    for j in range(6):
        candidates = [r for r in records if r['emirates_id']]
        if not candidates:
            continue
        target = random.choice(candidates)
        collision = target.copy()
        collision['given_name'] = random.choice(['Fraud', 'Test', 'Duplicate'])
        collision['family_name'] = random.choice(['Suspicious', 'Record', 'Entry'])
        collision['date_of_birth'] = '1900-01-01'
        collision['canonical_id'] = f'COLLISION_{j+1:03d}'
        records.append(collision)

    return pd.DataFrame(records)
