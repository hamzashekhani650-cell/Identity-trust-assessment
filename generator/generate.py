"""
Standalone synthetic patient population generator.
Generates FHIR Patient resources with realistic identity degradation.
"""
import random
import json
import argparse


NAME_POOLS = {
    "Emirati": {
        "given": ["Ahmed", "Maryam", "Khalid", "Noura", "Saeed", "Latifa"],
        "family": ["Al-Mansoori", "Al-Zahra", "Al-Nuaimi", "Al-Falasi"],
    },
    "Indian": {
        "given": ["Raj", "Priya", "Arun", "Deepa", "Vikram", "Meera"],
        "family": ["Kumar", "Sharma", "Patel", "Reddy", "Nair"],
    },
    "Filipino": {
        "given": ["Maria", "Jose", "Ana", "Carlo", "Rosa", "Miguel"],
        "family": ["Santos", "Reyes", "Cruz", "Garcia", "Mendoza"],
    },
    "Pakistani": {
        "given": ["Ali", "Fatima", "Hassan", "Zara", "Bilal", "Aisha"],
        "family": ["Khan", "Ahmed", "Malik", "Hussain"],
    },
}

DEMOGRAPHIC_MIX = [
    ("Indian",    0.38),
    ("Pakistani", 0.17),
    ("Emirati",   0.11),
    ("Filipino",  0.06),
]

FACILITIES = [
    "Cleveland Clinic Abu Dhabi",
    "Sheikh Khalifa Medical City",
    "Al Noor Hospital",
    "Mediclinic Abu Dhabi",
]


def pick_demographic():
    r = random.random()
    c = 0
    for group, w in DEMOGRAPHIC_MIX:
        c += w
        if r <= c:
            return group
    return "Indian"


def make_emirates_id():
    year = random.randint(1950, 2010)
    return f"784-{year}-{random.randint(1000000, 9999999)}-{random.randint(0,9)}"


def make_dob():
    return f"{random.randint(1950,2010)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"


def degrade(rec):
    if random.random() < 0.25:
        rec["identifier"] = []
    if random.random() < 0.10:
        parts = rec["birthDate"].split("-")
        day = max(1, int(parts[2]) - random.randint(1, 5))
        rec["birthDate"] = f"{parts[0]}-{parts[1]}-{day:02d}"
    if random.random() < 0.15:
        rec["name"][0]["given"][0] = rec["name"][0]["given"][0][:-1] + "x"
    return rec


def generate_fhir_patient(patient_id):
    group = pick_demographic()
    pool = NAME_POOLS[group]
    return {
        "resourceType": "Patient",
        "id": f"P{patient_id:05d}",
        "identifier": [{
            "system": "https://fhir.doh.gov.ae/emirates-id",
            "value": make_emirates_id(),
        }],
        "name": [{
            "given": [random.choice(pool["given"])],
            "family": random.choice(pool["family"]),
        }],
        "birthDate": make_dob(),
        "meta": {
            "tag": [{
                "system": "https://fhir.doh.gov.ae/facility",
                "display": random.choice(FACILITIES),
            }]
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--out", type=str, default="synthetic_population.json")
    args = parser.parse_args()

    population = []
    for i in range(args.n):
        rec = generate_fhir_patient(i)
        rec = degrade(rec)
        population.append(rec)

    with open(args.out, "w") as f:
        json.dump(population, f, indent=2)

    print(f"Generated {len(population)} patients to {args.out}")


if __name__ == "__main__":
    main()