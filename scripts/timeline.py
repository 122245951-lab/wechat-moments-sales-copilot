#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""timeline.py — 微信朋友圈截图时间轴整理工具(纯标准库,零依赖)

作用: 用户提供多张客户朋友圈截图时,把文件按时间先后排序,
      输出一份 LLM 可直接消费的时间轴清单(JSON/文本),
      帮分析过程建立正确的时间序列证据链。

用法:
    python timeline.py <截图文件或目录> [--out timeline.json] [--format text|json]

时间来源优先级:
    1. 文件名 mmexport<13位毫秒时间戳>.jpg / <毫秒时间戳>.jpg
    2. 文件名 IMG_YYYYMMDD_HHMMSS.* / VID_YYYYMMDD_HHMMSS.*
    3. 文件名 WeChat_YYYYMMDD_HHMMSS.* / Screenshot_YYYYMMDD-HHMMSS.*
    4. 其他命名 → 按文件修改时间(mtime)兜底,并在输出中标注 estimate

注意: 文件名时间与图内时间戳冲突时,以图内内容为准(由分析者判断),
      本工具只负责排序与提供时间证据。
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys

MILLIS_13 = re.compile(r"(\d{13})")
IMG_DT = re.compile(r"(?:IMG|VID|WeChat|Screenshot)[_-]?(\d{4})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})", re.IGNORECASE)
MMEXPORT_TS = re.compile(r"(?:mmexport|wx)(\d{13})", re.IGNORECASE)


def ts_from_13_digits(text: str):
    """13 位毫秒时间戳 → (datetime, True/是否来自毫秒戳);无匹配返回 (None, False)"""
    m = MMEXPORT_TS.search(text) or MILLIS_13.search(text)
    if not m:
        return None, False
    ms = int(m.group(1))
    try:
        return datetime.datetime.fromtimestamp(ms / 1000.0), True
    except (OSError, OverflowError, ValueError):
        return None, False


def ts_from_filename(text: str):
    """IMG_YYYYMMDD_HHMMSS / WeChat_YYYYMMDD_HHMMSS / Screenshot_YYYYMMDD-HHMMSS"""
    m = IMG_DT.search(text)
    if not m:
        return None, False
    try:
        return datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                 int(m.group(4)), int(m.group(5)), int(m.group(6))), True
    except ValueError:
        return None, False


def ts_from_mtime(path: str):
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)), False
    except OSError:
        return None


def extract_time(path: str):
    """返回 (datetime | None, source: exact_file | estimate_mtime)"""
    base = os.path.basename(path)
    dt, exact = ts_from_13_digits(base)
    if dt:
        return dt, "exact_file(13位毫秒戳)"
    dt, exact = ts_from_filename(base)
    if dt:
        return dt, "exact_file(命名时间戳)"
    dt, exact = ts_from_mtime(path)
    if dt:
        return dt, "estimate(文件修改时间,请以图内时间为准)"
    return None, "unknown"


def collect_paths(target: str):
    if os.path.isdir(target):
        exts = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif", ".bmp")
        return sorted(os.path.join(target, f) for f in os.listdir(target)
                      if f.lower().endswith(exts))
    if os.path.isfile(target):
        return [target]
    raise FileNotFoundError(f"路径不存在: {target}")


def build_timeline(targets, fmt="json"):
    entries = []
    for t in targets:
        for p in collect_paths(t):
            dt, source = extract_time(p)
            entries.append({
                "file": os.path.abspath(p),
                "filename": os.path.basename(p),
                "time": dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None,
                "time_source": source,
                "order_hint": "依时间戳排序" if dt else "无法解析,排在最后",
            })
    entries.sort(key=lambda e: e["time"] or "9999")
    for idx, e in enumerate(entries, 1):
        e["seq"] = idx
    return entries


def fmt_text(entries):
    lines = [f"时间轴:共 {len(entries)} 张截图(按时间升序)"]
    for e in entries:
        t = e["time"] or "时间未知"
        flag = "⚠️" if "estimate" in e["time_source"] else "  "
        lines.append(f"{e['seq']:>2}. {flag} [{t}] {e['filename']}")
    lines.append("提示:estimate 条目请结合图内动态发布时间人工复核;")
    lines.append("若文件名时间与图内时间冲突,一律以图内内容为准。")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="微信朋友圈截图时间轴整理(纯标准库)")
    ap.add_argument("targets", nargs="+", help="截图文件或目录(可多个)")
    ap.add_argument("--out", default=None, help="输出文件路径;缺省打印到 stdout")
    ap.add_argument("--format", choices=["json", "text"], default="json")
    args = ap.parse_args()

    try:
        entries = build_timeline(args.targets)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.format == "json":
        payload = {"total": len(entries), "entries": entries}
        output = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        output = fmt_text(entries)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"已写入 {os.path.abspath(args.out)}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
