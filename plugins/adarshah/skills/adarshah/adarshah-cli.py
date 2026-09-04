#!/usr/bin/env python3
"""adarshah-cli — Adarshah 藏文大藏经全文检索 CLI

Wraps the public REST API at https://api.adarshah.org (Dharma Treasure Corp).
站点完全免费、无需注册——前端硬编码 apiKey 即为公开 key。

Endpoints used:
  POST /plugins/adarshaplugin/file_servlet/search/esCount
  POST /plugins/adarshaplugin/file_servlet/search/esSearch
  POST /plugins/adarshaplugin/file_servlet/listDivisions
  POST /plugins/adarshaplugin/file_servlet/sutraInfo
  POST /plugins/adarshaplugin/file_servlet/sutra/texts

Pagination quirk: 后端 size 硬编码 20，searchAfter 在 wildcard=true 下会失效
回退到 OR 分词检索。绕开方式：用 esCount 的 count_kdb aggregation 拿到
每个 kdb 的命中数，再按 kdb filter 各跑一次 esSearch（每 kdb 命中 ≤20 是常态）。
"""

import argparse
import json
import ssl
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

API_BASE = "https://api.adarshah.org/plugins/adarshaplugin/file_servlet"
API_KEY = "ZTI3Njg0NTNkZDRlMTJjMWUzNGM3MmM5ZGI3ZDUxN2E="

# kdb 中文标签（基于实测 + divisionName.tw 推断；新发现请补充）
KDB_LABELS = {
    "degekangyur":         "德格甘珠尔（佛说部）",
    "jiangkangyur":        "江（理塘）甘珠尔",
    "lhasakangyur":        "拉萨甘珠尔",
    "narthangkangyur":     "那塘甘珠尔",
    "pekingkangyur":       "北京甘珠尔",
    "stogkangyur":         "拓宫甘珠尔",
    "phugdrakkangyur":     "普扎甘珠尔",
    "tabokangyur":         "塔波甘珠尔",
    "degetengyur":         "德格丹珠尔（论释部）",
    "pekingtengyur":       "北京丹珠尔",
    "dalailamasungbum":    "历代法王文集",
    "panchenlamasungbum":  "历代班禅喇嘛文集",
    "terdzo":              "《大宝伏藏》Rinchen Terdzö",
    "taranatha":           "多罗那他文集",
    "tsongkhapa":          "宗喀巴文集",
    "8thkarmapa":          "第八世噶玛巴米觉多杰文集",
    "gorampa":             "果然巴·索南僧格文集",
    "shakyachogden":       "释迦确丹文集",
    "matipanchen":         "玛底班禅·绛央罗追文集",
    "padkar":              "索南僧格《白莲心义》",
    "tshalminpa":          "蔡米巴文集",
    "ngawangkungalodroe":  "阿旺贡噶罗追文集（萨迦）",
    "ngawangkungasonam":   "阿旺贡噶索南文集（萨迦）",
    "dolpopa":             "笃布巴文集",
    "dragpagyaltsen":      "扎巴坚赞文集",
    "sonamgragpa":         "索南扎巴文集",
    "sonamgyaltsen":       "索南坚赞文集",
    "sakyalotsawa":        "萨迦洛扎瓦文集",
    "logrosgragspa":       "罗追扎巴文集",
    "nyadbonkungapal":     "聂温贡嘎贝文集",
    "yontenbzangpo":       "云丹桑波文集",
    "yeshegyatsho":        "益西嘉措文集",
    "thugsrjebrtsongrus":  "图杰宗珠文集",
    "choglenamgyal":       "确雷南杰文集",
    "chodrapal":           "确扎巴文集",
    "lodropal":            "罗追巴文集",
    "gharungpa":           "噶绒巴文集",
}

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _post(path: str, **params) -> dict:
    import subprocess
    data = {"apiKey": API_KEY, **{k: v for k, v in params.items() if v is not None}}
    # 直接用 curl（Python 3.14 ssl 对 Adarsha 服务器不稳定）
    # -k: 跳过 SSL 验证（Adarsha 服务器证书间歇性问题）
    # --retry 2: 遇到暂时性错误时重试
    cmd = ["curl", "-s", "-k", "--retry", "2", "-X", "POST", API_BASE + path]
    for k, v in data.items():
        cmd += ["--data-urlencode", f"{k}={v}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed (exit {result.returncode}): {result.stderr}")
    return json.loads(result.stdout)


def cmd_count(args):
    """仅返回 phrase 命中数 + 按 kdb 分布。"""
    d = _post(
        "/search/esCount",
        text=args.phrase,
        wildcard="true" if args.wildcard else "false",
    )
    total = d["hits"]["total"]["value"]
    buckets = d["aggregations"]["count_kdb"]["buckets"]
    print(f"phrase: {args.phrase}")
    print(f"wildcard: {args.wildcard}")
    print(f"total hits: {total}\n")
    print(f"{'kdb':30s} {'count':>6}  label")
    print("-" * 80)
    for b in buckets:
        kdb = b["key"]
        n = b["doc_count"]
        label = KDB_LABELS.get(kdb, "")
        print(f"{kdb:30s} {n:>6}  {label}")


