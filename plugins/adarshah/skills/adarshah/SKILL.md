---
name: adarshah
description: >
  Adarshah 藏文大藏经全文检索（Dharma Treasure Corp，站点免费、无需注册）。
  覆盖 14+ 个语料库：德格／江／拉萨／那塘／北京／托格／普扎／塔波等甘珠尔，
  德格与北京丹珠尔，以及宗喀巴、多罗那他、八世噶玛巴、果然巴、释迦确丹、
  萨迦诸祖、历代法王等祖师文集，《大宝伏藏》。
  当用户说「查找藏文 X」「adarshah 搜 X」「在大藏经里搜 X」「查这句藏文出处」
  「/adarshah」，或给出一句藏文要求追查出处时触发。
  也适用于：判断一句藏文是原典直引还是后世改写、做多版本对照、
  为某段祖师注释追溯其所本的印度释论。
allowed-tools: Bash(adarshah-cli.py:*) Bash(python3:*) Bash(curl:*)
---

# Adarshah 藏文大藏经全文检索

纯 Python 标准库，无需安装依赖，无需 API key。

```bash
CLI="${CLAUDE_PLUGIN_ROOT}/skills/adarshah/adarshah-cli.py"
```

## 四个子命令

### `count <短语>` — 看命中量与 kdb 分布

```bash
python3 "$CLI" count "ཇི་སྙེད་སུ་དག་ཕྱོགས་བཅུའི་འཇིག་རྟེན་ན"
```

用来决定要不要展开全列表。超过 200 条就该精化短语或补上下文词。

### `search <短语>` — 拉全部 phrase-match 出处

```bash
python3 "$CLI" search "ཇི་སྙེད་སུ་དག་ཕྱོགས་བཅུའི་འཇིག་རྟེན་ན"
python3 "$CLI" search "ཇི་སྙེད་སུ་དག" --format json
```

按 kdb 分组输出（命中多的在前），每条标注 sutra 编号、部类、函、pb 页码、tname。

**默认 `wildcard=true`（近似 phrase 匹配）**。省掉这个参数的话 esSearch 会按 token
拆词海捞——54 条真实命中能被烧成一万条以上的噪声。确需 OR 检索时用 `--no-wildcard`。

### `divisions <kdb>` / `sutra-info <kdb> <sutra>` — 目录浏览

```bash
python3 "$CLI" divisions degekangyur          # 列德格甘珠尔全部函
python3 "$CLI" sutra-info degetengyur D2679   # 看某部的科判／标题结构
```

### `texts <kdb> <sutra> [--out <file>]` — 提取某部全文

```bash
python3 "$CLI" texts degetengyur D2679
python3 "$CLI" texts degetengyur D2679 --out D2679.md
python3 "$CLI" texts degetengyur D2679 --format json
```

内部先调 `sutraInfo` 拿 `heads[0].pbName` 起始页码，再调 `/sutra/texts` 自动翻页。
输出 Markdown 带 pb 页码标记与标题层级。

## 已知坑

1. **wildcard 在 searchAfter 翻页后失效**——后端 bug。CLI 内部绕开的办法是不用
   searchAfter，改从 esCount 的 `count_kdb` aggregation 取每个 kdb 的命中数，
   再按 `kdb=<x>` 分批 esSearch（单个 kdb 命中数几乎都 ≤20，单页即够）。
2. **后端 size 硬编码 20**——传 `size=100` 或 `limit=100` 都会被忽略。少数单 kdb
   命中超过 20 的情况需要再细化短语。
3. **apiKey 是公开的**——它硬编码在站点前端 JS 里，对所有访客原样暴露，
   属于站点标识而非个人凭证，无需保密，也无需自行申请。
4. **token 字段用不上**——检索与取文接口完全开放；token 那一层是给「个人书签／
   userData」用的可选层，本 CLI 不碰。
5. **藏文直接传字符**，别用 `\uXXXX` 转义手拼。曾有把 `0f9f`（ྟ）误写成 `0fa9`（ྩ）
   而查成另一个词、返回零命中的先例，很容易误判成「原典里没有这句」。

## License 边界

Adarshah 的 toolbox 页面标注 CC BY-NC-ND 4.0。取数据做个人研究与离线阅读没问题，
商用或二次发布数据本身需要避开。本 skill 只是 API 客户端，不附带任何语料。

## 已知 kdb 代号

| 类别 | 代号 |
|---|---|
| 甘珠尔 | `degekangyur` `jiangkangyur` `lhasakangyur` `narthangkangyur` `pekingkangyur` `stogkangyur` `phugdrakkangyur` `tabokangyur` |
| 丹珠尔 | `degetengyur` `pekingtengyur` |
| 历代法王 | `dalailamasungbum` `panchenlamasungbum` `tsongkhapa` `8thkarmapa` |
| 萨迦 | `ngawangkungalodroe` `ngawangkungasonam` `dragpagyaltsen` `sonamgyaltsen` `gorampa` `shakyachogden` |
| 觉囊 | `taranatha` `dolpopa` `matipanchen` |
| 伏藏 | `terdzo`（《大宝伏藏》） |
| 其他 | `padkar` `tshalminpa` `choglenamgyal` `chodrapal` `lodropal` `gharungpa` `nyadbonkungapal` `yontenbzangpo` `yeshegyatsho` `thugsrjebrtsongrus` `sonamgragpa` `logrosgragspa` `sakyalotsawa` |

这份清单不完整。新代号可从 `count` 输出的 buckets 里认出来，或到
`https://online.adarshah.org/search.html` 看下拉菜单的 `data-kdb` 属性。

## 典型场景

**核对一句藏文是不是经文原文**——`search` 跑完整列表，看命中是否落在甘珠尔／丹珠尔，
据此判断直引还是后世改写。

**追溯祖师注释的来源**——把那句藏文丢给 `search`，看 `degetengyur` 的命中，
即可定位其所本的印度释论原句。

**多版本对照**——一次 `search` 同时给出德格、江、拉萨等版的 pb 页码。

**短语校勘**——先 `count` 看版本分布。多版本一致则文本稳定；仅个别版本独有的读法
需要进一步校勘。

## 写检索总结时的约束

归纳检索结果时，避免出现「印证了你之前说的 X」「呼应你提过的 Y」这类对用户的归因，
除非能当场检索到具体出处。属于自己的现场推论，用「一个观察是 X」「看着像 Y」
挂在自己名下，别说成是用户的既有判断。

## 接口契约

CLI 已经封装好，一般无需直接调用。

| 接口 | 路径 | 必传字段 |
|---|---|---|
| esCount | `/plugins/adarshaplugin/file_servlet/search/esCount` | `apiKey, text, wildcard` |
| esSearch | `/plugins/adarshaplugin/file_servlet/search/esSearch` | `apiKey, text, wildcard, [kdb]` |
| listDivisions | `/plugins/adarshaplugin/file_servlet/listDivisions` | `apiKey, kdb` |
| sutraInfo | `/plugins/adarshaplugin/file_servlet/sutraInfo` | `apiKey, kdb, sutra` |
| sutra/texts | `/plugins/adarshaplugin/file_servlet/sutra/texts` | `apiKey, kdb, sutra, page, size(=20), lang(=bo)` |

POST form-urlencoded，返回 JSON。响应里 `cts_status: fail` 加 `cts_message` 即为报错。

> **`/sutra/texts` 的参数名陷阱**：起始页码字段叫 `page`，而非 `pb` / `startPb` /
> `start_pb`，并且必须同时传 `size=20` 和 `lang=bo`。这是从前端 JS 逆向确认的。
