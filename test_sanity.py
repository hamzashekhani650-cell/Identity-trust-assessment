# test_sanity.py
from trust_engine import TrustEngine

def test_engine_initialization():
    """Simple test to ensure the engine initializes correctly."""
    engine = TrustEngine()
    assert engine.region_profile == "UAE (DOH)"
    assert engine.threshold_auto == 0.75
    assert engine.threshold_quar == 0.45
