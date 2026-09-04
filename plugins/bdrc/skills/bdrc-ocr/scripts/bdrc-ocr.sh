#!/bin/bash
# BDRC Tibetan OCR 便利封装
#
# 把模型简称（Modern / Woodblock / …）替换成 OCRModels 下的完整路径，
# 再调用上游 buda-base/tibetan-ocr-app 的 cli.py。
#
# 用法：
#   BDRC_OCR_HOME=/path/to/tibetan-ocr-app \
#     bdrc-ocr.sh --model Modern --image page.png --output ./results --dewarp --merge-lines
#
# 模型：Modern / Woodblock / Woodblock-Stacks / Ume_Druma / Ume_Petsuk

set -euo pipefail

if [ -z "${BDRC_OCR_HOME:-}" ]; then
    cat >&2 <<'EOF'
ERROR: 需要设置 BDRC_OCR_HOME，指向 buda-base/tibetan-ocr-app 的本地目录。

  git clone https://github.com/buda-base/tibetan-ocr-app.git
  cd tibetan-ocr-app
  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
  export BDRC_OCR_HOME="$PWD"

模型需另行下载放到 $BDRC_OCR_HOME/OCRModels/ 下，见上游 README
与 BDRC 的 Huggingface 账号 https://huggingface.co/BDRC
EOF
    exit 1
fi

CLI="$BDRC_OCR_HOME/cli.py"
MODELS_DIR="$BDRC_OCR_HOME/OCRModels"

if [ ! -f "$CLI" ]; then
    echo "ERROR: 找不到 $CLI，请确认 BDRC_OCR_HOME 指向 tibetan-ocr-app 目录" >&2
    exit 1
fi

# 优先用上游项目自己的 venv，没有就用系统 python3
if [ -x "$BDRC_OCR_HOME/.venv/bin/python" ]; then
    PY="$BDRC_OCR_HOME/.venv/bin/python"
else
    PY="$(command -v python3)"
fi

# 把模型简称换成完整路径
ARGS=()
for arg in "$@"; do
    if [ -d "$MODELS_DIR/$arg" ]; then
        ARGS+=("$MODELS_DIR/$arg")
    else
        ARGS+=("$arg")
    fi
done

exec "$PY" "$CLI" "${ARGS[@]}"
