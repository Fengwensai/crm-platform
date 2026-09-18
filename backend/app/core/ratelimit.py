"""进程内固定窗口限流。

单 worker 部署下够用（本项目就是单 worker）。多 worker 时每个进程各计一份，
限额会成倍放宽——所以这只是「防刷的第一道闸」，真正的防线是管理员审批：
就算被刷进来一堆 pending 账号，也一个都登不上、看不到任何数据。
"""

import time
from collections import defaultdict

# (scope, key) -> [命中时间戳...]
_hits: dict[tuple[str, str], list[float]] = defaultdict(list)
_last_gc = 0.0
_GC_INTERVAL = 600.0


def _gc(now: float, max_window: float) -> None:
    """定期清掉完全过期的桶，防内存无限增长。"""
    global _last_gc
    if now - _last_gc < _GC_INTERVAL:
        return
    _last_gc = now
    cutoff = now - max_window
    for k in [k for k, v in _hits.items() if not v or v[-1] < cutoff]:
        _hits.pop(k, None)


def allow(scope: str, key: str, limit: int, window_seconds: int) -> bool:
    """记一次访问并返回是否在限额内。超限时本次不计入（窗口不再被撑长）。"""
    now = time.time()
    _gc(now, max(window_seconds, 3600))
    bucket = _hits[(scope, key)]
    cutoff = now - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True
