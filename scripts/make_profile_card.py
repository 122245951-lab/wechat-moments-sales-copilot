#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_profile_card.py — 客户档案卡 HTML 生成器(纯标准库,零依赖)

作用: 把一次朋友圈分析的结构化结果(JSON)渲染成单文件 HTML 客户档案卡,
      销售可离线打开、存档,下次跟进时复用同一档案追加新证据。

用法:
    python make_profile_card.py profile.json [-o customer_profile.html]

JSON 结构(所有字段可选,缺失自动跳过渲染):

{
  "customer": {"name": "张女士", "note": "保险潜在客户 · 2026-05 展会加微信"},
  "generated_at": "2026-09-04",
  "profile": {
    "summary": "一句话画像:二孩妈妈,关注教育与家庭保障",
    "dimensions": [
      {"name": "基础身份", "items": [
        {"label": "家庭阶段", "value": "二胎家庭", "evidence": "朋友圈多次晒娃",
         "confidence": "高"}]}],
    "not_observed": ["收入水平", "所在城市"]
  },
  "timeline": [{"period": "2026-06", "highlights": "晒新房装修进度"}, ...],
  "signals": [
    {"type": "red", "description": "转发学区房对比测评",
     "evidence": "6-12 转发《XX 学区实测对比》",
     "action": "48h 内提供对比资料", "priority": "P0"}],
  "actions": [
    {"level": "P0 · 24 小时内", "action": "提供学区对比资料",
     "script": "看到你最近在看学区房……", "when": "工作日 20:00 私聊"}]
}
signals.type 取值: red(购买)/yellow(生活事件)/orange(负面情绪)/black(流失预警)
"""
import argparse
import datetime
import html
import json
import os
import sys

SIGNAL_META = {
    "red":    ("🔴", "购买信号", "#c0392b"),
    "yellow": ("🟡", "生活事件", "#b7791f"),
    "orange": ("🟠", "负面情绪", "#d35400"),
    "black":  ("⚫", "流失预警", "#34495e"),
    "other":  ("🔵", "其他观察", "#2c6cb0"),
}

CONF_STYLE = {"高": "high", "中": "mid", "低": "low"}

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:"PingFang SC","Microsoft YaHei",sans-serif; background:#f0f2f5; color:#1f2937; padding:24px; }
.page { max-width:860px; margin:0 auto; }
.card { background:#fff; border-radius:14px; padding:28px 32px; margin-bottom:18px;
        box-shadow:0 2px 8px rgba(0,0,0,.06); }
h1 { font-size:22px; } h2 { font-size:17px; margin-bottom:14px; padding-bottom:8px;
     border-bottom:2px solid #e8ecf1; color:#111827; }
.muted { color:#6b7280; font-size:13px; }
.cust-note { margin-top:8px; }
.summary { background:#f6f9ff; border-left:4px solid #3b82f6; padding:12px 16px;
           border-radius:6px; margin:14px 0 4px; font-size:15px; }
.dim { margin-bottom:12px; }
.dim-name { font-weight:600; color:#374151; margin-bottom:6px; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th,td { text-align:left; padding:8px 10px; border-bottom:1px solid #eef1f5; vertical-align:top; }
th { color:#6b7280; font-weight:500; width:110px; background:#fafbfc; }
.badge { display:inline-block; padding:1px 8px; border-radius:10px; font-size:12px; font-weight:600; }
.badge.high { background:#dcfce7; color:#15803d; }
.badge.mid  { background:#fef9c3; color:#a16207; }
.badge.low  { background:#fee2e2; color:#b91c1c; }
.signal { display:flex; gap:12px; padding:12px 0; border-bottom:1px dashed #e5e7eb; align-items:flex-start; }
.signal:last-child { border-bottom:none; }
.sig-emoji { font-size:20px; line-height:1.4; }
.sig-body { flex:1; }
.sig-title { font-weight:600; }
.sig-ev { color:#6b7280; font-size:13px; margin-top:3px; }
.sig-action { margin-top:6px; font-size:14px; }
.sig-action b { color:#b45309; }
.act { padding:12px 0; border-bottom:1px dashed #e5e7eb; }
.act:last-child { border-bottom:none; }
.act-head { font-weight:700; color:#0f4c81; font-size:15px; margin-bottom:4px; }
.script { background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px 14px;
          margin-top:8px; font-size:14px; line-height:1.7; position:relative; }
.copy-btn { position:absolute; right:8px; top:8px; border:none; background:#e5e7eb; border-radius:6px;
            padding:3px 10px; cursor:pointer; font-size:12px; color:#374151; }
.copy-btn:hover { background:#d1d5db; }
.when { color:#6b7280; font-size:13px; margin-top:6px; }
.tl-item { display:flex; gap:14px; padding:8px 0; }
.tl-period { font-weight:600; color:#0f4c81; min-width:90px; }
.na { color:#9ca3af; font-style:italic; }
.disclaimer { font-size:12px; color:#9ca3af; line-height:1.8; margin-top:14px;
              padding-top:12px; border-top:1px dashed #e5e7eb; }
ul { padding-left:20px; } li { margin:4px 0; font-size:14px; }
"""


def esc(s):
    return html.escape(str(s)) if s not in (None, "") else ""


def _badge(conf):
    """置信度 → badge HTML;空返回空串"""
    if not conf:
        return ""
    cls = CONF_STYLE.get(conf, "mid")
    return '<span class="badge ' + cls + '">' + esc(conf) + "</span>"


