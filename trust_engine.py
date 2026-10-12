from database import AuditDatabase
# trust_engine.py
import re

FLOOR = 0.4

REGION_CONFIG = {
    'UAE (DOH)': {
        'id_label': 'Emirates ID',
        'id_pattern': r'^784\d{12}$',
        'trusted_facilities': {
            'Cleveland Clinic Abu Dhabi', 'Ssmc', 'Al Noor Hospital',
            'Tawam Hospital', 'Sheikh Khalifa Medical City',
        },
        'required_fields': ['emirates_id', 'given_name', 'family_name', 'date_of_birth'],
    },
    'India (ABDM)': {
        'id_label': 'ABHA / Aadhaar',
        'id_pattern': r'^\d{12}$',
        'trusted_facilities': {
            'Manipal Hospital', 'Apollo Hospital', 'Fortis Healthcare',
            'Max Healthcare', 'Aiims', 'Aiims Delhi', 'Narayana Health',
        },
        'required_fields': ['emirates_id', 'given_name', 'family_name', 'date_of_birth'],
    },
}

class CrossRecordValidator:
    def __init__(self):
        self.identifier_index = {}
        self.name_dob_index = {}

    def add_record(self, record):
        if getattr(record, 'emirates_id', None):
            self.identifier_index.setdefault(record.emirates_id, set()).add(record.canonical_id)
        key = (
            (getattr(record, 'given_name', '') or '').strip().lower(),
            (getattr(record, 'family_name', '') or '').strip().lower(),
            getattr(record, 'date_of_birth', '') or '',
        )
        if key != ('', '', ''):
            self.name_dob_index.setdefault(key, set()).add(record.canonical_id)

    def validate(self, record):
        eid = getattr(record, 'emirates_id', None)
        if eid and eid in self.identifier_index:
            owners = self.identifier_index[eid]
            if record.canonical_id not in owners:
                return 0.0
        key = (
            (getattr(record, 'given_name', '') or '').strip().lower(),
            (getattr(record, 'family_name', '') or '').strip().lower(),
            getattr(record, 'date_of_birth', '') or '',
        )
        if key != ('', '', '') and key in self.name_dob_index:
            owners = self.name_dob_index[key]
            if record.canonical_id not in owners:
                return 0.5
        return 1.0

