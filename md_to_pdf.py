#!/usr/bin/env python3
"""Convert a Markdown report into a polished, link-enabled Chinese PDF."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


PAGE_W, PAGE_H = A4
NAVY = colors.HexColor("#132238")
BLUE = colors.HexColor("#245A84")
ACCENT = colors.HexColor("#C54B3C")
MUTED = colors.HexColor("#687386")
PALE_BLUE = colors.HexColor("#EAF1F6")
LINE = colors.HexColor("#D5DDE4")
PAPER = colors.HexColor("#FBFAF7")
TEXT = colors.HexColor("#26313D")
WHITE = colors.white

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
TABLE_DIVIDER_RE = re.compile(r":?-{3,}:?")


def register_same_font(path: Path, index: int = 0) -> None:
    for name in ("CNSerif", "CNSerifBold", "CNSerifBlack", "CNSans", "CNSansBold"):
        pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=index))


def register_fonts(args: argparse.Namespace) -> None:
    """Register embedded CJK fonts, preferring the macOS Songti/Heiti set."""
    if args.font:
        register_same_font(args.font.expanduser().resolve(), args.font_index)
    else:
        songti = Path("/System/Library/Fonts/Supplemental/Songti.ttc")
        heiti_light = Path("/System/Library/Fonts/STHeiti Light.ttc")
        heiti_medium = Path("/System/Library/Fonts/STHeiti Medium.ttc")
        if songti.exists() and heiti_light.exists() and heiti_medium.exists():
            pdfmetrics.registerFont(TTFont("CNSerif", str(songti), subfontIndex=6))
            pdfmetrics.registerFont(TTFont("CNSerifBold", str(songti), subfontIndex=1))
            pdfmetrics.registerFont(TTFont("CNSerifBlack", str(songti), subfontIndex=0))
            pdfmetrics.registerFont(TTFont("CNSans", str(heiti_light), subfontIndex=1))
            pdfmetrics.registerFont(TTFont("CNSansBold", str(heiti_medium), subfontIndex=1))
        else:
            candidates = [
                Path("C:/Windows/Fonts/msyh.ttc"),
                Path("C:/Windows/Fonts/simsun.ttc"),
                Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
                Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
            ]
            for candidate in candidates:
                if candidate.exists():
                    register_same_font(candidate)
                    break
            else:
                raise SystemExit(
                    "未找到可嵌入的中文字体。请使用 --font 指定一个支持中文的 .ttf/.ttc 文件。"
                )
    pdfmetrics.registerFontFamily(
        "CNSerif",
        normal="CNSerif",
        bold="CNSerifBold",
        italic="CNSerif",
        boldItalic="CNSerifBold",
    )
    pdfmetrics.registerFontFamily(
        "CNSans",
        normal="CNSans",
        bold="CNSansBold",
        italic="CNSans",
        boldItalic="CNSansBold",
    )


def normalize_display(text: str) -> str:
    """Remove common decorative emoji that many PDF fonts do not contain."""
    for token in ("📅 ", "🔬 ", "📋 ", "👥 ", "📊 ", "📐 ", "📚 ", "📏 ", "⚠️ "):
        text = text.replace(token, "")
    return text.replace("\u2011", "-")


def inline_markup(text: str) -> str:
    """Convert a safe subset of Markdown inline syntax to ReportLab markup."""
    text = normalize_display(text)
    links: list[str] = []

    def save_link(match: re.Match[str]) -> str:
        label = html.escape(match.group(1))
        url = html.escape(match.group(2), quote=True)
        links.append(f'<a href="{url}" color="#245A84"><u>{label}</u></a>')
        return f"@@LINK{len(links) - 1}@@"

    protected = LINK_RE.sub(save_link, text)
    protected = html.escape(protected)
    protected = BOLD_RE.sub(r"<b>\1</b>", protected)
    for index, link in enumerate(links):
        protected = protected.replace(f"@@LINK{index}@@", link)
    return protected


class Rule(Flowable):
    def __init__(self, width: float, color=LINE, thickness=0.7, space=5 * mm):
        super().__init__()
        self.width = width
        self.color = color
        self.thickness = thickness
        self.height = space

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, self.height / 2, self.width, self.height / 2)


class SectionMarker(Flowable):
    """Set the running header before a following PageBreak."""

    def __init__(self, section: str):
        super().__init__()
        self.section = section
        self.width = 0
        self.height = 0

    def draw(self):
        self.canv._doctemplate.current_section = self.section


class ReportDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str, *, short_title: str, **kwargs):
        super().__init__(filename, **kwargs)
        self.short_title = short_title
        self.current_section = "报告"

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        level = getattr(flowable, "_toc_level", None)
        if level is None:
            return
        text = getattr(flowable, "_toc_text", flowable.getPlainText())
        key = getattr(flowable, "_bookmark_name", None)
        if key:
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=level == 0)
        self.notify("TOCEntry", (level, text, self.page, key))
        if level == 0:
            self.current_section = text


def draw_cover(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - 13 * mm, PAGE_W, 13 * mm, fill=1, stroke=0)
    canvas.setFillColor(ACCENT)
    canvas.rect(0, 0, 6 * mm, PAGE_H, fill=1, stroke=0)
    canvas.restoreState()


def draw_body(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    left = doc.leftMargin
    right = PAGE_W - doc.rightMargin
    header_y = PAGE_H - 15 * mm
    canvas.setFont("CNSans", 7.5)
    canvas.setFillColor(MUTED)
    section = doc.current_section
    if len(section) > 35:
        section = section[:35] + "…"
    report_title = doc.short_title
    if len(report_title) > 28:
        report_title = report_title[:28] + "…"
    canvas.drawString(left, header_y, section)
    canvas.drawRightString(right, header_y, report_title)
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.6)
    canvas.line(left, header_y - 3 * mm, right, header_y - 3 * mm)
    canvas.line(left, 15 * mm, right, 15 * mm)
    canvas.setFont("CNSans", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(left, 10.8 * mm, "Markdown → PDF")
    canvas.drawRightString(right, 10.8 * mm, f"{doc.page:02d}")
    canvas.restoreState()


def draw_toc(canvas, doc):
    previous = doc.current_section
    doc.current_section = "目录"
    draw_body(canvas, doc)
    doc.current_section = previous


def make_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "CoverKickerCN",
            fontName="CNSansBold",
            fontSize=10,
            leading=14,
            textColor=ACCENT,
            alignment=TA_LEFT,
            spaceAfter=8 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "CoverTitleCN",
            fontName="CNSerifBlack",
            fontSize=25,
            leading=36,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=8 * mm,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            "CoverMetaCN",
            fontName="CNSans",
            fontSize=9.2,
            leading=15,
            textColor=MUTED,
            alignment=TA_LEFT,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            "BodyCN",
            fontName="CNSerif",
            fontSize=9.65,
            leading=17.4,
            textColor=TEXT,
            alignment=TA_JUSTIFY,
            wordWrap="CJK",
            firstLineIndent=19.3,
            spaceAfter=3.2 * mm,
            allowWidows=0,
            allowOrphans=0,
        )
    )
    styles.add(
        ParagraphStyle(
            "BulletCN",
            parent=styles["BodyCN"],
            leftIndent=5 * mm,
            firstLineIndent=-4 * mm,
            bulletIndent=0,
            fontSize=9.15,
            leading=15.9,
            spaceAfter=2.1 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "QuoteCN",
            fontName="CNSerif",
            fontSize=9,
            leading=15.5,
            textColor=colors.HexColor("#4D5968"),
            leftIndent=7 * mm,
            rightIndent=5 * mm,
            borderColor=ACCENT,
            borderWidth=1.3,
            borderPadding=(3 * mm, 4 * mm, 3 * mm, 5 * mm),
            backColor=colors.HexColor("#F7F2EE"),
            wordWrap="CJK",
            spaceBefore=2 * mm,
            spaceAfter=4 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "H2CN",
            fontName="CNSansBold",
            fontSize=17,
            leading=25,
            textColor=NAVY,
            wordWrap="CJK",
            spaceAfter=7 * mm,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "H3CN",
            fontName="CNSansBold",
            fontSize=12,
            leading=19,
            textColor=BLUE,
            wordWrap="CJK",
            spaceBefore=5 * mm,
            spaceAfter=3 * mm,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "TOCTitleCN",
            fontName="CNSerifBlack",
            fontSize=24,
            leading=30,
            textColor=NAVY,
            spaceAfter=8 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "TOC0CN",
            fontName="CNSansBold",
            fontSize=10.5,
            leading=19,
            textColor=NAVY,
            spaceBefore=2.2 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "TOC1CN",
            fontName="CNSerif",
            fontSize=8.5,
            leading=14.5,
            textColor=MUTED,
            leftIndent=6 * mm,
        )
    )
    styles.add(
        ParagraphStyle(
            "SmallCN",
            fontName="CNSans",
            fontSize=7.8,
            leading=12.5,
            textColor=MUTED,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            "TableHeaderCN",
            fontName="CNSansBold",
            fontSize=8.2,
            leading=12.5,
            textColor=WHITE,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            "TableLabelCN",
            fontName="CNSansBold",
            fontSize=8.2,
            leading=12.5,
            textColor=NAVY,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            "TableValueCN",
            fontName="CNSerif",
            fontSize=8.2,
            leading=12.5,
            textColor=TEXT,
            wordWrap="CJK",
        )
    )
    return styles


def parse_table(lines: list[str], start: int, styles) -> tuple[Table, int]:
    rows: list[list[str]] = []
    index = start
    while index < len(lines) and lines[index].strip().startswith("|"):
        cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
        if not all(TABLE_DIVIDER_RE.fullmatch(cell) for cell in cells):
            rows.append(cells)
        index += 1
    column_count = max(len(row) for row in rows)
    rows = [row + [""] * (column_count - len(row)) for row in rows]
    formatted = []
    for row_index, row in enumerate(rows):
        formatted.append(
            [
                Paragraph(
                    inline_markup(cell),
                    styles[
                        "TableHeaderCN"
                        if row_index == 0
                        else ("TableLabelCN" if column_count == 2 and col_index == 0 else "TableValueCN")
                    ],
                )
                for col_index, cell in enumerate(row)
            ]
        )
    usable = PAGE_W - 44 * mm
    if column_count == 2:
        widths = [usable * 0.24, usable * 0.76]
    else:
        widths = [usable / column_count] * column_count
    table = Table(formatted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("BACKGROUND", (0, 1), (0, -1), PALE_BLUE),
                ("BACKGROUND", (1, 1), (-1, -1), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3.2 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3.2 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2 * mm),
            ]
        )
    )
    return table, index


def make_heading(text: str, level: int, styles, sequence: int) -> Paragraph:
    key = f"heading-{sequence}"
    style = styles["H2CN" if level == 0 else "H3CN"]
    paragraph = Paragraph(f'<a name="{key}"/>{inline_markup(text)}', style)
    paragraph._toc_level = level
    paragraph._toc_text = normalize_display(text)
    paragraph._bookmark_name = key
    return paragraph


def document_title(lines: list[str], fallback: str) -> tuple[str, int]:
    for index, line in enumerate(lines):
        if line.strip().startswith("# "):
            return normalize_display(line.strip()[2:].strip()), index
    return fallback, -1


def is_contents_heading(line: str) -> bool:
    if not line.strip().startswith("## "):
        return False
    title = line.strip()[3:].strip().lower()
    return title in {"目录", "contents", "table of contents"}


def first_body_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if line.strip().startswith("## "):
            if not is_contents_heading(line):
                return index
            scan = index + 1
            while scan < len(lines) and not lines[scan].strip().startswith("## "):
                scan += 1
            return scan
    return len(lines)


def cover_elements(lines: list[str], title_index: int, body_index: int):
    meta_lines: list[str] = []
    quote = ""
    tables: list[int] = []
    stop = body_index if body_index < len(lines) else len(lines)
    index = max(title_index + 1, 0)
    while index < stop:
        stripped = lines[index].strip()
        if stripped.startswith("|"):
            tables.append(index)
            while index < stop and lines[index].strip().startswith("|"):
                index += 1
            continue
        if stripped.startswith(">") and not quote:
            quote = stripped.lstrip("> ").strip()
        elif stripped and stripped != "---" and not stripped.startswith("#"):
            meta_lines.append(stripped)
        index += 1
    return meta_lines, quote, tables


def build_story(lines: list[str], title: str, title_index: int, styles, include_toc: bool):
    story: list[Flowable] = []
    usable = PAGE_W - 44 * mm
    body_index = first_body_index(lines)
    front_end = next(
        (index for index, line in enumerate(lines) if line.strip().startswith("## ")),
        body_index,
    )
    meta_lines, quote, front_tables = cover_elements(lines, title_index, front_end)

    story.extend(
        [
            Spacer(1, 22 * mm),
            Paragraph("MARKDOWN REPORT", styles["CoverKickerCN"]),
            Paragraph(inline_markup(title), styles["CoverTitleCN"]),
            Rule(usable, ACCENT, 1.4, 8 * mm),
        ]
    )
    if meta_lines:
        story.append(Paragraph("<br/>".join(inline_markup(line) for line in meta_lines[:4]), styles["CoverMetaCN"]))
        story.append(Spacer(1, 7 * mm))
    if front_tables:
        table, _ = parse_table(lines, front_tables[0], styles)
        story.append(table)
        story.append(Spacer(1, 6 * mm))
    if quote:
        story.append(Paragraph(inline_markup(quote), styles["QuoteCN"]))
    story.append(Spacer(1, 7 * mm))
    story.append(Paragraph("由 Markdown 自动生成 · 中文字体嵌入 · 链接可点击", styles["SmallCN"]))

    first_section = "正文"
    for line in lines[body_index:]:
        if line.strip().startswith("## "):
            first_section = line.strip()[3:].strip()
            break

    if include_toc:
        story.extend([NextPageTemplate("TOC"), PageBreak()])
        story.append(Paragraph("目录", styles["TOCTitleCN"]))
        story.append(Rule(usable, ACCENT, 1.2, 5 * mm))
        toc = TableOfContents()
        toc.levelStyles = [styles["TOC0CN"], styles["TOC1CN"]]
        toc.dotsMinLevel = 0
        story.append(toc)
        story.append(SectionMarker(first_section))
        story.append(NextPageTemplate("Body"))
        story.append(PageBreak())
    else:
        story.extend(
            [
                SectionMarker(first_section),
                NextPageTemplate("Body"),
                PageBreak(),
            ]
        )

    sequence = 0
    first_heading = True
    index = body_index
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped == "---":
            story.append(Rule(usable, LINE, 0.7, 7 * mm))
            index += 1
            continue
        if is_contents_heading(stripped):
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("## "):
                index += 1
            continue
        if stripped.startswith("## "):
            text = stripped[3:].strip()
            if not first_heading:
                story.extend([SectionMarker(text), PageBreak()])
            first_heading = False
            sequence += 1
            story.append(make_heading(text, 0, styles, sequence))
            index += 1
            continue
        if stripped.startswith("### "):
            sequence += 1
            story.append(make_heading(stripped[4:].strip(), 1, styles, sequence))
            index += 1
            continue
        if stripped.startswith("|"):
            table, index = parse_table(lines, index, styles)
            story.extend([table, Spacer(1, 3 * mm)])
            continue
        if stripped.startswith(">"):
            story.append(Paragraph(inline_markup(stripped.lstrip("> ").strip()), styles["QuoteCN"]))
            index += 1
            continue
        if stripped.startswith("- "):
            story.append(
                Paragraph(
                    inline_markup(stripped[2:].strip()),
                    styles["BulletCN"],
                    bulletText="•",
                )
            )
            index += 1
            continue
        story.append(Paragraph(inline_markup(stripped), styles["BodyCN"]))
        index += 1
    return story


def output_path_for(source: Path, requested: Path | None) -> Path:
    if requested:
        return requested.expanduser().resolve()
    return source.with_suffix(".pdf")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 Markdown 报告转换为带目录、书签、链接和中文字体的 A4 PDF。"
    )
    parser.add_argument("input", type=Path, help="输入 Markdown 文件")
    parser.add_argument("-o", "--output", type=Path, help="输出 PDF；默认与输入文件同名")
    parser.add_argument("--title", help="覆盖 Markdown 一级标题")
    parser.add_argument("--no-toc", action="store_true", help="不生成自动目录")
    parser.add_argument("--font", type=Path, help="自定义中文 TTF/TTC 字体")
    parser.add_argument("--font-index", type=int, default=0, help="TTC 字体子字体索引，默认 0")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.input.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"输入文件不存在：{source}")
    output = output_path_for(source, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    register_fonts(args)
    styles = make_styles()
    lines = source.read_text(encoding="utf-8").splitlines()
    detected_title, title_index = document_title(lines, source.stem)
    title = args.title or detected_title
    short_title = re.sub(r"\s+", " ", title)
    doc = ReportDocTemplate(
        str(output),
        short_title=short_title,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=24 * mm,
        bottomMargin=22 * mm,
        title=title,
        author="Markdown to PDF CN",
        subject=title,
        creator="markdown-to-pdf-cn",
    )
    cover_frame = Frame(
        22 * mm,
        18 * mm,
        PAGE_W - 44 * mm,
        PAGE_H - 31 * mm,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="cover-frame",
    )
    body_frame = Frame(
        22 * mm,
        22 * mm,
        PAGE_W - 44 * mm,
        PAGE_H - 46 * mm,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="body-frame",
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="Cover", frames=[cover_frame], onPage=draw_cover),
            PageTemplate(id="TOC", frames=[body_frame], onPage=draw_toc),
            PageTemplate(id="Body", frames=[body_frame], onPage=draw_body),
        ]
    )
    story = build_story(lines, title, title_index, styles, not args.no_toc)
    doc.multiBuild(story)
    print(output)


if __name__ == "__main__":
    main()
