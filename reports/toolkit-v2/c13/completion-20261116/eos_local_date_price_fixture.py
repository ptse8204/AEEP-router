"""Replay the publisher's own price sample in the two unmocked EOS tests."""

import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest

PRICE_TESTS = {
    "tests/test_elecpriceakkudoktor.py::test_cache_integration",
    "tests/test_elecpriceakkudoktor.py::test_key_to_array_resampling",
}
PRICE_SAMPLE = "tests/testdata/elecpriceforecast_akkudoktor_1.json"
PRICE_PIN = "434aa03dc2b1d5133c10fa439ad5875dc52062cef1cd0c31ccd60cbc00f07210"
START = datetime(2024, 12, 11, tzinfo=ZoneInfo("Europe/Berlin"))
REQUESTS = []


def fixture_requests():
    return list(REQUESTS)


def with_price_fixture(base):
    class PriceFixture(base):
        @pytest.hookimpl(wrapper=True)
        def pytest_runtest_call(self, item):
            if item.nodeid not in PRICE_TESTS:
                return (yield)

            import pendulum
            import requests
            import time_machine
            from akkudoktoreos.config.config import get_config
            from akkudoktoreos.core.ems import EnergieManagementSystem
            from akkudoktoreos.utils.datetimeutil import to_datetime

            sample = (Path("/tmp/aeep-repository-native-v6") / PRICE_SAMPLE).read_bytes()
            if hashlib.sha256(sample).hexdigest() != PRICE_PIN:
                raise ValueError("publisher price fixture digest changed")

            config = get_config()
            if config.prediction_hours != 48:
                raise ValueError("publisher price sample requires the default 48-hour window")
            local = START.astimezone(pendulum.local_timezone())
            expected_query = {
                "start": [(local - timedelta(days=35)).date().isoformat()],
                "end": [(local + timedelta(hours=48)).date().isoformat()],
                "tz": [str(config.timezone)],
            }

            def replay(url):
                endpoint = urlsplit(url)
                query = parse_qs(endpoint.query, strict_parsing=True)
                if ((endpoint.scheme, endpoint.netloc, endpoint.path, endpoint.fragment)
                        != ("https", "api.akkudoktor.net", "/prices", "")
                        or query != expected_query):
                    raise ValueError("forecast URL differs from reviewed offline sample request")
                REQUESTS.append(item.nodeid)
                response = requests.Response()
                response.status_code = 200
                response._content = sample
                return response

            saved = EnergieManagementSystem._start_datetime
            with time_machine.travel(START, tick=False), patch("requests.get", side_effect=replay):
                try:
                    # The adjacent upstream response-fixture test chooses this date.
                    EnergieManagementSystem.set_start_datetime(to_datetime(START, in_timezone="Europe/Berlin"))
                    return (yield)
                finally:
                    EnergieManagementSystem._start_datetime = saved

    return PriceFixture