def _row(label, value, evidence, conf):
    """画像表的一行"""
    cells = ["<tr><th>" + esc(label) + "</th><td>" + esc(value)]
    if evidence:
        cells.append('<div class="muted">证据:' + esc(evidence) + "</div>")
    cells.append(_badge(conf))
    cells.append("</td></tr>")
    return "".join(cells)


def _render_profile(p):
    blocks = []
    summary = p.get("summary", "")
    if summary:
        blocks.append('<div class="summary">' + esc(summary) + "</div>")
    for dim in p.get("dimensions", []):
        rows = "".join(
            _row(it.get("label"), it.get("value"), it.get("evidence"), it.get("confidence"))
            for it in dim.get("items", []))
        blocks.append('<div class="dim"><div class="dim-name">' + esc(dim.get("name"))
                      + "</div><table>" + rows + "</table></div>")
    na = p.get("not_observed", [])
    if na:
        lis = "".join("<li>" + esc(x) + "</li>" for x in na)
        blocks.append('<div class="dim"><div class="dim-name">未观察到(不脑补)</div>'
                      + "<ul>" + lis + "</ul></div>")
    return "".join(blocks)


def _render_signal(s):
    st = s.get("type", "other")
    emoji, label, color = SIGNAL_META.get(st, SIGNAL_META["other"])
    parts = ['<div class="signal"><div class="sig-emoji">' + emoji + "</div>"
             '<div class="sig-body"><div class="sig-title" style="color:' + color + '">'
             + esc(label) + " · " + esc(s.get("description")) + "</div>"]
    if s.get("evidence"):
        parts.append('<div class="sig-ev">证据:' + esc(s.get("evidence")) + "</div>")
    parts.append('<div class="sig-action"><b>' + esc(s.get("priority", "")) + "</b> "
                 + esc(s.get("action")) + "</div></div></div>")
    return "".join(parts)


def _render_action(a):
    parts = ['<div class="act"><div class="act-head">' + esc(a.get("level")) + " · "
             + esc(a.get("action")) + "</div>"]
    script = a.get("script")
    if script:
        parts.append('<div class="script"><button class="copy-btn" onclick="copyText(this)">复制话术</button>'
                     "<span>" + esc(script) + "</span></div>")
    if a.get("when"):
        parts.append('<div class="when">🕐 ' + esc(a.get("when")) + "</div>")
    parts.append("</div>")
    return "".join(parts)


def render(profile):
    customer = profile.get("customer", {})
    name = customer.get("name", "客户")
    note = customer.get("note", "")
    generated = profile.get("generated_at", datetime.date.today().isoformat())

    p = profile.get("profile", {})

    tl = profile.get("timeline", [])
    tl_block = ""
    if tl:
        items = "".join(
            '<div class="tl-item"><div class="tl-period">' + esc(x.get("period"))
            + "</div><div>" + esc(x.get("highlights")) + "</div></div>" for x in tl)
        tl_block = '<div class="card"><h2>🕐 朋友圈时间线</h2>' + items + "</div>"

    signals = profile.get("signals", [])
    sig_block = ""
    if signals:
        items = "".join(_render_signal(s) for s in signals)
        sig_block = '<div class="card"><h2>🚦 信号提取</h2>' + items + "</div>"

    actions = profile.get("actions", [])
    act_block = ""
    if actions:
        items = "".join(_render_action(a) for a in actions)
        act_block = '<div class="card"><h2>🎯 行动建议与话术</h2>' + items + "</div>"

    disc = ""
    if profile.get("disclaimer", True):
        disc = ('<div class="disclaimer"><b>免责声明:</b>本档案基于客户公开发布的朋友圈内容进行倾向性推断,'
                "仅作为销售跟进参考,不构成对任何人的人格判定或信用评价。朋友圈呈现不等于完整真实,"
                "建议结合线下沟通交叉验证。请妥善保管客户隐私,截图内容仅用于本次分析。</div>")

    head_extra = ""
    if note:
        head_extra = '<div class="cust-note muted">' + esc(note) + "</div>"

    doc = (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>" + esc(name) + " · 客户档案</title><style>" + CSS + "</style></head>"
        '<body><div class="page">'
        '<div class="card"><h1>📇 ' + esc(name) + "</h1>"
        '<div class="muted">档案生成:' + esc(generated) + "</div>"
        + head_extra
        + '<h2 style="margin-top:16px;">👤 客户商业画像</h2>' + _render_profile(p)
        + "</div>"
        + tl_block + sig_block + act_block + disc
        + '</div><script>function copyText(b){var s=b.nextElementSibling;'
        "if(navigator.clipboard){navigator.clipboard.writeText(s.innerText);}"
        "var o=b.innerText;b.innerText='✓ 已复制';"
        "setTimeout(function(){b.innerText=o;},1200);}</script></body></html>"
    )
    return doc


def main():
    ap = argparse.ArgumentParser(description="客户档案卡 HTML 生成器(纯标准库)")
    ap.add_argument("profile_json", help="分析结果 JSON 路径")
    ap.add_argument("-o", "--out", default=None, help="输出 HTML 路径;缺省为 <json名>_档案.html")
    args = ap.parse_args()

    with open(args.profile_json, "r", encoding="utf-8") as f:
        profile = json.load(f)

    doc = render(profile)
    out = args.out or (os.path.splitext(args.profile_json)[0] + "_档案.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    print("已生成档案卡: " + os.path.abspath(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