def cmd_search(args):
    """按 kdb 分批拉全部 phrase-match hits。"""
    cnt = _post(
        "/search/esCount",
        text=args.phrase,
        wildcard="true" if args.wildcard else "false",
    )
    buckets = cnt["aggregations"]["count_kdb"]["buckets"]
    total = cnt["hits"]["total"]["value"]
    sys.stderr.write(f"[count] phrase hits = {total} across {len(buckets)} kdb\n")

    all_hits = []
    seen = set()
    for b in buckets:
        kdb = b["key"]
        expected = b["doc_count"]
        r = _post(
            "/search/esSearch",
            text=args.phrase,
            wildcard="true" if args.wildcard else "false",
            kdb=kdb,
        )
        hits = r.get("hits", {}).get("hits", [])
        sys.stderr.write(f"  {kdb:25s} expected={expected:>4} got={len(hits):>4}\n")
        for h in hits:
            if h["_id"] in seen:
                continue
            seen.add(h["_id"])
            all_hits.append(h)

    sys.stderr.write(f"[done] unique hits = {len(all_hits)}\n\n")

    if args.format == "json":
        json.dump(all_hits, sys.stdout, ensure_ascii=False, indent=2)
        return

    # human-readable: group by kdb, sort by orderPB
    by_kdb = defaultdict(list)
    for h in all_hits:
        by_kdb[h["fields"]["kdb"][0]].append(h)
    order = [b["key"] for b in buckets]

    print(f"# 「{args.phrase}」全部 {len(all_hits)} 处\n")
    for kdb in order:
        items = by_kdb[kdb]
        if not items:
            continue
        label = KDB_LABELS.get(kdb, kdb)
        print(f"\n## {label}  ({kdb}, {len(items)} 条)\n")
        items.sort(key=lambda h: h["fields"].get("orderPB", [0])[0])
        for i, h in enumerate(items, 1):
            f = h["fields"]
            sutra = f.get("sutra", ["?"])[0]
            tname = f.get("tname", [""])[0]
            cname = f.get("cname", [""])[0].strip()
            div = f.get("divisionName.cn", [""])[0] or f.get("divisionName.tw", [""])[0]
            vol = f.get("volName.cn", [""])[0]
            pb = f.get("pb", ["?"])[0]
            name = cname if cname else tname
            print(f"  {i:>2}. [{sutra}] {div} / {vol} · pb={pb}")
            print(f"      tname: {tname[:100]}")


def cmd_divisions(args):
    d = _post("/listDivisions", kdb=args.kdb)
    if args.format == "json":
        json.dump(d, sys.stdout, ensure_ascii=False, indent=2)
        return
    print(f"# kdb={args.kdb} divisions\n")
    print(f"hasPicture={d.get('hasPicture')}  lang_tw={d.get('lang_tw')}\n")
    print(f"volumes ({len(d.get('vols', []))}):")
    for v in d.get("vols", [])[:60]:
        print(f"  {v.get('n'):>4}  {v.get('t', ''):4s}  {v.get('cn', ''):20s}  bo={v.get('bo', '')}")


def cmd_sutra_info(args):
    d = _post("/sutraInfo", kdb=args.kdb, sutra=args.sutra)
    if args.format == "json":
        json.dump(d, sys.stdout, ensure_ascii=False, indent=2)
        return
    print(f"# kdb={args.kdb}  sutra={args.sutra}\n")
    heads = d.get("heads", [])
    if heads:
        print(f"heads ({len(heads)}):")
        print(f"  pb range: {heads[0].get('pbName', '?')} → {heads[-1].get('pbName', '?')}\n")
        for h in heads:
            indent = "  " * (h.get("level", "1").count(".") + 1)
            print(f"  {indent}{h.get('level', '?'):12s} pb={h.get('pbName', '?'):12s} {h.get('t', '')}")
    print()
    for b in d.get("bampos", [])[:200]:
        print(f"  {b.get('n', '?'):>8}  type={b.get('type', '?'):8s}  pb={b.get('pbName', '?'):12s}  bo={b.get('bo', '')}")


