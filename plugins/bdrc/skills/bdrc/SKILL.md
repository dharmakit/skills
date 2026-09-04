---
name: bdrc
description: >
  BDRC（佛教数字资源中心）文献搜索与 PDF 下载。
  搜索藏文／中文关键词 → 浏览结果 → 下载 PDF。
  支持单篇下载、搜索浏览选择、批量下载三种模式。
  当用户说「bdrc」「下载藏文文献」「下载佛典」「搜藏文文献」「藏文 PDF」
  「/bdrc」，或给出一个 MW 编号要求取 PDF 时触发。
  下载需要用户自己的 BDRC token（走 ~/.config/bdrc/token 或环境变量
  BDRC_TOKEN）；只做搜索浏览则无需 token。
allowed-tools: Bash(bdrc-cli.sh:*) Bash(mkdir:*) Bash(curl:*) Bash(file:*) Bash(python3:*)
---

# BDRC 文献搜索与下载

## 关键约束

- **永远不要把 PDF URL 送进浏览器**。IIIF 的 download endpoint 直接 stream PDF，
  会让 headless 浏览器的 dump-dom 卡死。
- 搜索结果页与文献详情页是 SPA，用 headless 浏览器 `--dump-dom` 拿渲染后的 HTML，
  再用正则解析。
- **Volume ID 走 BDRC LDS-PDI 的 JSON-LD API**，比解析 HTML 稳定：
  `curl -H "Accept: application/ld+json" https://ldspdi.bdrc.io/resource/{MW|W|I}.jsonld`
- PDF 下载全部走 `bdrc-cli.sh download`（内部是 curl 加 Bearer token）。

## 环境

```bash
CLI="${CLAUDE_PLUGIN_ROOT}/skills/bdrc/bdrc-cli.sh"

# 下载存放目录，按自己的习惯设；未设时脚本用当前目录
BDRC_DIR="${BDRC_DIR:-./bdrc-downloads}"

# headless 浏览器，按平台自行指定
#   macOS   /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
#   Linux   google-chrome / chromium
CHROME="${CHROME:-google-chrome}"
```

## 拿 token（每约 2 小时一次）

搜索浏览不需要 token，**只有下载 PDF 需要**。

token 来自 BDRC 单页应用经 Auth0 登录后写在 localStorage 里的 JWT：

1. 在任意已登录 BDRC 的浏览器里打开 DevTools → Console
2. 运行 `localStorage.getItem('access_token')`
3. 复制引号之间的 JWT
4. 运行 `bdrc-cli.sh token <JWT>` 写入缓存

有效期约 2 小时（看 JWT 的 `exp` claim）。也可以直接 `export BDRC_TOKEN='...'`，
环境变量优先于缓存文件。

批量下载前先跑一次 `bdrc-cli.sh token`（不带参数）做有效性检查。

## 模式路由

| 用户给了什么 | 模式 | 流程 |
|---|---|---|
| MW 编号（如 MW1NLM2145） | 单篇下载 | JSON-LD API 拿 Volume → 下载 |
| 搜索关键词 | 搜索浏览 | dump-dom 搜索页 → 解析 → 用户选 → 下载 |
| 关键词 + 「全部下载」／「批量」 | 全自动 | 搜索 → 建索引 → 逐篇下载 |

## 模式一：单篇下载

1. **JSON-LD 拿 Volume ID**：

```bash
curl -sL -H "Accept: application/ld+json" \
  "https://ldspdi.bdrc.io/resource/{MW_ID}.jsonld" -o /tmp/mw.jsonld
```

解析路径：`@graph` 里找 `bdr:{MW_ID}` 节点 → `instanceHasReproduction`
→ 找 ID 以 `W` 开头（非 `WA`）的 ImageInstance → 再取 `W.jsonld`
→ 该节点的 `instanceHasVolume` 就是 Volume 列表。
同一节点的 `numberOfVolumes` 给卷数，MW 节点的 `extentStatement` 给页数。

2. **API 不通时回退**到 dump-dom 详情页，grep `bdr:I[0-9A-Z_]+` 取 Volume ID。

3. **下载**：

