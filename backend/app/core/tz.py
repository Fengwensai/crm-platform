"""平台统一的「今天」。

**不要用 `date.today()`** —— 那是**服务器本地时区**的今天。线上服务器目前是
`Asia/Shanghai`，所以还没出问题；但这是个隐患：

- CI 跑在 GitHub Actions（UTC）。UTC 比北京时间晚 8 小时，北京时间 00:00–08:00
  期间 UTC 还停在前一天。用 `date.today()` 的话，员工填「今天」会被
  `_assert_date_allowed` 判成「不能填报未来日期」直接 422，
  而「今日工作量」统计卡会显示昨天的数。
- 将来换服务器、或容器默认 UTC，同样中招。

中国自 1991 年起无夏令时，固定 +08:00 即可。**故意不用 `ZoneInfo("Asia/Shanghai")`** ——
Windows 没有系统 tz 数据库，会直接抛 `ZoneInfoNotFoundError`，本地开发就废了。
"""

from datetime import date, datetime, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8), "CST")


def now_cn() -> datetime:
    """当前北京时间（带 tzinfo）。"""
    return datetime.now(CN_TZ)


def today_cn() -> date:
    """北京的今天。所有「今天」「不能填未来」「最近 N 天」的判断都用它。"""
    return now_cn().date()
