#!/usr/bin/env bash
# ============================================================================
# 七专家分析师 Agent - 一键安装脚本
# ----------------------------------------------------------------------------
# 用途: 在新机器上部署本 agent 工程
#   1) 创建虚拟环境并安装 Python 依赖（核心 + 可选）
#   2) 检查/安装 ffmpeg（视频解析功能需要）
#   3) 配置 .env（MX_APIKEY）
#   4) 修正 agent 定义里硬编码的「绝对路径」与「API Key」到当前机器
#   5) 自检关键模块可运行
#
# 用法:
#   bash install.sh                 # 交互式（推荐）
#   bash install.sh --system        # 不建虚拟环境，装到系统/user pip
#   bash install.sh --extras        # 连带安装重型可选依赖（torch 等）
#   bash install.sh --core-only     # 仅装核心依赖
#   bash install.sh --apikey <KEY>  # 直接提供 API Key，跳过交互
#   bash install.sh --yes           # 全部默认 yes（非交互，CI 友好）
# ============================================================================
#
# 上游 vendored skill 说明（本仓库未内置其引擎）：
#   - last30days（近30天多平台舆情研究）：上游 https://github.com/mvanhorn/last30days-skill
#     （author: mvanhorn, MIT）。其引擎 scripts/last30days.py 与 scripts/lib/ 未随本仓库分发，
#     需另行克隆安装后才能使用；未安装时 caisen-10-experts-analyst 会跳过该舆情通道，
#     改用 WebSearch + news-aggregator。last30days/SKILL.md 顶部已标注此约束。
# ============================================================================

set -euo pipefail

# ---------------------- 颜色与日志 ----------------------
if [[ -t 1 ]]; then
    C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'
    C_BLU=$'\033[34m'; C_CYA=$'\033[36m'; C_OFF=$'\033[0m'
else
    C_RED=""; C_GRN=""; C_YEL=""; C_BLU=""; C_CYA=""; C_OFF=""
fi
info()  { printf "%s[INFO]%s  %s\n"  "$C_BLU" "$C_OFF" "$*"; }
ok()    { printf "%s[ OK ]%s  %s\n"  "$C_GRN" "$C_OFF" "$*"; }
warn()  { printf "%s[WARN]%s  %s\n"  "$C_YEL" "$C_OFF" "$*"; }
err()   { printf "%s[ERR ]%s  %s\n"  "$C_RED" "$C_OFF" "$*" >&2; }
step()  { printf "\n%s━━▶ %s %s\n"   "$C_CYA" "$*" "$C_OFF"; }
die()   { err "$*"; exit 1; }

# ---------------------- 参数解析 ----------------------
USE_VENV=1
INSTALL_EXTRAS=""
CORE_ONLY=0
APIKEY_ARG=""
ASSUME_YES=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --system)    USE_VENV=0; shift;;
        --extras)    INSTALL_EXTRAS=1; shift;;
        --core-only) CORE_ONLY=1; shift;;
        --apikey)    APIKEY_ARG="${2:-}"; shift 2;;
        --yes|-y)    ASSUME_YES=1; shift;;
        -h|--help)
            sed -n '2,20p' "$0"; exit 0;;
        *) die "未知参数: $1（用 --help 查看用法）";;
    esac
done
[[ "$CORE_ONLY" = 1 ]] && INSTALL_EXTRAS=0
ask() { # ask "提示" -> 返回 0=yes
    if [[ "$ASSUME_YES" = 1 ]]; then return 0; fi
    local r; read -rp "$(printf '%s?%s %s [Y/n] ' "$C_YEL" "$C_OFF" "$1")" r
    [[ "$r" =~ ^[Yy]$ || -z "$r" ]]
}

