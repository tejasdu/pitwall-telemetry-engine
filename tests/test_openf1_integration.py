import pytest

from pitwall_telemetry_engine.ingestion import openf1_client


@pytest.mark.openf1_live
def test_historical_session_and_driver_registry():
    session_key = 9472
    session = openf1_client.get_session(session_key)
    drivers = openf1_client.get_drivers(session_key)

    assert session.session_key == session_key
    assert session.session_name == "Race"
    assert session.date_end > session.date_start
    assert drivers
    for driver_number, driver in drivers.items():
        assert driver.driver_number == driver_number
        assert driver.session_key == session_key
        assert driver.meeting_key == session.meeting_key
        assert driver.name_acronym.strip()
