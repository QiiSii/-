import datetime as dt

from dashboard import classify_trend, inventory_risk_level


def test_classify_trend_up_down_flat():
    assert classify_trend(120, 80)[0] == "上升"
    assert classify_trend(50, 100)[0] == "下滑"
    assert classify_trend(102, 100)[0] == "持平"


def test_inventory_risk_levels():
    assert inventory_risk_level(10, 5, 20)[0] == "高风险"
    assert inventory_risk_level(30, 5, 10)[0] == "中风险"
    assert inventory_risk_level(100, 5, 10)[0] == "低风险"