# ---------------------- 定位工作区根目录 ----------------------
SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKDIR="$(cd "$SCRIPT" && pwd)"
# 原始硬编码路径（源机器默认为 /Users/weihaoli/Desktop/蔡森 skill），可用环境变量 CAISEN_OLD_PATH 覆盖
OLD_PATH="${CAISEN_OLD_PATH:-$HOME/Desktop/蔡森 skill}"
DEFAULT_KEY=""   # 内置默认 API Key（为空：需通过 --apikey 传入或从 .env 读取）

step "环境检测"
info "工作区根目录: $WORKDIR"
info "操作系统:     $(uname -s) $(uname -m)"
[[ -f "$WORKDIR/.qoder/agents/seven-experts-analyst.md" ]] \
    || die "未在 $WORKDIR 找到 .qoder/agents/seven-experts-analyst.md，请确认脚本位于工程根目录"

# ---------------------- Python 版本检查 ----------------------
command -v python3 >/dev/null 2>&1 || die "未找到 python3，请先安装 Python 3.9+"
PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
PYMAJ=${PYV%.*}; PYMIN=${PYV#*.}
if [[ "$PYMAJ" -lt 3 || ( "$PYMAJ" -eq 3 && "$PYMIN" -lt 9 ) ]]; then
    die "Python 版本过低 ($PYV)，需 3.9+"
fi
ok "Python $PYV"

# ---------------------- 决定 pip / python 解释器 ----------------------
if [[ "$USE_VENV" = 1 ]]; then
    step "创建/使用虚拟环境 (.venv)"
    if [[ ! -d "$WORKDIR/.venv" ]]; then
        python3 -m venv "$WORKDIR/.venv" || die "创建虚拟环境失败"
        ok "已创建 $WORKDIR/.venv"
    else
        ok "虚拟环境已存在，复用"
    fi
    PY="$WORKDIR/.venv/bin/python"
    PIP=( "$PY" -m pip )
else
    step "系统模式（不建虚拟环境）"
    PY="python3"
    PIP=( python3 -m pip )
    warn "系统模式可能因 PEP668 报错；若失败请改用默认虚拟环境模式（去掉 --system）"
fi
"$PIP" install --quiet --upgrade pip >/dev/null
ok "pip 就绪"

# ---------------------- 安装核心依赖 ----------------------
step "安装核心依赖 (requirements.txt)"
if [[ -f "$WORKDIR/requirements.txt" ]]; then
    if [[ "$USE_VENV" = 0 ]]; then
        "${PIP[@]}" install --user -r "$WORKDIR/requirements.txt" \
            || die "系统模式安装失败，建议去掉 --system 改用虚拟环境"
    else
        "${PIP[@]}" install -r "$WORKDIR/requirements.txt" || die "核心依赖安装失败"
    fi
    ok "核心依赖安装完成"
else
    warn "未找到 requirements.txt，跳过"
fi

# ---------------------- 可选重型依赖 ----------------------
if [[ -z "$INSTALL_EXTRAS" && "$CORE_ONLY" = 0 ]]; then
    if ask "是否安装可选扩展依赖（torch/transformers/sklearn 等，体积大，alphaear 语义搜索/可视化用）？"; then
        INSTALL_EXTRAS=1
    fi
fi
if [[ "$INSTALL_EXTRAS" = 1 ]]; then
    step "安装可选扩展依赖 (requirements-extras.txt)"
    if [[ -f "$WORKDIR/requirements-extras.txt" ]]; then
        if [[ "$USE_VENV" = 0 ]]; then
            "${PIP[@]}" install --user -r "$WORKDIR/requirements-extras.txt" \
                || warn "部分扩展依赖安装失败，可稍后手动 pip install"
        else
            "${PIP[@]}" install -r "$WORKDIR/requirements-extras.txt" \
                || warn "部分扩展依赖安装失败，可稍后手动 pip install"
        fi
        ok "扩展依赖处理完成（若有警告请按需手动补装）"
    else
        warn "未找到 requirements-extras.txt，跳过"
    fi
fi

# ---------------------- ffmpeg 检测/安装 ----------------------
step "检查 ffmpeg（视频解析功能需要）"
if command -v ffmpeg >/dev/null 2>&1; then
    ok "ffmpeg 已安装: $(ffmpeg -version | head -1)"
else
    warn "未检测到 ffmpeg"
    if ask "是否现在安装 ffmpeg？"; then
        case "$(uname -s)" in
            Darwin)
                if command -v brew >/dev/null 2>&1; then
                    brew install ffmpeg || warn "brew 安装失败，请手动安装"
                else
                    warn "未检测到 Homebrew，请先装 brew 或手动安装 ffmpeg"
                fi ;;
            Linux)
                if command -v apt-get >/dev/null 2>&1; then
                    sudo apt-get update && sudo apt-get install -y ffmpeg \
                        || warn "apt 安装失败，请手动安装"
                elif command -v yum >/dev/null 2>&1; then
                    sudo yum install -y ffmpeg || warn "yum 安装失败，请手动安装"
                else
                    warn "未识别的包管理器，请手动安装 ffmpeg"
                fi ;;
            *) warn "无法自动安装，请手动安装 ffmpeg";;
        esac
        command -v ffmpeg >/dev/null 2>&1 && ok "ffmpeg 安装成功" || warn "ffmpeg 仍不可用，视频解析功能将受限"
    else
        warn "已跳过；需要视频解析时请手动安装 ffmpeg"
    fi
