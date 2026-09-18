#!/usr/bin/env bash
# 端到端冒烟：走真实公网域名（nginx + TLS + uvicorn），而不是 TestClient 内进程调用。
# 专门验一件 TestClient 验不到的事：Authorization 头有没有被 nginx 透传到后端。
# 用法（服务器上）：bash scripts/e2e_http.sh
# 不打印任何密钥；结束前会把自己建的项目删掉。
set -uo pipefail

cd "$(dirname "$0")/.."
B=https://crm-api.qlzby.com
CURL="curl -sS --resolve crm-api.qlzby.com:443:127.0.0.1"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "[PASS] $1"; }
bad()  { FAIL=$((FAIL+1)); echo "[FAIL] $1   $2"; }

ADMIN_PW=$(grep '^ADMIN_INIT_PASSWORD=' .env | cut -d= -f2- | tr -d '\r\n')
TODAY=$(date +%F)
MARK="E2E$(date +%s | tail -c 5)"

jqv() { python3 -c "import sys,json;d=json.load(sys.stdin);print(d$1)" 2>/dev/null; }

# 1) 登录
LOGIN=$($CURL -X POST "$B/api/auth/login" -H 'Content-Type: application/json' \
        -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PW\"}")
TOK=$(echo "$LOGIN" | jqv "['access_token']")
[ -n "$TOK" ] && ok "HTTPS 登录拿到 token（长度 ${#TOK}）" || bad "HTTPS 登录" "$LOGIN"

AUTH="Authorization: Bearer $TOK"

# 2) ★ Authorization 头透传（nginx 丢掉它整个后台就废了）
ME=$($CURL "$B/api/auth/me" -H "$AUTH")
ROLE=$(echo "$ME" | jqv "['role']")
[ "$ROLE" = "super_admin" ] && ok "★ Authorization 头经 nginx 透传成功（/auth/me 返回 $ROLE）" \
                            || bad "★ Authorization 头透传" "$ME"

# 3) 无 token 必须 401（确认不是"没人管"）
CODE=$($CURL -o /dev/null -w '%{http_code}' "$B/api/stats/overview")
[ "$CODE" = "401" ] && ok "无 token 访问受保护接口 → 401" || bad "无 token 应 401" "得到 $CODE"

# 4) 建项目 → 填报 → 统计
PJ=$($CURL -X POST "$B/api/projects" -H "$AUTH" -H 'Content-Type: application/json' \
      -d "{\"code\":\"$MARK\",\"name\":\"端到端临时项目\",\"unit\":\"条\"}")
PID=$(echo "$PJ" | jqv "['id']")
[ -n "$PID" ] && ok "建项目成功（id=$PID）" || bad "建项目" "$PJ"

REC=$($CURL -X POST "$B/api/work-records" -H "$AUTH" -H 'Content-Type: application/json' \
       -d "{\"project_id\":$PID,\"work_date\":\"$TODAY\",\"amount\":123,\"rework_amount\":23,\"remark\":\"端到端\"}")
QUAL=$(echo "$REC" | jqv "['qualified']")
RID=$(echo "$REC" | jqv "['id']")
[ "$QUAL" = "100" ] && ok "填报成功且合格量 123-23=100" || bad "填报" "$REC"

OV=$($CURL "$B/api/stats/overview" -H "$AUTH")
TA=$(echo "$OV" | jqv "['total_amount']")
[ "${TA:-0}" -ge 123 ] && ok "总览统计已计入（total_amount=$TA）" || bad "总览统计" "$OV"

# 5) 清理：删记录 + 删项目
D1=$($CURL -o /dev/null -w '%{http_code}' -X DELETE "$B/api/work-records/$RID" -H "$AUTH")
D2=$($CURL -o /dev/null -w '%{http_code}' -X DELETE "$B/api/projects/$PID" -H "$AUTH")
[ "$D1" = "200" ] && [ "$D2" = "200" ] && ok "临时数据已清理（记录 $D1 / 项目 $D2）" \
                                        || bad "清理临时数据" "记录=$D1 项目=$D2"

echo "--------------------------------------------"
echo "PASS=$PASS  FAIL=$FAIL"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
