from rapidfuzz.distance import Levenshtein


class FuzzyCrossRecordValidator:
    def __init__(self, id_distance=1, use_phonetic=True):
        self.identifier_owners = []
        self.name_dob_owners = []
        self.id_distance = id_distance
        self.use_phonetic = use_phonetic

    def _phonetic(self, name):
        name = (name or '').lower()
        if not name:
            return ''
        first = name[0]
        rest = ''.join(c for c in name[1:] if c not in 'aeiou')
        return (first + rest)[:4]

    def _name_dob_key(self, record):
        if self.use_phonetic:
            return (self._phonetic(record.given_name),
                    self._phonetic(record.family_name),
                    record.date_of_birth)
        return (record.given_name.strip().lower(),
                record.family_name.strip().lower(),
                record.date_of_birth)

    def _name_and_dob_agree(self, a, b):
        # Strict: both family name (or prefix) AND DOB must agree
        if not (a.date_of_birth and b.date_of_birth):
            return False
        if a.date_of_birth != b.date_of_birth:
            return False
        fa = (a.family_name or '').strip().lower()
        fb = (b.family_name or '').strip().lower()
        if not fa or not fb:
            return False
        if fa == fb:
            return True
        if len(fa) >= 4 and len(fb) >= 4 and fa[:4] == fb[:4]:
            return True
        return False

    def add_record(self, record):
        if record.emirates_id:
            self.identifier_owners.append((record.emirates_id, record))
        self.name_dob_owners.append((self._name_dob_key(record), record.canonical_id))

    def validate(self, record):
        if record.emirates_id:
            for eid, owner in self.identifier_owners:
                if owner.canonical_id == record.canonical_id:
                    continue
                distance = Levenshtein.distance(record.emirates_id, eid)
                if distance == 0:
                    return 0.0
                if distance <= self.id_distance:
                    if self._name_and_dob_agree(record, owner):
                        return 0.0
        key = self._name_dob_key(record)
        for existing_key, owner in self.name_dob_owners:
            if existing_key == key and owner != record.canonical_id:
                return 0.5
        return 1.0