fi

# ---------------------- 配置 .env（MX_APIKEY） ----------------------
step "配置 .env"
ENV_FILE="$WORKDIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$WORKDIR/.env.example" ]]; then
        cp "$WORKDIR/.env.example" "$ENV_FILE"
        ok "已从 .env.example 创建 .env"
    else
        printf '# 七专家分析师 Agent 环境变量\nMX_APIKEY=\n' > "$ENV_FILE"
    fi
fi

read_key_from_env() { grep -E "^MX_APIKEY=" "$ENV_FILE" | head -1 | cut -d= -f2-; }
CUR_KEY="$(read_key_from_env)"
NEW_KEY="$CUR_KEY"
if [[ -n "$APIKEY_ARG" ]]; then
    NEW_KEY="$APIKEY_ARG"
    info "使用命令行传入的 API Key"
elif [[ -n "$CUR_KEY" ]]; then
    : # .env 已有 key，沿用
elif [[ -n "$DEFAULT_KEY" ]]; then
    NEW_KEY="$DEFAULT_KEY"
    info "使用内置默认 API Key"
fi
if [[ -n "$NEW_KEY" && "$NEW_KEY" != "$CUR_KEY" ]]; then
    # 写回 .env（替换或追加 MX_APIKEY 行）
    if grep -qE "^MX_APIKEY=" "$ENV_FILE"; then
        # 跨平台就地替换：写到临时文件再覆盖
        ESC_KEY=$(printf '%s' "$NEW_KEY" | sed 's/[&/\]/\\&/g')
        sed "s|^MX_APIKEY=.*|MX_APIKEY=$ESC_KEY|" "$ENV_FILE" > "$ENV_FILE.tmp" && mv "$ENV_FILE.tmp" "$ENV_FILE"
    else
        printf 'MX_APIKEY=%s\n' "$NEW_KEY" >> "$ENV_FILE"
    fi
    ok "MX_APIKEY 已写入 .env"
else
    [[ -z "$NEW_KEY" ]] && warn "MX_APIKEY 为空，mx-* 数据工具将无法使用，请稍后编辑 .env"
fi