```bash
"$CLI" download {VOLUME_ID} {PAGE_RANGE} "$BDRC_DIR/{主题}/{MW}_{简称}.pdf"
```

多卷本逐卷下，命名 `{MW}_v{NN}_{slug}.pdf`。

4. 报告文件大小、路径、Volume ID。

## 模式二：搜索浏览

1. **构造搜索词**。中文命中率低，**藏文 Wylie 转写覆盖面更全**。
   太短的词（如 `'jam dkar`）会匹配六千条以上，加上文体名（`sgrub thabs` 修法）更精准。

2. **抓搜索结果页**：

```bash
QUERY=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$KEYWORDS")
"$CHROME" --headless --disable-gpu --no-sandbox --virtual-time-budget=25000 \
  --user-data-dir=$(mktemp -d) \
  --dump-dom "https://library.bdrc.io/osearch/search?q=${QUERY}&page=1" > /tmp/p1.html
```

注意：URL 用 `/osearch/search?q=`，`/search?q=` 只会返回 SPA 空壳。
长调用建议套超时防卡死，并且每次用独立的 `--user-data-dir` 避免并发与旧状态干扰。

3. **解析每张卡片**。结构是 `<div class="result Instance">`（也有 PartTypeText /
   PartTypeChapter），其中：

```
<span class="RID">MW|...|</span>                       ← MW 号或章节级 RID
<span lang="bo">藏文标题</span>                          ← 单语标题
<span lang="bo-x-ewts"><em>WYLIE</em></span>            ← Wylie 标题
<span>open access | archive.org | not available</span>  ← 可获取状态
<span class="quality">excellent | best | good OCR…</span>
```

4. **翻页**：每页 20 条，追加 `&page=N`，翻到零卡片或重复率过高为止。

5. **去重分类**：work 级 MW 的 RID 不带 `_` 后缀；章节级 RID 形如
   `MW{X}_{hash}`，其母作品是 `split('_')[0]`。跨 page 与跨关键词都要去重。

6. **建索引文件**记录搜索词、日期、结果数，分「已下载」「未下载」两张表，
   列出 MW、标题、访问状态、Volume ID。

7. 把结果做成简洁表格给用户挑，标注 open access / archive.org / not available。

## 模式三：批量下载

同模式二做完搜索与索引，然后筛出 open access 的逐篇下载，
`not available` 跳过，失败的在索引里记原因但不中断整批，最后汇总成功／失败／跳过与总大小。

单条超时建议设 15 分钟，超大全集首批可以用 `--max-pages` 设上限。

**请节制并发与频率**——BDRC 是公益机构，别把它当爬取目标。

## 命名规则

- 单卷：`{MW}_{slug}.pdf`
- 多卷：`{MW}_v{NN}_{slug}.pdf`

slug 取藏文 Wylie 或中文简称，40 字符以内，清掉非法字符。

## 搜索技巧

- **Wylie 全称 > Wylie 简称 > 中文**
- 同一概念多试几个变体（`byams chos sde lnga` / `byams pa'i chos sde lnga` /
  `byams chos lnga`）
- work 级卡片的标题含关键词 = 题目层命中，较强；否则是全文命中，可能落在某个章节里
- 排除误命中要看音节边界：`བྱམས་` 前面若接着别的藏文字母（如 `འབྱམས`），
  那是嵌在另一个词里，应排除

## 错误处理

| 情况 | 处理 |
|---|---|
| exit 1，token expired | 让用户重新取 token：`bdrc-cli.sh token <NEW_JWT>` |
| exit 2，下载到的不是 PDF | URL 或 Volume ID 错，回 JSON-LD API 核对 |
| exit 3，生成超时（>3 分钟） | 大部头分段下：`1-100` / `101-200`…；调低页数上限 |
| 文献标记 not available | 跳过，在索引里注明 |
| archive.org 的扫描件 | 仍可试 IIIF endpoint，失败再走 archive.org 通道 |
| 文件已存在 | 默认跳过（大于 1KB 者）；用户明确要求重下时先删 |
| dump-dom 拿到零张卡片 | 该页超出范围，或渲染没完成，翻前一页或加长 virtual-time-budget |
