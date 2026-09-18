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

# 4) 建项目 → 登记一条标注 → 统计卡
#    ★ v2 起走 /api/annotations。原来这里打的是 v1 的 /api/work-records，
#      而 v2 的统计**有意不读 work_records**（见 README「双轨数据模型」），
#      所以那条断言会永远失败——不是部署坏了，是脚本没跟着换轨。
PJ=$($CURL -X POST "$B/api/projects" -H "$AUTH" -H 'Content-Type: application/json' \
      -d "{\"code\":\"$MARK\",\"name\":\"端到端临时项目\"}")
PID=$(echo "$PJ" | jqv "['id']")
[ -n "$PID" ] && ok "建项目成功（id=$PID）" || bad "建项目" "$PJ"

REC=$($CURL -X POST "$B/api/annotations" -H "$AUTH" -H 'Content-Type: application/json' \
       -d "{\"project_id\":$PID,\"work_date\":\"$TODAY\",\"item_no\":\"$MARK\",\"box2d\":23,\"box3d\":100,\"remark\":\"端到端\"}")
RID=$(echo "$REC" | jqv "['id']")
BT=$(echo "$REC" | jqv "['box_total']")
[ "$BT" = "123" ] && ok "登记标注成功且 box_total 23+100=123" || bad "登记标注" "$REC"

SUM=$($CURL "$B/api/stats/annotation-summary" -H "$AUTH")
TB=$(echo "$SUM" | jqv "['total_box']")
[ "${TB:-0}" -ge 123 ] && ok "统计卡已计入（total_box=$TB）" || bad "统计卡" "$SUM"

# 5) ★ 越权铁律：不存在的记录是 404 而不是 403。
#    403 等于承认「这条存在」，是个存在性预言机（见 README 的 404/403 规则表）。
CODE404=$($CURL -o /dev/null -w '%{http_code}' -X DELETE "$B/api/annotations/99999999" -H "$AUTH")
[ "$CODE404" = "404" ] && ok "★ 不存在的记录 → 404（不是 403）" || bad "404 铁律" "得到 $CODE404"

# 6) 清理：删记录 + 删项目
D1=$($CURL -o /dev/null -w '%{http_code}' -X DELETE "$B/api/annotations/$RID" -H "$AUTH")
D2=$($CURL -o /dev/null -w '%{http_code}' -X DELETE "$B/api/projects/$PID" -H "$AUTH")
[ "$D1" = "200" ] && [ "$D2" = "200" ] && ok "临时数据已清理（记录 $D1 / 项目 $D2）" \
                                        || bad "清理临时数据" "记录=$D1 项目=$D2"

echo "--------------------------------------------"
echo "PASS=$PASS  FAIL=$FAIL"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
