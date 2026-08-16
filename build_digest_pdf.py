#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_digest_pdf.py — converts the daily China-news digest markdown into a
styled Chinese-language PDF. Commit this file to the repo (e.g. scripts/)
so the routine calls it instead of re-deriving PDF/font logic every run.

Usage:
    python3 scripts/build_digest_pdf.py drafts/news-digest-2026-08-16.md

Expected markdown structure (the routine's prompt must produce this):

    # 中国新闻每日摘要
    日期: 2026年8月16日

    ## 政治
    ### 【标题】具体新闻标题文字
    来源: 新华社 | 2026年8月15日
    这里是两到三句中文摘要内容...

    ### 【标题】下一条新闻标题
    来源: 中国日报 | 2026年8月14日
    摘要内容...

    ## 经济
    ...

Requires (install once via the routine's Environment > Setup script, not
per-run):
    apt-get install -y fonts-wqy-zenhei
    pip install reportlab --break-system-packages
"""

import re
import sys
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.styles import ParagraphStyle

# ---------- Fonts ----------
# WenQuanYi Zen Hei ships as a .ttc collection; index 0 is the plain
# (non-Mono, non-Sharp) TrueType face reportlab can embed directly.
CJK_TTC = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
CJK_TTF_CACHE = "/tmp/WenQuanYiZenHei.ttf"


def ensure_cjk_font():
    if not Path(CJK_TTF_CACHE).exists():
        from fontTools.ttLib import TTCollection
        tc = TTCollection(CJK_TTC)
        tc.fonts[0].save(CJK_TTF_CACHE)
    pdfmetrics.registerFont(TTFont('CJK', CJK_TTF_CACHE))


# ---------- Palette ----------
MAROON = colors.HexColor('#8C1D2B')
MAROON_DARK = colors.HexColor('#5E1420')
GOLD = colors.HexColor('#C9A34E')
INK = colors.HexColor('#242424')
GRAY = colors.HexColor('#767676')
RULE = colors.HexColor('#E4DFD6')
META_BROWN = colors.HexColor('#9A7A2E')

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm

cat_header_style = ParagraphStyle('CatHeader', fontName='CJK', fontSize=13.5, leading=17, textColor=colors.white)
headline_style = ParagraphStyle('Headline', fontName='CJK', fontSize=12, leading=17, textColor=MAROON_DARK, spaceAfter=3)
summary_style = ParagraphStyle('Summary', fontName='CJK', fontSize=9.8, leading=15, textColor=INK)
meta_style = ParagraphStyle('Meta', fontName='CJK', fontSize=8.5, leading=12, textColor=META_BROWN)


# ---------- Markdown parsing ----------
def parse_digest_md(text):
    """Returns (title, date_str, [ {cn, items:[{headline, meta, summary}]} ])"""
    lines = text.splitlines()
    title, date_str = "中国新闻每日摘要", ""
    categories = []
    cur_cat = None
    cur_item = None

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("日期"):
            date_str = line.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif line.startswith("## "):
            cur_cat = {"cn": line[3:].strip(), "items": []}
            categories.append(cur_cat)
            cur_item = None
        elif line.startswith("### "):
            cur_item = {"headline": line[4:].strip(), "meta": "", "summary": ""}
            if cur_cat is not None:
                cur_cat["items"].append(cur_item)
        elif line.startswith("来源") and cur_item is not None:
            cur_item["meta"] = line.strip()
        elif line.strip() and cur_item is not None:
            cur_item["summary"] = (cur_item["summary"] + " " + line.strip()).strip()

    return title, date_str, categories


# ---------- PDF building ----------
def draw_header_footer_factory(title, date_str):
    def draw(canvas, doc):
        canvas.saveState()
        band_h = 28 * mm
        canvas.setFillColor(MAROON)
        canvas.rect(0, PAGE_H - band_h, PAGE_W, band_h, stroke=0, fill=1)
        canvas.setFillColor(MAROON_DARK)
        canvas.rect(0, PAGE_H - band_h, PAGE_W, 2.2 * mm, stroke=0, fill=1)

        canvas.setFillColor(colors.white)
        canvas.setFont('CJK', 17)
        canvas.drawString(MARGIN, PAGE_H - 12.5 * mm, title)
        canvas.setFont('CJK', 9.5)
        canvas.drawString(MARGIN, PAGE_H - 19 * mm, f"Eurasia Times Thailand  |  {date_str}")

        canvas.setFont('CJK', 9)
        badge_w, badge_h = 34 * mm, 6.5 * mm
        bx, by = PAGE_W - MARGIN - badge_w, PAGE_H - 11.5 * mm
        canvas.setFillColor(colors.HexColor('#3F5C3A'))
        canvas.roundRect(bx, by, badge_w, badge_h, 2, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.drawCentredString(bx + badge_w / 2, by + 2 * mm, "待主编审核")

        canvas.setFillColor(GRAY)
        canvas.setFont('CJK', 8)
        canvas.drawString(MARGIN, 12 * mm, "本文件为自动生成的草稿 — 未经主编批准前不会发布")
        canvas.drawRightString(PAGE_W - MARGIN, 12 * mm, f"第 {doc.page} 页")
        canvas.setStrokeColor(RULE)
        canvas.line(MARGIN, 15 * mm, PAGE_W - MARGIN, 15 * mm)
        canvas.restoreState()
    return draw


def category_block(cat):
    flow = []
    header_tbl = Table([[Paragraph(cat['cn'], cat_header_style)]], colWidths=[174 * mm])
    header_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GOLD),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (0, 0), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    flow.append(header_tbl)
    flow.append(Spacer(1, 4))

    for item in cat['items']:
        block = [
            Paragraph(item['headline'], headline_style),
            Paragraph(item['summary'], summary_style),
            Spacer(1, 2),
            Paragraph(item['meta'], meta_style),
            Spacer(1, 7),
            HRFlowable(width="100%", thickness=0.6, color=RULE, spaceAfter=7),
        ]
        flow.append(KeepTogether(block))

    flow.append(Spacer(1, 6))
    return flow


def build(md_path):
    ensure_cjk_font()
    text = Path(md_path).read_text(encoding="utf-8")
    title, date_str, categories = parse_digest_md(text)

    out_path = str(Path(md_path).with_suffix(".pdf"))
    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        topMargin=34 * mm, bottomMargin=20 * mm,
        leftMargin=MARGIN, rightMargin=MARGIN,
        title=title,
    )
    story = []
    for cat in categories:
        story.extend(category_block(cat))

    doc.build(story, onFirstPage=draw_header_footer_factory(title, date_str),
               onLaterPages=draw_header_footer_factory(title, date_str))
    print("Built:", out_path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 build_digest_pdf.py <path-to-digest.md>")
        sys.exit(1)
    build(sys.argv[1])
