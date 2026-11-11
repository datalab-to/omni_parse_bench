from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

# ci replays the same fixed examples every run (derandomized, no database); only deep explores new ones
HEALTH = [HealthCheck.too_slow, HealthCheck.data_too_large]
settings.register_profile("ci", max_examples=300, deadline=None, derandomize=True, database=None,
                          suppress_health_check=HEALTH)
settings.register_profile("deep", max_examples=5000, deadline=None, database=None,
                          suppress_health_check=HEALTH)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))
