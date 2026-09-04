#!/bin/bash
# bdrc-cli.sh — BDRC token management and PDF download helper
# Token 走 cache file (~/.config/bdrc/token) 或 env BDRC_TOKEN,不再依赖 cmux browser。
# 拿 token:在已登录 BDRC 的浏览器 DevTools 跑 localStorage.getItem('access_token')
# 然后:bdrc-cli.sh token <TOKEN_STR>  写入 cache
# 或:export BDRC_TOKEN='...'        优先于 cache
set -euo pipefail

BDRC_URL="https://library.bdrc.io"
IIIF_URL="https://iiif.bdrc.io"
TOKEN_FILE="${BDRC_TOKEN_FILE:-$HOME/.config/bdrc/token}"

# ─── JWT Expiry Check ───

is_token_expired() {
    local token="$1"
    [ -z "$token" ] && return 0
    [ "$token" = "null" ] && return 0

    local exp
    exp=$(echo "$token" | cut -d. -f2 | python3 -c "
import sys, base64, json
p = sys.stdin.read().strip()
p += '=' * (4 - len(p) % 4)
try:
    print(json.loads(base64.urlsafe_b64decode(p)).get('exp', 0))
except:
    print(0)
" 2>/dev/null)

    local now
    now=$(date +%s)
    [ "${exp:-0}" -le "$((now + 60))" ]
}

# ─── Token Source ───

read_cached_token() {
    if [ -n "${BDRC_TOKEN:-}" ]; then
        printf '%s' "$BDRC_TOKEN"
        return 0
    fi
    if [ -f "$TOKEN_FILE" ]; then
        cat "$TOKEN_FILE"
        return 0
    fi
    return 1
}

write_cached_token() {
    local token="$1"
    mkdir -p "$(dirname "$TOKEN_FILE")"
    printf '%s' "$token" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
}

# ─── Token Command ───
# bdrc-cli.sh token              → echo cached token (验证有效)
# bdrc-cli.sh token <TOKEN_STR>  → 写 token 到 cache

cmd_token() {
    local arg="${1:-}"
    if [ -n "$arg" ]; then
        write_cached_token "$arg"
        echo "Token cached to $TOKEN_FILE" >&2
        if is_token_expired "$arg"; then
            echo "WARNING: Token is already expired or expires within 60s" >&2
            return 1
        fi
        local exp now
        exp=$(echo "$arg" | cut -d. -f2 | python3 -c "
import sys, base64, json
p = sys.stdin.read().strip()
p += '=' * (4 - len(p) % 4)
print(json.loads(base64.urlsafe_b64decode(p)).get('exp', 0))" 2>/dev/null)
        now=$(date +%s)
        echo "Valid for $(( (exp - now) / 60 )) minutes" >&2
        return 0
    fi

    local token
    if ! token=$(read_cached_token); then
        cat >&2 <<EOF
ERROR: No BDRC token found.

To set token:
  1. Open https://library.bdrc.io in any logged-in browser (Chrome/Safari)
  2. Open DevTools → Console
  3. Run: localStorage.getItem('access_token')
  4. Copy the JWT string (between quotes), then:
       bdrc-cli.sh token <PASTE_TOKEN_HERE>
  Or:
       export BDRC_TOKEN='...'
EOF
        exit 1
    fi
    if is_token_expired "$token"; then
        echo "ERROR: Cached BDRC token is expired. Run \`bdrc-cli.sh token <NEW_TOKEN>\` to refresh." >&2
        exit 1
    fi
    echo "$token"
}

# ─── Download Command ───

cmd_download() {
    local volume_id="$1"
    local page_range="$2"
    local output_path="$3"

    if [ -f "$output_path" ]; then
        local size
        size=$(stat -f%z "$output_path" 2>/dev/null || stat -c%s "$output_path" 2>/dev/null)
        echo "SKIP: Already exists ($(echo "scale=1; $size/1048576" | bc)MB): $output_path"
        return 0
    fi

    mkdir -p "$(dirname "$output_path")"

    local token
    token=$(cmd_token)

    local gen_url="${IIIF_URL}/download/pdf/v:bdr:${volume_id}::${page_range}"
    local max_polls=60
    local actual_url=""

    echo "Requesting PDF: ${volume_id} pages ${page_range}..." >&2

    for i in $(seq 1 $max_polls); do
        local response
        response=$(curl -s -H "Authorization: Bearer $token" "$gen_url")

        if echo "$response" | grep -q "Generating"; then
            local pct
            pct=$(echo "$response" | grep -oE '[0-9]+%' | head -1 || echo "?%")
            printf "\r  Generating... %s (poll %d/%d)" "$pct" "$i" "$max_polls" >&2
            sleep 3

        elif echo "$response" | grep -q "Download link\|download/file"; then
            actual_url=$(echo "$response" | grep -oE 'href="[^"]*"' | head -1 | sed 's/href="//;s/"//')
            echo "" >&2
            break

        elif echo "$response" | grep -qi "log in\|401\|unauthorized"; then
            echo "" >&2
            echo "ERROR: BDRC returned 401/login required. Token may be expired." >&2
            echo "Run \`bdrc-cli.sh token <NEW_TOKEN>\` to update cached token." >&2
            exit 1
        else
            echo "" >&2
            echo "ERROR: Unexpected response from BDRC:" >&2
            echo "$response" | head -5 >&2
            exit 2
        fi
    done

    if [ -z "$actual_url" ]; then
        echo "ERROR: PDF generation timed out after 3 minutes." >&2
        echo "TIP: Try a smaller page range (e.g., 1-30)." >&2
        exit 3
    fi

    echo "  Downloading PDF..." >&2
    curl -s --retry 2 -o "$output_path" -H "Authorization: Bearer $token" "$actual_url"

    local filetype
    filetype=$(file -b "$output_path" 2>/dev/null)

    if echo "$filetype" | grep -qi "pdf"; then
        local size
        size=$(stat -f%z "$output_path" 2>/dev/null || stat -c%s "$output_path" 2>/dev/null)
        local mb
        mb=$(echo "scale=1; $size/1048576" | bc)
        echo "OK: ${mb}MB → $output_path"
    else
        echo "ERROR: Downloaded file is not a PDF (got: $filetype)" >&2
        rm -f "$output_path"
        exit 2
    fi
}

# ─── Main Dispatcher ───

case "${1:-}" in
    token)
        cmd_token "${2:-}"
        ;;
    download)
        if [ $# -lt 4 ]; then
            echo "Usage: bdrc-cli.sh download <volume_id> <page_range> <output_path>" >&2
            exit 1
        fi
        cmd_download "$2" "$3" "$4"
        ;;
    *)
        cat >&2 <<'USAGE'
Usage: bdrc-cli.sh <command> [args]

Commands:
  token                                     Print cached token (fail if expired)
  token <TOKEN_STR>                         Cache a new token
  download <volume_id> <page_range> <path>  Download PDF from BDRC

Token sources (in order):
  1. $BDRC_TOKEN env var
  2. $BDRC_TOKEN_FILE or ~/.config/bdrc/token

To get a token:
  1. Open https://library.bdrc.io in any logged-in browser
  2. DevTools → Console → localStorage.getItem('access_token')
  3. Copy JWT, then: bdrc-cli.sh token <JWT>

Examples:
  bdrc-cli.sh token eyJhbGciOi...    # 缓存 token
  bdrc-cli.sh token                  # 验证 cached token 还有效
  bdrc-cli.sh download I2PD18926 1-197 /tmp/test.pdf
USAGE
        exit 1
        ;;
esac
