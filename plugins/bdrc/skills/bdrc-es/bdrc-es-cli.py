#!/usr/bin/env python3
"""bdrc-es-cli — BDRC Elasticsearch 检索 CLI（autocomplete.bdrc.io/msearch）

一个 index `bdrc_prod` 索引了 BDRC 全部资源。本工具的主用途是：
搜书目（书名/篇名/作者）→ 拿到可下载的 Instance MW 号 → 交给 skill `bdrc` 下载 PDF。

为什么需要它：短篇的愿赞、赞颂、释文多半不单独成书（Instance），而是捆在
thor bu 合集里，作为一条 PartTypeText 存在。直接查 Instance 列表「查无」
≠ 不存在；得搜 PartTypeText，再顺 inRootInstance 摸到所在合集去下载。

三个命令：
  search   搜书目，给出可下载 MW 号（默认搜 PartTypeText + Instance）
  count    命中数 + 按 type 分布
  fulltext etext 全文检索（仅覆盖有 OCR/录入文本的 etext）

两个 BDRC ES 的坑（已在代码里处理）：
  1. 书名字段 prefLabel_bo_x_ewts 存 EWTS Wylie，不是 Unicode 藏文。
     本工具自动把藏文输入转 Wylie（pyewts）；也可直接传 Wylie。
     全文字段 chunks.text_bo 才是 Unicode 藏文。
  2. autocomplete.bdrc.io 在国内网络被 DNS 污染。本工具用 DoH 取真实 IP，
     curl --resolve 绕过。HTTP 一律走 curl 子进程，避开 SNI/SSL 的麻烦。
"""

import argparse
import json
import re
import subprocess
import sys

HOST = "autocomplete.bdrc.io"
URL = f"https://{HOST}/msearch"
DOH = f"https://dns.google/resolve?name={HOST}&type=A"

TYPE_LABELS = {
    "Instance":          "版本/扫描本（可下载 PDF）",
    "PartTypeText":      "篇目（短篇愿赞常在此）",
    "PartTypeChapter":   "章节",
    "PartTypeVolume":    "卷册",
    "PartTypeSection":   "段落",
    "PartTypeTableOfContent": "目录",
    "PartTypeEditorial": "编辑说明",
    "PartTypeCodicologicalVolume": "实物卷册",
    "Etext":             "电子文本（OCR/录入，可全文搜）",
    "Person":            "人物/作者",
    "Place":             "地名",
    "Topic":             "主题",
    "Collection":        "丛书",
}

_TIBETAN = re.compile(r"[ༀ-࿿]")
_ip_cache = None


def has_tibetan(s: str) -> bool:
    return bool(_TIBETAN.search(s))


def to_wylie(text: str) -> str:
    """藏文 Unicode → EWTS Wylie。已是 Wylie 则原样返回。"""
    if not has_tibetan(text):
        return text.strip()
    try:
        import pyewts
    except ModuleNotFoundError:
        sys.exit(
            "输入是藏文 Unicode，但没装 pyewts 做转换。\n"
            "  办法 A：装 pyewts（它是老包，需要旧版 setuptools 提供 pkg_resources）：\n"
            "          pip install 'setuptools<70' wheel\n"
            "          pip install --no-build-isolation pyewts\n"
            "  办法 B：直接传 Wylie，如 'smon lam'"
        )
    return pyewts.pyewts().toWylie(text).strip()


def real_ip() -> str:
    """DoH 取 autocomplete.bdrc.io 的真实 IP，绕过 DNS 污染。"""
    global _ip_cache
    if _ip_cache:
        return _ip_cache
    for _ in range(3):  # DoH 偶发空响应，重试
        out = subprocess.run(
            ["curl", "-s", "-m", "15", DOH], capture_output=True
        ).stdout
        try:
            d = json.loads(out)
        except json.JSONDecodeError:
            continue
        for a in d.get("Answer", []):
            if a.get("type") == 1:
                _ip_cache = a["data"]
                return _ip_cache
    sys.exit(f"无法经 DoH 解析 {HOST} 真实 IP（DoH 也被挡？）")


