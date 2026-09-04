#!/usr/bin/env python3
"""cbeta_index — 从 CBETA XML P5 建本地全文检索索引（SQLite FTS5 trigram）

用法：
  python3 cbeta_index.py build <xml-p5 目录> [-o cbeta.sqlite]
  python3 cbeta_index.py build ~/cbeta/xml-p5 --canon T          # 只建大正藏
  python3 cbeta_index.py info [-d cbeta.sqlite]

数据自备：CBETA 官方 XML P5 在 https://github.com/cbeta-org/xml-p5
  git clone --depth 1 https://github.com/cbeta-org/xml-p5.git

处理规则：
  · <note> 校勘注、夹注一律排除，否则检索会命中注文而非正文
  · <app><lem>底本读法</lem><rdg>异读</rdg></app> 取 lem 弃 rdg
  · <g ref="#CB00768">𡁠</g> 外字标签内已有 Unicode，直接取文本
  · <lb n="0022b03"/> 逐行记录，段内建立「字符偏移 → 行锚点」映射，
    检索命中时据此还原出精确到行的 linehead（如 T30n1579_p0279a05）

只用标准库。全藏建库是几十分钟量级（随机器差别很大），产出库比源 XML 略大。
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
from xml.etree import ElementTree as ET

TEI = "{http://www.tei-c.org/ns/1.0}"
CB = "{http://www.cbeta.org/ns/1.0}"

# 这些子树整个跳过：校勘注、异读、目录标记、行首标题等非正文内容
SKIP = {
    TEI + "note", TEI + "rdg", TEI + "teiHeader",
    CB + "mulu", CB + "docNumber", CB + "jhead",
}


def split_work_id(work_id):
    """T30n1579 → ('T', 'T1579')。册号是物理位置，经号才是引用用的标识。

    少数部类的 ID 形如 ZW01n0001、B01n0001，规则一致：字母部类 + 册号 + n + 经号。
    """
    m = re.match(r"^([A-Za-z]+)(\d*)n(.+)$", work_id)
    if m:
        canon, _vol, num = m.groups()
        return canon, f"{canon}{num}"
    canon = "".join(c for c in work_id if c.isalpha())
    return canon or "?", work_id


def iter_text(elem, ctx, state, out):
    """深度遍历，收集正文文本，并在遇到 <lb> 时记录行锚点位置。

    ctx:   {"lb": 当前行锚}，跨段共享——<lb> 常散落在 <p> 之外，
           必须全局追踪，否则段起始拿不到锚点
    state: {"map": [(字符偏移, 行锚), ...]} 本段内的偏移映射
    out:   文本片段列表
    """
    tag = elem.tag

    if tag in SKIP:
        # 跳过整个子树，但 tail 仍属于父级正文
        if elem.tail:
            out.append(elem.tail)
        return

    if tag == TEI + "lb":
        n = elem.get("n")
        if n:
            ctx["lb"] = n
            state["map"].append((sum(len(x) for x in out), n))
        if elem.tail:
            out.append(elem.tail)
        return

    if elem.text:
        out.append(elem.text)

    for child in elem:
        iter_text(child, ctx, state, out)

    if elem.tail:
        out.append(elem.tail)


def parse_work(path):
    """解析一部经，产出 (juan, linehead, text, linemap) 的段落记录。"""
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        print(f"  跳过（XML 解析失败）{os.path.basename(path)}: {e}", file=sys.stderr)
        return None, None, []

    root = tree.getroot()
    work_id = root.get("{http://www.w3.org/XML/1998/namespace}id") or ""

    title = ""
    for t in root.iter(TEI + "title"):
        if t.get("level") == "m" and t.text:
            title = t.text.strip()
            break
    if not title:
        for t in root.iter(TEI + "title"):
            if t.text:
                title = t.text.strip()
                break

    body = root.find(f".//{TEI}body")
    if body is None:
        return work_id, title, []

    rows = []
    juan = 0
    ctx = {"lb": None}  # 当前行锚，跨段延续

    def walk(elem):
        nonlocal juan
        for child in elem:
            tag = child.tag

            if tag in SKIP:
                continue

            # <lb> 在段落之外也要追踪，否则下一段拿不到起始锚点
            if tag == TEI + "lb":
                n = child.get("n")
                if n:
                    ctx["lb"] = n
                continue

            if tag == TEI + "milestone" and child.get("unit") == "juan":
                try:
                    juan = int(child.get("n") or 0)
                except ValueError:
                    pass
                continue

            if tag == CB + "juan":
                n = child.get("n")
                if n:
                    try:
                        juan = int(n)
                    except ValueError:
                        pass

            if tag in (TEI + "p", TEI + "lg"):
                start_lb = ctx["lb"]
                state = {"map": []}
                out = []
                iter_text(child, ctx, state, out)
                text = " ".join("".join(out).split())
                if len(text) >= 2:
                    # 段首若无 lb，用进入本段时的行锚补上
                    lmap = state["map"]
                    if start_lb and (not lmap or lmap[0][0] > 0):
                        lmap = [(0, start_lb)] + lmap
                    lh = lmap[0][1] if lmap else ""
                    rows.append((juan, lh, text, json.dumps(lmap, separators=(",", ":"))))
                continue

            walk(child)

    walk(body)
    return work_id, title, rows


def build(src, dbpath, canon_filter=None):
    if not os.path.isdir(src):
        sys.exit(f"找不到目录 {src}")

    if os.path.exists(dbpath):
        sys.exit(f"{dbpath} 已存在。要重建请先删除它。")

    con = sqlite3.connect(dbpath)
    con.executescript("""
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        CREATE TABLE passage(
            id INTEGER PRIMARY KEY,
            work TEXT NOT NULL,      -- 全 ID，如 T30n1579（含册号）
            sutra TEXT NOT NULL,     -- 经号，如 T1579（CBETA 标准写法）
            canon TEXT NOT NULL,     -- 部类，如 T
            juan INTEGER,
            title TEXT,
            linehead TEXT,
            text TEXT NOT NULL,
            linemap TEXT
        );
    """)

    files = []
    for dirpath, _, names in os.walk(src):
        for n in sorted(names):
            if n.endswith(".xml"):
                files.append(os.path.join(dirpath, n))
    files.sort()

    if canon_filter:
        want = {c.upper() for c in canon_filter}
        files = [f for f in files
                 if os.path.basename(f).split("n")[0].rstrip("0123456789").upper() in want]

    if not files:
        sys.exit(f"{src} 下没找到 XML 文件。确认已 clone cbeta-org/xml-p5。")

    print(f"待处理 {len(files)} 部", flush=True)
    t0 = time.time()
    total = 0

    for i, path in enumerate(files, 1):
        work_id, title, rows = parse_work(path)
        if not rows:
            continue
        canon, sutra = split_work_id(work_id or os.path.basename(path)[:-4])
        con.executemany(
            "INSERT INTO passage(work,sutra,canon,juan,title,linehead,text,linemap) "
            "VALUES(?,?,?,?,?,?,?,?)",
            [(work_id, sutra, canon, j, title, lh, tx, lm) for j, lh, tx, lm in rows],
        )
        total += len(rows)
        if i % 200 == 0:
            con.commit()
            print(f"  {i}/{len(files)}  已入 {total:,} 段  {time.time()-t0:.0f}s", flush=True)

    con.commit()
    print(f"正文入库完成：{total:,} 段，{time.time()-t0:.0f}s。开始建 FTS5 索引…", flush=True)

    con.executescript("""
        CREATE VIRTUAL TABLE passage_fts USING fts5(
            text, content='passage', content_rowid='id', tokenize='trigram');
        INSERT INTO passage_fts(passage_fts) VALUES('rebuild');
        CREATE INDEX idx_sutra ON passage(sutra);
        CREATE INDEX idx_canon ON passage(canon);
    """)
    con.commit()
    con.execute("VACUUM")
    con.close()

    mb = os.path.getsize(dbpath) / 1024 / 1024
    print(f"完成：{dbpath}  {mb:.0f} MB  共 {time.time()-t0:.0f}s")


def info(dbpath):
    if not os.path.exists(dbpath):
        sys.exit(f"找不到 {dbpath}")
    con = sqlite3.connect(f"file:{dbpath}?mode=ro", uri=True)
    n_p = con.execute("SELECT count(*) FROM passage").fetchone()[0]
    n_w = con.execute("SELECT count(DISTINCT work) FROM passage").fetchone()[0]
    print(f"{dbpath}  {os.path.getsize(dbpath)/1024/1024:.0f} MB")
    print(f"  {n_w:,} 部  {n_p:,} 段")
    print("  按部类：")
    for canon, c, w in con.execute(
        "SELECT canon, count(*), count(DISTINCT work) FROM passage GROUP BY canon ORDER BY count(*) DESC"
    ):
        print(f"    {canon:4} {w:>6,} 部  {c:>9,} 段")
    con.close()


def main():
    ap = argparse.ArgumentParser(description="从 CBETA XML P5 建本地全文索引")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="建索引")
    b.add_argument("src", help="xml-p5 仓库目录")
    b.add_argument("-o", "--out", default="cbeta.sqlite", help="输出数据库（默认 cbeta.sqlite）")
    b.add_argument("--canon", nargs="*", help="只建指定部类，如 T X J（默认全建）")

    i = sub.add_parser("info", help="看库里有什么")
    i.add_argument("-d", "--db", default="cbeta.sqlite")

    args = ap.parse_args()
    if args.cmd == "build":
        build(args.src, args.out, args.canon)
    else:
        info(args.db)


if __name__ == "__main__":
    main()
