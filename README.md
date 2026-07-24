# Markdown to PDF CN

把中文 Markdown 报告转换为排版良好的 A4 PDF。

主要功能：

- 自动封面、目录、页眉、页脚和页码
- 保留二级、三级标题层级，并生成 PDF 书签
- 保留 Markdown 表格、引用框、列表、粗体和外部链接
- 自动嵌入中文字体，避免换电脑后出现方框或缺字
- 章节自动分页，目录页码与正文同步

## 安装

需要 Python 3.10 或更高版本。

```bash
python3 -m pip install -r requirements.txt
```

## 使用

最简单的方式：

```bash
python3 md_to_pdf.py 报告.md
```

PDF 默认生成在 Markdown 文件旁边。也可以指定输出位置：

```bash
python3 md_to_pdf.py 报告.md -o 输出/报告.pdf
```

其他选项：

```bash
python3 md_to_pdf.py 报告.md \
  --title "自定义报告标题" \
  --no-toc
```

查看全部参数：

```bash
python3 md_to_pdf.py --help
```

## 中文字体

在 macOS 上，脚本会自动使用系统自带的宋体和黑体。

如果在 Windows、Linux 或精简系统中运行，可以手动指定支持中文的 TrueType 字体：

```bash
python3 md_to_pdf.py 报告.md --font "/path/to/chinese-font.ttf"
```

对于 `.ttc` 字体集合，可通过 `--font-index` 指定子字体索引：

```bash
python3 md_to_pdf.py 报告.md \
  --font "/path/to/chinese-font.ttc" \
  --font-index 0
```

## 支持的 Markdown 格式

当前重点支持研究报告常用格式：

- `#` 一级标题：作为封面标题
- `##` 二级标题：作为章节标题并分页
- `###` 三级标题：作为小节标题
- Markdown 表格
- `>` 引用
- `-` 无序列表
- `**粗体**`
- `[文字](https://example.com)` 外部链接

如果原文含有 `## 目录`，脚本会用带页码和跳转链接的自动目录替换它。

## 输出检查

重要报告建议在交付前把 PDF 渲染成图片逐页检查，重点确认：

- 中文字体是否完整显示
- 长表格是否跨页正常
- 标题是否被挤到页尾
- 链接和参考文献是否完整

## 许可

MIT License
