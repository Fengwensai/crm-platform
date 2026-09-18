"""CSV 下载响应 + 导出行数上限。

`csv_response` **逐字复制自 dialect-platform/backend/app/services/export.py**。
刻意复制而不是抽公共包：两个仓库独立 venv、独立部署，只是恰好同机跑，
一个平台的重构不该能影响另一个；而且加顶层目录要改打包 tar 和解包命令，
那条命令在本项目有过 `rm -rf scripts` 误删 `backup.sh` 的前科。
保留完全相同的模块路径与函数签名，是为了让将来 diff 两个仓库是有意义的。

方言平台那份 224 行里其余（ZIP 打包、录音富化）全是方言专属，不搬。
"""

import csv
import io
from urllib.parse import quote

from fastapi import HTTPException, Response

# ————————————————————————————————————————————————
# ★ 导出必须限行数。这条是本平台最独特的一个风险，写清楚：
#
#   `csv_response` 里的 `text.getvalue()` 再 `.encode()` 会产生**两份完整副本**。
#   服务器是 `MemoryMax=512M`，而且**与方言采集平台同机**——一次超大的导出
#   打爆内存，被 OOM killer 带走的可能是隔壁那个正在采集的生产平台。
#   这是共享故障域，不是本平台自己崩一下就完事。
#
#   超限**返回 422 让用户缩小范围**，**绝不静默截断**：被悄悄砍掉一半的表格
#   会让人拿它去做决策，比直接报错危险得多。
# ————————————————————————————————————————————————
EXPORT_MAX_ROWS = 50_000


def csv_response(
    rows: list[dict], columns: list[str], fname: str, *, ascii_name: str = "export.csv"
) -> Response:
    """utf-8-sig CSV 下载响应（Excel 双击可直接打开中文）。

    ★ 为什么是 `utf-8-sig` 而不是 `utf-8`：Excel 打开无 BOM 的 UTF-8 CSV
      会按 GBK 解释，中文全变乱码——这是「导出的表格打不开」类投诉的头号原因。

    ★ 为什么 filename 要写两遍，而且 plain 那个**必须是 ASCII**：

      Starlette 把响应头按 **latin-1** 编码，中文文件名直接 `UnicodeEncodeError`
      → 整个请求 500。这不是理论风险，是实测（starlette 1.4.1，本仓同一份依赖）。

      ★ 这一处与方言平台那份**有意不同**，别当成抄漏了：方言的
        `services/export.py` 写的是 `filename="{fname}"` 直塞中文，它之所以没炸，
        纯粹因为它的三个调用方（tasks / words / speakers）**恰好都传 ASCII 文件名**；
        而真正需要中文名的那份本地拷贝（`mp.py` 的 `_csv_response`）自己加了
        ASCII 兜底——说明有人踩过这个坑，只是没回头修公共服务。
        本平台每一个导出都是中文名（导出的是给 Excel 看的业务表格），
        照抄那一版**上线即 500**，所以这里直接采用 mp.py 的兜底写法。
    """
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=text.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={
            # plain：HTTP 老语法，只能放 ASCII，给老浏览器兜底
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; '
                f"filename*=UTF-8''{quote(fname)}"
            )
        },
    )


def assert_export_size(n: int) -> None:
    """导出前先数一遍，超限就 422。

    ★ 必须**在把行取进内存之前**调用（先 `.count()` 再 `.all()`）。
      等 `rows` 已经躺在内存里再检查，内存已经被吃掉了，检查毫无意义。
    """
    if n > EXPORT_MAX_ROWS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"本次导出 {n} 行，超过单次上限 {EXPORT_MAX_ROWS} 行。"
                f"请缩小日期范围或增加筛选条件后重试。"
            ),
        )