def es(query: dict) -> dict:
    """发一个 msearch 查询，返回 responses[0]。"""
    ndjson = "{}\n" + json.dumps(query, ensure_ascii=False) + "\n"
    p = subprocess.run(
        ["curl", "-s", "-m", "30",
         "--resolve", f"{HOST}:443:{real_ip()}",
         "-H", "Content-Type: application/x-ndjson",
         "--data-binary", "@-", URL],
        input=ndjson.encode("utf-8"), capture_output=True,
    )
    if p.returncode != 0:
        sys.exit(f"curl 失败 (rc={p.returncode}): {p.stderr.decode()[:300]}")
    try:
        d = json.loads(p.stdout)
    except json.JSONDecodeError:
        sys.exit(f"响应非 JSON（前 300 字）：{p.stdout[:300]!r}")
    r = d["responses"][0]
    if r.get("status") not in (200, None):
        sys.exit(f"ES 返回 status={r.get('status')}: {json.dumps(r, ensure_ascii=False)[:400]}")
    return r


def _type(src: dict) -> str:
    """type 字段是数组，取首元素。"""
    t = src.get("type")
    return t[0] if isinstance(t, list) else (t or "?")


def _label_str(src: dict) -> str:
    pref = src.get("prefLabel_bo_x_ewts") or []
    alt = src.get("altLabel_bo_x_ewts") or []
    s = pref[0] if pref else (alt[0] if alt else "(无书名字段)")
    return s.strip()


def cmd_search(args):
    wylie = to_wylie(args.query)
    if args.type == "all":
        types = list(TYPE_LABELS)
    elif args.type == "bib":
        types = ["Instance", "PartTypeText"]
    else:
        types = [args.type]

    match_type = "phrase" if args.phrase else "best_fields"
    q = {
        "track_total_hits": True,
        "size": args.size,
        "query": {"bool": {
            "must": [{"multi_match": {
                "query": wylie,
                "fields": ["prefLabel_bo_x_ewts", "altLabel_bo_x_ewts"],
                "type": match_type,
                **({"operator": "and"} if not args.phrase else {}),
            }}],
            "filter": [{"terms": {"type": types}}],
        }},
        "_source": ["type", "prefLabel_bo_x_ewts", "altLabel_bo_x_ewts",
                    "inRootInstance", "scans_access", "etext_access",
                    "translator", "workIsAbout"],
    }
    r = es(q)
    hits = r["hits"]["hits"]
    total = r["hits"]["total"]

    if args.format == "json":
        json.dump(hits, sys.stdout, ensure_ascii=False, indent=2)
        return

    sys.stderr.write(f"[query] 藏→Wylie: {args.query!r} -> {wylie!r}  (match={match_type})\n")
    tv = total["value"]
    mark = "+" if total.get("relation") != "eq" else ""
    print(f"# 「{wylie}」命中 {tv}{mark} 条，显示前 {len(hits)}\n")
    for i, h in enumerate(hits, 1):
        s = h["_source"]
        t = _type(s)
        tl = TYPE_LABELS.get(t, t)
        print(f"{i:>2}. [{tl}]  _id={h['_id']}  score={h.get('_score') or 0:.1f}")
        name_label = "姓名" if t == "Person" else "书名"
        print(f"    {name_label}: {_label_str(s)}")
        tr = s.get("translator")
        if tr:
            print(f"    译者: {', '.join(tr) if isinstance(tr, list) else tr}")
        # 给出可下载的 MW 号
        if t == "Instance":
            dl = h["_id"]
        elif t == "PartTypeText":
            roots = s.get("inRootInstance") or []
            dl = roots[0] if roots else None
        else:
            dl = None
        if dl:
            sa = s.get("scans_access")
            sa_s = f"  scans_access={sa}" if sa is not None else ""
            print(f"    ↓ 可下载母本: {dl}{sa_s}")
            print(f"      https://library.bdrc.io/show/bdr:{dl}")
        print()


