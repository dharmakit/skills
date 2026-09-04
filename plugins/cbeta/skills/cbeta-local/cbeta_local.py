#!/usr/bin/env python3
"""cbeta_local — CBETA 汉文佛典本地全文检索（SQLite FTS5 trigram，毫秒级，不联网）

用法：
  cbeta_local.py "色不異空"                      # 基本检索
  cbeta_local.py "前九地" -w T1580               # 限定某部经（经号）
  cbeta_local.py "境行果" -t 瑜伽                 # 限定书名含某词的经
  cbeta_local.py "如是我聞" --count               # 精确命中总数
  cbeta_local.py "色不異空" -n 20 -c 300          # 条数与上下文字数
  cbeta_local.py "涅槃" --slow                    # 少于 3 字的查询需显式放行

索引由 cbeta_index.py 从 CBETA XML P5 建出，每条结果直接给出
精确到行的引用锚点（如 T30n1579_p0279a08），无需联网回查。

数据库位置按以下顺序查找：
  1. -d/--db 参数
  2. 环境变量 CBETA_DB
  3. ./cbeta.sqlite
  4. ~/.cbeta/cbeta.sqlite
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time


def find_db(explicit=None):
    for p in (explicit, os.environ.get("CBETA_DB"), "cbeta.sqlite",
              os.path.expanduser("~/.cbeta/cbeta.sqlite")):
        if p and os.path.exists(p):
            return p
    sys.exit(
        "找不到索引库。先用 cbeta_index.py 建一个：\n"
        "  git clone --depth 1 https://github.com/cbeta-org/xml-p5.git\n"
        "  python3 cbeta_index.py build xml-p5 -o ~/.cbeta/cbeta.sqlite\n"
        "或用 -d 指定路径，或设环境变量 CBETA_DB。"
    )


def line_at(linemap_json, offset):
    """按段内字符偏移，找出命中落在哪一行的锚点。"""
    try:
        lmap = json.loads(linemap_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return ""
    best = ""
    for off, lb in lmap:
        if off <= offset:
            best = lb
        else:
            break
    return best or (lmap[0][1] if lmap else "")


def fts_quote(q):
    """trigram 表按字面短语匹配，整个查询包成一个 FTS5 phrase。"""
    return '"' + q.replace('"', '""') + '"'


def search(args):
    dbpath = find_db(args.db)
    con = sqlite3.connect(f"file:{dbpath}?mode=ro", uri=True)

    q = args.query.strip()
    if len(q) < 3 and not args.slow:
        sys.exit(f"「{q}」只有 {len(q)} 个字，trigram 索引下会退化成全表扫。"
                 f"确实要查就加 --slow。")

    where, params = ["passage_fts MATCH ?"], [fts_quote(q)]
    if args.work:
        # 经号两种写法都认：T1579（标准）与 T30n1579（含册号）
        where.append("(p.sutra = ? OR p.work = ? OR p.sutra LIKE ?)")
        w = args.work.strip()
        params += [w, w, f"%{w}%"]
    if args.title:
        where.append("p.title LIKE ?")
        params.append(f"%{args.title}%")
    cond = " AND ".join(where)

    t0 = time.time()

    if args.count:
        n = con.execute(
            f"SELECT count(*) FROM passage_fts JOIN passage p ON p.id=passage_fts.rowid "
            f"WHERE {cond}", params).fetchone()[0]
        # FTS 是段级命中，再数段内出现次数
        total = 0
        for (text,) in con.execute(
            f"SELECT p.text FROM passage_fts JOIN passage p ON p.id=passage_fts.rowid "
            f"WHERE {cond}", params):
            total += text.count(q)
        print(f"「{q}」命中 {n:,} 段，共 {total:,} 处  ({time.time()-t0:.3f}s)")
        con.close()
        return

    rows = con.execute(
        f"SELECT p.work, p.sutra, p.juan, p.title, p.text, p.linemap "
        f"FROM passage_fts JOIN passage p ON p.id=passage_fts.rowid "
        f"WHERE {cond} LIMIT ?", params + [args.num]).fetchall()

    elapsed = time.time() - t0

    if not rows:
        print(f"「{q}」零命中  ({elapsed:.3f}s)")
        print()
        print("注意：trigram 是字面连续匹配，标点与插字都会断词。")
        print("单条零命中不能下「原典里没有这句」的结论——换 3-5 个不含标点的")
        print("连续字串交叉验证，全部零命中才可下结论。")
        con.close()
        return

    print(f"「{q}」显示 {len(rows)} 条  ({elapsed:.3f}s)")
    print()

    for i, (work, sutra, juan, title, text, linemap) in enumerate(rows, 1):
        pos = text.find(q)
        if pos < 0:
            pos = 0
        lb = line_at(linemap, pos)
        anchor = f"{work}_p{lb}" if lb else work

        half = max(args.context - len(q), 0) // 2
        lo, hi = max(0, pos - half), min(len(text), pos + len(q) + half)
        snippet = text[lo:hi]
        snippet = snippet.replace(q, f"【{q}】")
        if lo > 0:
            snippet = "…" + snippet
        if hi < len(text):
            snippet = snippet + "…"

        print(f"[{i}] {sutra} {title} 卷{juan}")
        print(f"    {anchor}")
        print(f"    {snippet}")
        print()

    con.close()


def main():
    ap = argparse.ArgumentParser(
        description="CBETA 汉文佛典本地全文检索",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", help="检索词（繁体，建议 3 字以上）")
    ap.add_argument("-d", "--db", help="索引库路径")
    ap.add_argument("-w", "--work", help="限定经号，如 T1580")
    ap.add_argument("-t", "--title", help="限定书名含某词")
    ap.add_argument("-n", "--num", type=int, default=5, help="结果条数（默认 5）")
    ap.add_argument("-c", "--context", type=int, default=120, help="上下文字数（默认 120）")
    ap.add_argument("--count", action="store_true", help="只给精确命中数")
    ap.add_argument("--slow", action="store_true", help="放行少于 3 字的查询")
    search(ap.parse_args())


if __name__ == "__main__":
    main()
