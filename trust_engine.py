def assess_record(self, record_data):
        """
        Accepts a dictionary OR a Pydantic model. 
        Automatically maps common messy column names to standard internal keys.
        """
        # 1. Convert Pydantic model to dict if necessary
        if not isinstance(record_data, dict):
            record_data = record_data.model_dump()

        # 2. Helper to grab a value regardless of key name
        def get_val(*possible_keys):
            for key in possible_keys:
                if key in record_data and record_data[key] is not None:
                    return record_data[key]
            return None

        # 3. Map the messy input to standard variables
        given = self._normalize_text(get_val('given_name', 'Given Name', 'FirstName', 'first_name'))
        family = self._normalize_text(get_val('family_name', 'Family Name', 'LastName', 'last_name'))
        dob = str(get_val('date_of_birth', 'Date of Birth', 'DOB', 'dob') or '').strip()[:10]
        eid = self._normalize_id(get_val('emirates_id', 'Emirates ID', 'EmiratesID', 'eid'))
        facility = self._normalize_text(get_val('source_facility', 'Facility', 'Source Facility', 'source_facility'))
        canonical_id = get_val('canonical_id', 'Canonical ID', 'id') or 'UNKNOWN'

        # ... REST OF YOUR EXISTING CODE BELOW THIS LINE ...
        # (Leave the completeness, temporal, identity calculations exactly as they are)
