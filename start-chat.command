#!/bin/zsh
# Explicit foreground launch for the isolated, real-chat instance.
set -eu
cd "${0:A:h}"
CHAT_DATA="${1:-work/primordial00-first-wake}"
CHAT_PORT="${DIGITAL_LIFE_CHAT_PORT:-18765}"
CHAT_NAME="${CHAT_DATA:t}"
CHAT_WAKE="${DIGITAL_LIFE_WAKE:-1}"
CHAT_SHOW_ONLY=0
if [[ "$CHAT_DATA" == "--show-config" ]]; then
  CHAT_SHOW_ONLY=1
  CHAT_DATA="work/primordial00-first-wake"
  CHAT_NAME="${CHAT_DATA:t}"
fi
if [[ "$CHAT_WAKE" != 0 && "$CHAT_WAKE" != 1 ]]; then
  print -u2 "DIGITAL_LIFE_WAKE 只能为 0 或 1。"
  exit 1
fi
if [[ ! -f "$CHAT_DATA/runtime.sqlite" ]]; then
  print -u2 '聊天实例不存在。不会自动新建或替换身份；请先显式 prepare --strict。'
  exit 1
fi
PYTHONDONTWRITEBYTECODE=1 python3 - "$CHAT_DATA" "$CHAT_PORT" "$CHAT_WAKE" <<'PYCONF'
import sys
from digital_life.entrypoints.startup_info import show
show(sys.argv[1],int(sys.argv[2]),sys.argv[3]=='1')
PYCONF
if [[ "$CHAT_SHOW_ONLY" == 1 ]]; then exit 0; fi
# Reopen the authenticated panel if this same instance is already served.
if python3 - "$CHAT_DATA" "$CHAT_PORT" <<'PY'
import json,sys,urllib.request
from pathlib import Path
try:
 root=Path(sys.argv[1]);token=(root/'controller.token').read_text().strip()
 req=urllib.request.Request('http://127.0.0.1:'+sys.argv[2]+'/internal/live',headers={'Authorization':'Bearer '+token})
 with urllib.request.urlopen(req,timeout=2) as response:ok=json.load(response).get('alive') is True
 sys.exit(0 if ok else 1)
except Exception:sys.exit(1)
PY
then
  open "http://127.0.0.1:$CHAT_PORT/"
  if [[ "$CHAT_WAKE" == 1 ]] && ! PYTHONDONTWRITEBYTECODE=1 python3 - "$CHAT_DATA" "$CHAT_PORT" <<'PYSTATE'
import sys
from digital_life.entrypoints.startup_info import configuration
sys.exit(0 if configuration(sys.argv[1],int(sys.argv[2]))['当前唤醒状态']=='已唤醒' else 1)
PYSTATE
  then
    print '面板已打开，正在按配置唤醒当前实例。'
    exec python3 manage.py --data "$CHAT_DATA" wake --confirm "WAKE $CHAT_NAME"
  fi
  print '已打开当前实例面板，没有重复启动运行器。'
  exit 0
fi
if [[ "$CHAT_WAKE" == 0 ]]; then
  exec python3 manage.py --data "$CHAT_DATA" panel --port "$CHAT_PORT"
fi
exec python3 manage.py --data "$CHAT_DATA" start --port "$CHAT_PORT" --open --confirm "WAKE $CHAT_NAME"
