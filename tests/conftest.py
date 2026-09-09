import pytest
from homeassistant.util import dt as dt_util


@pytest.fixture(autouse=True)
def _use_utc_as_default_time_zone():
    """Pin Home Assistant's dt_util timezone to UTC for every test.

    Without this, tests relying on dt_util.now()/as_local() would behave
    differently depending on the machine (and CI runner) local timezone.
    """
    dt_util.set_default_time_zone(dt_util.UTC)