def cmd_count(args):
    wylie = to_wylie(args.query)
    q = {
        "track_total_hits": True, "size": 0,
        "query": {"multi_match": {
            "query": wylie,
            "fields": ["prefLabel_bo_x_ewts", "altLabel_bo_x_ewts"],
            "operator": "and",
        }},
        "aggs": {"by_type": {"terms": {"field": "type", "size": 40}}},
    }
    r = es(q)
    sys.stderr.write(f"[query] 藏→Wylie: {args.query!r} -> {wylie!r}\n")
    tv = r["hits"]["total"]["value"]
    mark = "+" if r["hits"]["total"].get("relation") != "eq" else ""
    print(f"「{wylie}」总命中: {tv}{mark}\n")
    print(f"{'type':24s} {'count':>7}  说明")
    print("-" * 70)
    for b in r["aggregations"]["by_type"]["buckets"]:
        k = b["key"]
        print(f"{k:24s} {b['doc_count']:>7}  {TYPE_LABELS.get(k, '')}")


def cmd_fulltext(args):
    # 全文走 Unicode 藏文，不转 Wylie
    bo = args.query
    if not has_tibetan(bo):
        sys.stderr.write("[warn] fulltext 检索的是 Unicode 藏文全文；你传的不像藏文，可能 0 命中。\n")
    inner = {"size": args.snippets,
             "_source": ["chunks.text_bo"],
             "highlight": {"fields": {"chunks.text_bo": {}},
                           "pre_tags": ["《"], "post_tags": ["》"]}}
    q = {
        "track_total_hits": True, "size": args.size,
        "query": {"nested": {
            "path": "chunks",
            "query": {"match_phrase": {"chunks.text_bo": bo}},
            "inner_hits": inner,
        }},
        "_source": ["etextNumber", "etext_vol", "volumeNumber",
                    "etext_instance", "etext_for_root_instance", "source_path"],
    }
    r = es(q)
    hits = r["hits"]["hits"]
    if args.format == "json":
        json.dump(hits, sys.stdout, ensure_ascii=False, indent=2)
        return
    tv = r["hits"]["total"]["value"]
    mark = "+" if r["hits"]["total"].get("relation") != "eq" else ""
    print(f"# 全文「{bo}」命中 {tv}{mark} 个 etext，显示前 {len(hits)}\n")
    for i, h in enumerate(hits, 1):
        s = h["_source"]
        inst = (s.get("etext_for_root_instance") or s.get("etext_instance") or ["?"])
        inst = inst[0] if isinstance(inst, list) else inst
        print(f"{i:>2}. _id={h['_id']}  vol={s.get('etext_vol') or s.get('volumeNumber')}")
        if inst and inst != "?":
            print(f"    所属扫描本: {inst}  https://library.bdrc.io/show/bdr:{inst}")
        # 高亮片段
        ih = h.get("inner_hits", {}).get("chunks", {}).get("hits", {}).get("hits", [])
        for x in ih[:args.snippets]:
            frag = x.get("highlight", {}).get("chunks.text_bo", [])
            for f in frag:
                print(f"      … {f.strip()[:140]} …")
        print()


def main():
    p = argparse.ArgumentParser(
        prog="bdrc-es-cli",
        description="BDRC Elasticsearch 检索（autocomplete.bdrc.io）。"
                    "搜书目拿可下载 MW 号 → 交 skill bdrc 下 PDF。",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("search", help="搜书目，给出可下载 MW 号")
    ps.add_argument("query", help="书名/篇名（藏文 Unicode 自动转 Wylie，或直接传 Wylie）")
    ps.add_argument("--type", default="bib",
                    help="bib(默认,Instance+PartTypeText) / all / 或单个 type 如 Instance/PartTypeText/Person/Etext")
    ps.add_argument("--phrase", action="store_true",
                    help="短语精确匹配（保词序）；默认 best_fields+and（所有词都出现，顺序不限）")
    ps.add_argument("--size", type=int, default=15)
    ps.add_argument("--format", choices=["text", "json"], default="text")
    ps.set_defaults(func=cmd_search)

    pc = sub.add_parser("count", help="命中数 + 按 type 分布")
    pc.add_argument("query")
    pc.set_defaults(func=cmd_count)

    pf = sub.add_parser("fulltext", help="etext 全文检索（Unicode 藏文）")
    pf.add_argument("query", help="藏文 Unicode 短语")
    pf.add_argument("--size", type=int, default=10, help="返回 etext 文档数")
    pf.add_argument("--snippets", type=int, default=3, help="每个 etext 显示几条高亮片段")
    pf.add_argument("--format", choices=["text", "json"], default="text")
    pf.set_defaults(func=cmd_fulltext)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