def cmd_texts(args):
    """提取某经全文（sutraInfo → /sutra/texts 自动分页）。"""
    import html as html_mod
    import re

    # Step 1: 获取起始页码
    sys.stderr.write(f"[info] sutraInfo kdb={args.kdb} sutra={args.sutra}\n")
    info = _post("/sutraInfo", kdb=args.kdb, sutra=args.sutra)
    heads = info.get("heads", [])
    if not heads:
        sys.stderr.write("[error] sutraInfo 返回空 heads，无法确定起始页码\n")
        sys.exit(1)
    start_pb = heads[0].get("pbName", "")
    end_pb = heads[-1].get("pbName", "")
    title = heads[0].get("t", "")
    cn = heads[0].get("cn", "") or heads[0].get("tw", "")
    sys.stderr.write(f"[info] pb={start_pb} → {end_pb}, heads={len(heads)}\n")
    sys.stderr.write(f"[info] title: {title}\n")

    # Step 2: 分页提取全文
    all_items = []
    page = start_pb
    seen = set()
    batch = 0
    while True:
        batch += 1
        r = _post("/sutra/texts", sutra=args.sutra, kdb=args.kdb, page=page, size="20", lang="bo")
        if not r:
            break
        new_items = []
        for item in r:
            pb = item.get("pbName", "")
            lv = item.get("headerLV", "")
            key = f"{pb}_{lv}_{len(item.get('text', ''))}"
            if key not in seen:
                seen.add(key)
                new_items.append(item)
        if not new_items:
            break
        all_items.extend(new_items)
        last_pb = r[-1].get("pbName", "")
        sys.stderr.write(f"  batch {batch}: {len(r)} items, last_pb={last_pb}\n")
        if len(r) < 20 or last_pb == page:
            break
        page = last_pb

    sys.stderr.write(f"[done] total {len(all_items)} items\n\n")

    # Step 3: 输出
    if args.format == "json":
        out = json.dumps(all_items, ensure_ascii=False, indent=2)
    else:
        # Markdown 格式
        lines = []
        lines.append(f"# {title}")
        if cn:
            lines.append(f"# {cn}")
        lines.append("")
        lines.append(f"- **典籍编号**: {args.sutra}")
        lines.append(f"- **文库**: {KDB_LABELS.get(args.kdb, args.kdb)}")
        lines.append(f"- **来源**: Adarsha (adarsha.dharma-treasure.org)")
        lines.append("")
        lines.append("---")
        lines.append("")

        current_pb = ""
        for item in all_items:
            pb = item.get("pbName", "")
            lv = item.get("headerLV", "")
            text_html = item.get("text", "")

            if pb != current_pb:
                if current_pb:
                    lines.append("")
                lines.append(f"[{pb}]")
                lines.append("")
                current_pb = pb

            # 处理标题
            if '<span class="head"' in text_html:
                m_t = re.search(r'data-t="([^"]*)"', text_html)
                head_t = html_mod.unescape(m_t.group(1)) if m_t else ""
                m_cn = re.search(r'data-cn="([^"]*)"', text_html)
                head_cn = html_mod.unescape(m_cn.group(1)) if m_cn else ""
                if head_t:
                    depth = lv.count(".") + 1 if lv else 1
                    md_level = min(depth + 1, 6)
                    heading = f"{'#' * md_level} {head_t}"
                    if head_cn:
                        heading += f" ({head_cn})"
                    lines.append(heading)
                    lines.append("")

            # 纯文本
            text = re.sub(r"<[^>]+>", "", text_html)
            text = html_mod.unescape(text).strip()
            if text:
                lines.append(text)
                lines.append("")

        out = "\n".join(lines)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        sys.stderr.write(f"[saved] {args.out} ({len(out)} bytes)\n")
    else:
        sys.stdout.write(out)


def main():
    p = argparse.ArgumentParser(
        prog="adarshah-cli",
        description="Adarshah 藏文大藏经全文检索 (https://adarshah.org)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("count", help="phrase 命中数 + 按 kdb 分布")
    pc.add_argument("phrase", help="待搜藏文短语（直接 utf-8）")
    pc.add_argument("--no-wildcard", dest="wildcard", action="store_false", default=True,
                    help="关闭 wildcard（默认 phrase-ish match；关掉是 token OR 检索）")
    pc.set_defaults(func=cmd_count)

    ps = sub.add_parser("search", help="拉全部 phrase-match hits（按 kdb 分批）")
    ps.add_argument("phrase")
    ps.add_argument("--format", choices=["text", "json"], default="text")
    ps.add_argument("--no-wildcard", dest="wildcard", action="store_false", default=True)
    ps.set_defaults(func=cmd_search)

    pd = sub.add_parser("divisions", help="列某个 kdb 的全部函（vol）")
    pd.add_argument("kdb", help="kdb 代号（如 degekangyur / jiangkangyur）")
    pd.add_argument("--format", choices=["text", "json"], default="text")
    pd.set_defaults(func=cmd_divisions)

    pi = sub.add_parser("sutra-info", help="某经的科判/标题结构")
    pi.add_argument("kdb")
    pi.add_argument("sutra", help="如 d44d / J299g / D4013 / D2679")
    pi.add_argument("--format", choices=["text", "json"], default="text")
    pi.set_defaults(func=cmd_sutra_info)

    pt = sub.add_parser("texts", help="提取某经全文（自动分页，输出 Markdown）")
    pt.add_argument("kdb", help="kdb 代号（如 degetengyur）")
    pt.add_argument("sutra", help="经号（如 D2679 / d750）")
    pt.add_argument("--out", help="输出文件路径（省略则输出到 stdout）")
    pt.add_argument("--format", choices=["text", "json"], default="text")
    pt.set_defaults(func=cmd_texts)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

