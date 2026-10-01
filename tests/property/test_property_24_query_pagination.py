"""Property 24: paged query results are the filtered, ordered slice."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.query_spec import QuerySpec
from app.services.query import AlertQueryRow, MonitoringQueryRow, query_alerts, query_monitoring

_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
_MAX = timedelta(days=31)


@given(
    count=st.integers(min_value=1, max_value=8),
    page=st.integers(min_value=1, max_value=3),
    page_size=st.integers(min_value=1, max_value=3),
    city=st.sampled_from(("北京", "上海")),
    data=st.data(),
)
@pytest.mark.property
def test_property_24_query_page_matches_the_filtered_slice(
    count: int,
    page: int,
    page_size: int,
    city: str,
    data: st.DataObject,
) -> None:
    """Monitoring and alert pages equal the filtered ordered sequence.

    **Feature: environmental-supervision-platform, Property 24: 查询谓词与分页一致**
    **Property 24：查询谓词与分页一致**
    **Validates: Requirements 10.9, 11.1, 11.2**
    """

    monitoring = []
    alerts = []
    for index in range(count):
        row_city = data.draw(st.sampled_from(("北京", "上海")))
        pollutant = data.draw(st.sampled_from(("PM2.5", "PM10")))
        moment = _START + timedelta(hours=index)
        monitoring.append(
            MonitoringQueryRow(index + 1, row_city, 1, moment, pollutant, float(index), "ONLINE", False)
        )
        alerts.append(AlertQueryRow(index + 1, row_city, 1, moment, pollutant, "SENT", "高"))
    spec = QuerySpec(start=_START, end=_START + timedelta(days=2), city=city, pollutant="PM2.5")
    mon_page = query_monitoring(monitoring, spec, page=page, page_size=page_size, max_span=_MAX)
    alert_page = query_alerts(alerts, spec, page=page, page_size=page_size, max_span=_MAX)
    mon_all = [row for row in monitoring if row.city == city and row.pollutant == "PM2.5"]
    mon_all.sort(key=lambda row: (row.observed_at, row.id))
    alert_all = [row for row in alerts if row.city == city and row.pollutant == "PM2.5"]
    alert_all.sort(key=lambda row: (row.generated_at, row.id))
    start = (page - 1) * page_size
    assert mon_page.items == tuple(mon_all[start : start + page_size])
    assert alert_page.items == tuple(alert_all[start : start + page_size])
    assert mon_page.total == len(mon_all) and mon_page.page == page and mon_page.page_size == page_size
    assert alert_page.total == len(alert_all) and alert_page.page == page and alert_page.page_size == page_size