class TrustEngine:
    def __init__(self, region_profile='UAE (DOH)', auto_threshold=0.75, quar_threshold=0.45):
        self.region_profile = region_profile
        self.threshold_auto = auto_threshold
        self.threshold_quar = quar_threshold
        self.config = REGION_CONFIG[region_profile]
        self.cross_validator = CrossRecordValidator()

    def _normalize_text(self, value):
        if not value:
            return ''
        s = str(value).strip()
        if s.lower() in ('nan', 'nat', 'none'):
            return ''
        return ' '.join(s.split()).title()

    def _normalize_id(self, value):
        if not value:
            return None
        digits = ''.join(c for c in str(value) if c.isdigit())
        return digits if digits else None

    def assess_record(self, record_data):
        """
        Accepts a dictionary OR a Pydantic model. 
        Automatically maps common messy column names to standard internal keys.
        """
        # 1. Convert Pydantic model to dict if necessary
        if not isinstance(record_data, dict):
            try:
                record_data = record_data.model_dump()
            except AttributeError:
                # Fallback for simple objects
                record_data = vars(record_data)

        # 2. Helper to grab a value regardless of key name or capitalization
        def get_val(*possible_keys):
            for key in possible_keys:
                if key in record_data and record_data[key] is not None:
                    return record_data[key]
                # Try case-insensitive match
                for actual_key in record_data.keys():
                    if str(actual_key).lower() == key.lower() and record_data[actual_key] is not None:
                        return record_data[actual_key]
            return None

        # 3. Map the messy input to standard variables
        cfg = self.config
        
        given = self._normalize_text(get_val('given_name', 'Given Name', 'FirstName', 'first_name'))
        family = self._normalize_text(get_val('family_name', 'Family Name', 'LastName', 'last_name'))
        dob = str(get_val('date_of_birth', 'Date of Birth', 'DOB', 'dob') or '').strip()[:10]
        eid = self._normalize_id(get_val('emirates_id', 'Emirates ID', 'EmiratesID', 'eid'))
        facility = self._normalize_text(get_val('source_facility', 'Facility', 'Source Facility', 'source_facility'))
        canonical_id = get_val('canonical_id', 'Canonical ID', 'id') or 'UNKNOWN'

        present = 0
        required = cfg['required_fields']
        fields = {
            'emirates_id': eid,
            'given_name': given,
            'family_name': family,
            'date_of_birth': dob,
        }
        for f in required:
            if fields.get(f):
                present += 1
        completeness = round(present / len(required), 2) if required else 1.0

        try:
            year = int(dob[:4])
            temporal = 1.0 if 1900 <= year <= 2025 else 0.3
        except (ValueError, TypeError):
            temporal = 0.0

        if not eid:
            identity = 0.0
        elif re.match(cfg['id_pattern'], eid):
            identity = 1.0
        else:
            identity = 0.3

        if not facility:
            provenance = 0.0
        elif facility in cfg['trusted_facilities']:
            provenance = 1.0
        else:
            provenance = 0.7

        # Create a simple object for the cross-record validator
        class _Rec:
            pass
        rec = _Rec()
        rec.emirates_id = eid
        rec.given_name = given
        rec.family_name = family
        rec.date_of_birth = dob
        rec.canonical_id = canonical_id

        cross_record = self.cross_validator.validate(rec)

        dims = {
            'completeness': completeness,
            'temporal': temporal,
            'identity': identity,
            'provenance': provenance,
            'cross_record': cross_record,
        }

        # Import the scoring functions inside the method to keep the engine standalone
        from trust_layer.scoring import compute_trust_score
        from trust_layer.router import route_decision_hard

        weighted_sum = compute_trust_score(**dims)

        min_dim = min(dims.values())
        composite = round(weighted_sum * (FLOOR + (1 - FLOOR) * min_dim), 4)

        decision, routing_reason = route_decision_hard(
            composite, cross_record, self.threshold_auto, self.threshold_quar
        )

        explanation = 'Record is clean and trusted.'
        primary_issue = 'None'
        if decision in ('LINK_WITH_FLAG', 'QUARANTINE'):
            weakest = min(dims, key=dims.get)
            if weakest == 'cross_record':
                if cross_record == 0.0:
                    explanation = f'Identifier collision: {cfg["id_label"]} {eid} is already registered to a different patient.'
                    primary_issue = 'Identifier Collision'
                elif cross_record == 0.5:
                    explanation = 'Name and DOB match an existing patient, but the identifier differs.'
                    primary_issue = 'Potential Name/DOB Collision'
            elif weakest == 'completeness':
                missing = [f for f in required if not fields.get(f)]
                explanation = f'Missing required fields: {", ".join(missing)}.'
                primary_issue = 'Missing Demographics'
            elif weakest == 'provenance':
                explanation = f'Facility "{facility}" is not in the trusted tier.'
                primary_issue = 'Untrusted Facility'
            elif weakest == 'temporal':
                explanation = f'Date of birth "{dob}" is invalid or outside the plausible range.'
                primary_issue = 'Temporal Validity Error'
            elif weakest == 'identity':
                explanation = f'{cfg["id_label"]} format does not match region standard.'
                primary_issue = 'Malformed Identifier'

        self.cross_validator.add_record(rec)

        return {
            'canonical_id': canonical_id,
            'trust_score': composite,
            'weighted_sum': round(weighted_sum, 4),
            'min_dimension': round(min_dim, 4),
            'decision': decision,
            'routing_reason': routing_reason,
            'dimensions': dims,
            'primary_issue': primary_issue,
            'explanation': explanation,
            'config_version': 'v0.7.0',
            'thresholds': {'auto': self.threshold_auto, 'quarantine': self.threshold_quar},
        }

    def reset(self):
        self.cross_validator = CrossRecordValidator()