# ---------------------- 修正 agent 定义：硬编码路径 + API Key ----------------------
step "修正 agent 定义（硬编码路径 / API Key）"
AGENTS_DIR="$WORKDIR/.qoder/agents"
KEY_FOR_MD="$(read_key_from_env)"
changed=0
while IFS= read -r -d '' f; do
   bak="$f.bak.$(date +%s)"
    cp "$f" "$bak"
    # 1) 绝对路径替换：旧路径 -> 当前工作区路径
    if [[ "$WORKDIR" != "$OLD_PATH" ]] && grep -qF "$OLD_PATH" "$f"; then
        # 用 awk 处理含特殊字符的路径，避免 sed 转义地狱
        # 纯字符串匹配（index）替换，避免路径含正则元字符出错；循环替换一行内所有出现
        awk -v o="$OLD_PATH" -v n="$WORKDIR" '{ while((i=index($0,o))>0) $0=substr($0,1,i-1) n substr($0,i+length(o)); print }' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
        info "  路径已更新: $(basename "$f")"
        changed=1
    fi
    # 2) API Key 同步：把 export MX_APIKEY=<任意值> 统一替换为 .env 里的值
    if [[ -n "$KEY_FOR_MD" ]]; then
        if grep -qE "export MX_APIKEY=" "$f"; then
            # 匹配 export MX_APIKEY=<值>，保留前缀后接新 key 再接行尾（RSTART-1 为匹配前长度）
            awk -v k="$KEY_FOR_MD" '{ if (match($0,/export MX_APIKEY=[^ "]*/)) { $0=substr($0,1,RSTART-1) "export MX_APIKEY=" k substr($0,RSTART+RLENGTH) } print }' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
            info "  API Key 已同步: $(basename "$f")"
            changed=1
        fi
    fi
    [[ "$changed" = 0 ]] || changed=1
    rm -f "$bak"   # 无改动或处理完成后清理（如需保留备份可注释此行）
done < <(find "$AGENTS_DIR" -type f -name '*.md' -print0)
[[ "$changed" = 1 ]] && ok "agent 定义已适配当前机器" || ok "agent 定义无需改动"

# ---------------------- 让 agent 使用虚拟环境（可选）----------------------
if [[ "$USE_VENV" = 1 ]]; then
    step "配置 agent 调用虚拟环境"
    if ask "是否将 agent 定义中的 python3 命令指向虚拟环境解释器（$WORKDIR/.venv/bin/python），以保证 agent 运行时使用已装依赖？"; then
        VENVPY="$WORKDIR/.venv/bin/python"
        while IFS= read -r -d '' f; do
            awk -v p="$VENVPY" '{ gsub(/python3 /, p " "); print }' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
        done < <(find "$AGENTS_DIR" -type f -name '*.md' -print0)
        ok "已将 .qoder/agents/*.md 中的 python3 指向 $VENVPY"
    else
        warn "未替换。agent 运行前请确保 shell 已激活虚拟环境: source \"$WORKDIR/.venv/bin/activate\""
    fi
fi

# ---------------------- 自检 ----------------------
step "自检"
fail=0
"$PY" -c "import requests, pandas; print('  核心库 requests/pandas 导入 OK')" || fail=1
if [[ -f "$WORKDIR/mx-data/mx_data.py" ]]; then
    "$PY" "$WORKDIR/mx-data/mx_data.py" --help >/dev/null 2>&1 \
        && info "  mx_data.py 可执行" || warn "  mx_data.py --help 未通过（可能无 --help，属正常）"
fi
[[ "$fail" = 1 ]] && warn "部分核心库导入失败，请检查依赖" || ok "自检通过"

# ---------------------- 总结 ----------------------
step "安装完成"
cat <<EOF
工程目录:   $WORKDIR
Python:     $PY
${USE_VENV:+虚拟环境:   $WORKDIR/.venv (source 该目录下 activate 以激活)}
API Key:    $([ -n "$KEY_FOR_MD" ] && echo '已配置' || echo '未配置（请编辑 .env 填入 MX_APIKEY）')

后续:
  - 在 Qoder 中打开本目录作为工作区，agent(seven-experts-analyst) 与 skill 即自动加载
  - 如未配置 API Key，编辑 $WORKDIR/.env 填入 MX_APIKEY 后重跑本脚本
  - 视频解析需 ffmpeg（$([ "$(command -v ffmpeg >/dev/null && echo OK || echo 缺失)" = OK ] && echo 已装 || echo 缺失))
EOF
ok "全部就绪 ✅"
