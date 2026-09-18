from fastapi import Request


def client_ip(request: Request) -> str:
    """取客户端 IP：优先 X-Forwarded-For（nginx 反代会写），否则退回直连地址。

    仅用于限流分桶与审计留痕，不参与鉴权；所以哪怕 XFF 被伪造，最坏结果
    也只是把自己的限流桶换个 key，拿不到任何越权能力。
    """
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""
