---
name: bdrc-es
description: >
  BDRC Elasticsearch 检索（autocomplete.bdrc.io，免注册、免 token）。
  搜 BDRC 全库书目（书名／篇名／作者）拿到可下载的 Instance MW 号，
  交给 bdrc 技能下载 PDF；也能全文检索已录入的 etext。
  当用户说「BDRC 搜 X」「在 BDRC 找 X」「查 X 在 BDRC 哪本书里」「bdrc-es」，
  或给出一句藏文书名／篇名要求找出处和可下载版本时触发。
  尤其适合：短篇愿赞、赞颂、释文被捆在 thor bu 合集里，
  Instance 列表查无 ≠ 不存在的场景——搜 PartTypeText 再顺 inRootInstance
  摸到母合集去下载。
  与 adarshah 的区别：adarshah 只覆盖大藏经全文，本技能覆盖 BDRC 全部书目、
  扫描本与人物，主打「找到可下载的版本」。
allowed-tools: Bash(python3:*) Bash(curl:*)
---

# bdrc-es — BDRC Elasticsearch 检索

BDRC 有一个 ES index `bdrc_prod`，索引了全部资源（书目／扫描本／篇目／人物／全文）。
本工具的主用途是：**搜书目 → 拿可下载的 Instance MW 号 → 交 `bdrc` 技能下 PDF**。

免注册、免 token。

## 运行

```bash
CLI="${CLAUDE_PLUGIN_ROOT}/skills/bdrc-es/bdrc-es-cli.py"

python3 "$CLI" search "རྟེན་འབྲེལ་བསྟོད་པ་"      # 藏文自动转 Wylie（需 pyewts）
python3 "$CLI" search "rten 'brel bstod pa"        # 直接传 Wylie，无需任何依赖
```

书目字段存的是 EWTS Wylie，所以藏文 Unicode 输入需要先转写。转写靠 `pyewts`，
装不上就直接传 Wylie。

`pyewts` 是个老包，依赖已被新版 setuptools 移除的 `pkg_resources`，装法是：

```bash
pip install 'setuptools<70' wheel
pip install --no-build-isolation pyewts
```

## 三个命令

```bash
# search — 搜书目，给出可下载的 MW 号（主力）
python3 "$CLI" search "<书名/篇名>"                # 默认搜 Instance + PartTypeText
python3 "$CLI" search "<书名>" --phrase            # 短语精确，保词序，最准
python3 "$CLI" search "<人名>" --type Person       # 搜作者，给 P 号
python3 "$CLI" search "<词>" --type all --size 30  # 全类型
python3 "$CLI" search "<词>" --format json         # JSON 输出

# count — 命中数与按 type 的分布（看东西落在 Instance 还是 PartTypeText）
python3 "$CLI" count "<书名/篇名>"

# fulltext — etext 全文检索（传 Unicode 藏文，仅覆盖有 OCR／录入文本的部分）
python3 "$CLI" fulltext "བྱང་ཆུབ་ཀྱི་སེམས" --snippets 2
```

## 结果怎么用

`search` 每条命中都给出可下载母本的 MW 号和链接：

- **Instance**：`_id` 本身就是 MW 号
- **PartTypeText**（短篇愿赞常在这一层）：取 `inRootInstance` 的 MW 号，
  那是它所在的合集

拿到 MW 号后交给 `bdrc` 技能下载 PDF。

## 两个坑

1. **书名搜 Wylie，全文搜 Unicode**。书目层的 `prefLabel_bo_x_ewts` 是 EWTS Wylie，
   只有 etext 层的 `chunks.text_bo` 才是 Unicode 藏文。字段搞错会静默返回 0 命中。

   短篇愿赞经常不作为独立 Instance 存在——**别拿 Instance 层的「查无」下否定结论**，
   要再搜一次 PartTypeText。

2. **DNS 污染**。`autocomplete.bdrc.io` 在部分地区会被解析到错误的 IP 段、SSL 连接被重置。
   脚本内部用 DoH（dns.google）取真实 AWS IP，再用 `curl --resolve` 绕过。
   若 DoH 本身也被拦，脚本会明确报错。

## 实现备忘

HTTP 全部走 `curl` 子进程（为了复用 `--resolve` 绕污染），没用 urllib，
避开 SNI 与 SSL 的麻烦。
