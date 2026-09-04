---
name: cbeta-local
description: >
  CBETA 汉文佛典本地全文检索（SQLite FTS5 trigram，毫秒级，不联网）。
  每条结果直接给出精确到行的引用锚点（如 T30n1579_p0279a08），无需回查 API。
  当用户说「查一下汉文大藏经」「CBETA 里搜 X」「这句汉文出处」「查这句经文」
  「大藏经全文检索」「/cbeta-local」，或给出一句汉文经文要求找出处时触发。
  也适用于：核对某句是否原典直引、确认某部经里有没有某句（负向排查）、
  为讲稿与译稿核证引文、判断某说法出自本论还是后世注疏。
  需自备索引库——用附带的 cbeta_index.py 从 CBETA 官方 XML P5 建，
  数据不随插件分发。
allowed-tools: Bash(python3:*)
---

# cbeta-local — CBETA 汉文佛典本地检索

只读本地 SQLite。**不联网、不烧 token、单次几毫秒。**

## 首次使用：建索引

本插件**不附带经文数据**，只附带建索引与检索的脚本。CBETA 的经文自己去官方仓库拿：

```bash
# 1. 取官方 XML P5（约 1.2 GB）
git clone --depth 1 https://github.com/cbeta-org/xml-p5.git

# 2. 建索引
python3 "${CLAUDE_PLUGIN_ROOT}/skills/cbeta-local/cbeta_index.py" build xml-p5 -o ~/.cbeta/cbeta.sqlite

# 只要大正藏的话（快很多）
python3 "${CLAUDE_PLUGIN_ROOT}/skills/cbeta-local/cbeta_index.py" build xml-p5 --canon T -o ~/.cbeta/cbeta.sqlite

# 3. 看看建出了什么
python3 "${CLAUDE_PLUGIN_ROOT}/skills/cbeta-local/cbeta_index.py" info -d ~/.cbeta/cbeta.sqlite
```

建库耗时随机器与范围差别很大，全藏是几十分钟量级，产出库比源 XML 略大。
建好后设一次环境变量就不用每次带 `-d`：

```bash
export CBETA_DB=~/.cbeta/cbeta.sqlite
```

数据库路径的查找顺序是：`-d` 参数 → `$CBETA_DB` → `./cbeta.sqlite` → `~/.cbeta/cbeta.sqlite`。

## 检索

```bash
LOCAL="${CLAUDE_PLUGIN_ROOT}/skills/cbeta-local/cbeta_local.py"

python3 "$LOCAL" "色不異空"                 # 基本检索，默认 5 条
python3 "$LOCAL" "色不異空" -n 20 -c 300    # -n 条数，-c 上下文字数
python3 "$LOCAL" "前九地" -w T1580          # 限定经号（T1580 与 T30n1580 都认）
python3 "$LOCAL" "境行果" -t 瑜伽           # 限定书名含某词
python3 "$LOCAL" "如是我聞" --count         # 精确命中数
python3 "$LOCAL" "涅槃" --slow              # 少于 3 字的查询需显式放行
```

每条结果给出经号、书名、卷次，以及**精确到行的锚点**：

```
[1] T1579 瑜伽師地論 卷1
    T30n1579_p0279a13
    五識相應、意、有尋伺等三、… 有依、及無依，是名【十七地】。
```

锚点格式 `T30n1579_p0279a13` = 册-经-页-栏-行，是学术引用的标准锚点。
它由索引里的段内偏移映射算出，与 CBETA 官方 API 的结果一致，
**不需要联网回查**。

## 用法铁律：单条零命中不能下结论

trigram 是**字面连续匹配**，两个陷阱必踩：

1. **词间插一字就断**。原文「次六地是瑜伽行」，搜「六地是行」零命中。
2. **标点会断词**。原文写「有依、及無依」带顿号，搜「有依及無依」搜不到。

所以：

- **正面找**：一个词形没中就换一个，别急着说「库里没有」。
- **负向排查**（要断言某部经里「没有」某说法）：**必须用 3–5 个不含标点的连续字串
  交叉验证**，全部零命中才可下结论。例如要确认 T1580 里没有「前九地是三乘境」这一判摄，
  应分别查「三乘境」「後二地」「初九地」「九地是」「如是具三乘」五个词形加 `-w T1580`，
  每次不到十毫秒。
- 检索词用**繁体**（库里是繁体原文），**至少 3 个汉字**。
- **结果顺序是入库顺序，不是相关度排序**。字面精确匹配下所有命中都是完整匹配，
  bm25 没有区分度，所以没做相关度排序。要看全貌就加大 `-n`。

## 索引里有什么、没什么

建索引时按以下规则处理 CBETA 的 TEI 标记：

- `<note>` 校勘注与夹注**一律排除**——否则检索会命中注文而非正文，
  这是这类索引最常见的污染源
- `<app><lem>底本</lem><rdg>异读</rdg></app>` 取 `lem` 弃 `rdg`，
  即索引的是底本读法。**要查异读得另找对勘本，本库给不了**
- `<g ref="#CB00768">𡁠</g>` 外字标签内自带 Unicode，直接收进正文
- `<lb n="0279a13"/>` 逐行记录，段内建立「字符偏移 → 行锚」映射，
  命中时据此还原精确行号

## 与 cbeta 插件的分工

| 要什么 | 用哪个 |
|---|---|
| 这句出自哪部经 | 本插件（本地，几毫秒） |
| 精确到册页行的引用锚点 | 本插件（已内建，不用联网） |
| 某部经／某卷的完整原文 | `cbeta` 插件的 `/juans` |
| 译者、卷数、年代等书目元数据 | `cbeta` 插件的 `/works` |
| 跟官方最新版本核对 | `cbeta` 插件 |

本地库是建库那天的快照，CBETA 每年出新版。涉及版本差异的场合回 `cbeta` 插件核。
