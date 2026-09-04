---
name: cbeta
description: >
  CBETA 汉文大藏经官方 API（法鼓文理学院 DILA，免 key、免注册、纯 curl）。
  取经文全文、取册／页／行引用锚点（linehead）、查经目元数据（译者／年代／卷数／部类）、
  全文检索并拿 KWIC 高亮上下文。
  当用户说「取某经全文」「取某卷原文」「这句在大正藏第几页」「查某经的译者／卷数／年代」
  「要引用锚点」「要 linehead」「/cbeta」，或需要精确到册页行的学术引用时触发。
  也适用于：核对某部经里有没有某句（负向排查）、为讲稿与译稿核证引文。
allowed-tools: Bash(curl:*) Bash(python3:*)
---

# CBETA 汉文大藏经 API

法鼓文理学院提供的公开 API，无需 key、无需注册，`curl` 直接调。

## 30 秒速查

```bash
BASE="https://cbdata.dila.edu.tw/stable"
REF="Referer: https://cbetaonline.dila.edu.tw/"

# 检索 + KWIC 高亮上下文（默认用这个）
curl -s -H "$REF" --get "$BASE/search/all_in_one" \
  --data-urlencode "q=色不異空" --data-urlencode "rows=5"

# 限定某部经
curl -s -H "$REF" --get "$BASE/search/all_in_one" \
  --data-urlencode "q=前九地" --data-urlencode "work=T1580"

# 取单卷全文（返回带行锚的 HTML，要纯文本需自行剥标签）
curl -s -H "$REF" --get "$BASE/juans" \
  --data-urlencode "work=T0251" --data-urlencode "juan=1"

# 书目元数据（标题／部类／译者／年代／字数／卷列表）
curl -s -H "$REF" "$BASE/works?work=T0251"
```

## 五条铁律

1. **域名认准 `cbdata.dila.edu.tw`**。`cbetaonline.cn` 全域已废弃（2026-08 实测无法连接），
   `Referer` 也必须填台湾站 `https://cbetaonline.dila.edu.tw/`，缺了会被拒。

2. **`/search/kwic` 除 `work` 外还必须带 `juan`**。缺 `juan` 时返回
   `{"success":false}` 却**不报错**，静默给出空结果表，极易误判成「查无此句」。
   要单经范围内的 KWIC，改用 `all_in_one` 加 `work=` 参数，它不需要 `juan`。

3. **中文 query 一律用 `--data-urlencode`**，别手拼 URL。

4. **没有语义检索**。`similar` 端点只是词项模糊匹配，并非 embedding。需要语义检索
   可另走 Dharmamitra（`POST https://dharmamitra.org/api-search/primary/`，免 key）。

5. **`linehead` 是学术引用锚点**。形如 `T05n0220_p0022b03`，即册-经-页-栏-行。
   注意 `all_in_one` 返回的 linehead 是**命中起处**那一行——探针若不是以查询词打头，
   行号会落在查询词之前一两行。要精确到查询词所在行，让探针以查询词开头，
   或先定经号再用 `work=` 二次收窄。

## all_in_one 的返回结构

顶层有 `num_found`、`total_term_hits`、`results`。每条 `results[]` 给出
`work`（经号）、`juan`（卷）、`title`（经名）、`byline` 与 `creators`（译者）、
`time_dynasty` / `time_from` / `time_to`（年代），命中上下文在 `kwics` 里再套一层：

```
results[].kwics.results[] = { vol, lb, kwic, linehead, offset_in_text_with_punc }
```

`kwic` 字段里命中词用 `<mark>` 包着，取纯文本要剥掉。取锚点的路径是
`results[0].kwics.results[0].linehead`——**别在顶层找 linehead，那里没有**。

```bash
curl -s -H "$REF" --get "$BASE/search/all_in_one" \
  --data-urlencode "q=色不異空" --data-urlencode "rows=2" \
| python3 -c "
import json,sys
for r in json.load(sys.stdin)['results']:
    for k in r['kwics']['results']:
        print(k['linehead'], r['work'], r['title'], k['kwic'])
"
```

## 负向排查的判据

要断言「某部经里没有某句」时，单条零命中不足以下结论。汉文检索里标点与插字都会断词，
必须换 3–5 个不含标点的连续字串交叉验证，全部零命中才可下结论。

CBETA 正文含新式标点，检索时标点通常被忽略（`色不異空。空不異色` 与
`色不異空空不異色` 都能命中）。若同时在用本地字面匹配的检索工具（如 FTS5），
那边的行为**不是这样**，别把本地的零命中当成 CBETA 也没有。

## 各端点分工

| 要什么 | 用哪个端点 |
|---|---|
| 这句出自哪部经 | `/search/all_in_one` |
| 精确到册页行的引用锚点 | `/search/all_in_one` 取 `linehead` |
| 某部经／某卷全文 | `/juans` |
| 译者是谁、有几卷、什么年代 | `/works` |
| 确认某经里没有某句 | `/search/all_in_one` 加 `work=`，多词形交叉 |

## 配套

本套件里另有 `cbeta-local` 技能，是本地 SQLite FTS5 检索，单次几毫秒，
比走 API 快两个数量级，适合高频检索；代价是要自己下载 CBETA 官方 XML 建一次索引。

分工：高频检索走本地，取整卷全文、书目元数据、跟官方最新版核对走本 API。
本地库自带精确到行的锚点，所以定位到行**不需要**再回查这里。
