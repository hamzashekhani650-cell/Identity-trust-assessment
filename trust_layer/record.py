from dataclasses import dataclass
from typing import Optional


@dataclass
class PatientRecord:
    emirates_id: Optional[str] = None
    passport_number: Optional[str] = None
    local_mrn: Optional[str] = None
    given_name: str = ""
    family_name: str = ""
    date_of_birth: str = ""
    nationality: str = ""
    source_facility: str = ""
    registration_date: str = ""
    canonical_id: str = ""