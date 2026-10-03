"""Reference values with effective dates; no administrator or CSV dependency."""
from typing import Any

from datetime import date
from sqlalchemy import select

from app.v2.domains.admin.models import Law
from app.v2.domains.monitoring.models import City, Standard
from app.v2.common import UNITS

GB2012 = "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/dqhjbh/dqhjzlbz/201203/t20120302_224165.shtml"
GB2026 = "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/dqhjbh/dqhjzlbz/202602/t20260225_1144419.shtml"


def seed(session: Any) -> None:
    if not session.scalar(select(City).where(City.code == "beijing")):
        session.add(City(code="beijing", name="北京"))
    periods = [
        ("GB 3095—2012", date(2016, 1, 1), date(2026, 2, 28), GB2012, {"PM2.5": 75, "PM10": 150, "SO2": 150, "NO2": 80, "CO": 4, "O3": 160}),
        ("GB 3095—2026（过渡阶段）", date(2026, 3, 1), date(2030, 12, 31), GB2026, {"PM2.5": 60, "PM10": 120, "SO2": 150, "NO2": 80, "CO": 4, "O3": 160}),
        ("GB 3095—2026", date(2031, 1, 1), None, GB2026, {"PM2.5": 50, "PM10": 100, "SO2": 50, "NO2": 50, "CO": 4, "O3": 160}),
    ]
    for code, start, end, url, values in periods:
        for pollutant, value in values.items():
            basis = "daily_max_8h" if pollutant == "O3" else "daily_mean"
            existing = session.scalar(select(Standard).where(Standard.code == code, Standard.pollutant == pollutant, Standard.basis == basis))
            if existing is None:
                session.add(Standard(code=code, pollutant=pollutant, basis=basis, limit_value=value,
                                     unit=UNITS[pollutant], min_points=14 if pollutant == "O3" else 20,
                                     effective_from=start, effective_to=end, source_url=url))
    laws = [
        ("中华人民共和国生态环境法典", "全国", date(2026, 8, 15), "https://ecro.mee.gov.cn/fgbz/fl/202604/t20260416_1148993.html", "现行生态环境基本法律。核查人员应根据具体事实确认适用条款；历史事项保留原依据。"),
        ("北京市生态环境行政处罚裁量权基准（2026年版）", "北京", date(2026, 8, 15), "https://www.beijing.gov.cn/zhengce/zhengcefagui/202608/t20260814_4823049.html", "北京地方裁量参考资料。本系统不自动作出处罚决定或估算罚款。"),
        ("环境空气质量指数（AQI）技术规定 HJ 633—2026", "全国", date(2026, 3, 1), "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/jcffbz/202602/t20260225_1144441.shtml", "空气质量指数统计与分级依据。"),
        ("环境空气质量评价技术规范 HJ 663—2026", "全国", date(2026, 3, 1), "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/jcffbz/202602/t20260225_1144459.shtml", "环境质量评价、数据统计有效性与完整性依据。"),
    ]
    for title, region, start, url, summary in laws:
        if not session.scalar(select(Law).where(Law.title == title)):
            session.add(Law(title=title, region=region, effective_from=start, source_url=url, summary=summary))
    historical = [
        ("中华人民共和国环境保护法（2014年修订）", "全国", date(2015,1,1), date(2026,8,14),
         "https://www.mee.gov.cn/ywgz/fgbz/fl/201404/t20140425_271040.shtml", "历史依据；自2026年8月15日起由生态环境法典替代。具体行为的时间效力由核查人员确认。"),
        ("中华人民共和国大气污染防治法（2018年修正）", "全国", date(2018,10,26), date(2026,8,14),
         "https://www.mee.gov.cn/ywgz/fgbz/fl/201811/t20181113_673567.shtml", "历史依据；自2026年8月15日起由生态环境法典替代，保留历史关联。"),
        ("北京市大气污染防治条例（2018年修正）", "北京", date(2018,3,30), None,
         "https://www.beijing.gov.cn/zhengce/dfxfg/202005/t20200518_1899727.html", "北京地方规则；使用时由人员核对现行条款及其与上位法的衔接，不自动推断处罚。"),
    ]
    for title, region, start, end, url, summary in historical:
        if not session.scalar(select(Law).where(Law.title == title)):
            session.add(Law(title=title, region=region, effective_from=start, effective_to=end, source_url=url, summary=summary))
