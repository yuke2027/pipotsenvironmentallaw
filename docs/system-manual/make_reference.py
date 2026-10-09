"""Patch pandoc's default reference.docx into a formal Chinese-government style.

Run: python make_reference.py   (expects ref-src.docx = pandoc default reference)
Produces: reference.docx
"""
import re
import zipfile

SRC = "ref-src.docx"
OUT = "reference.docx"

with zipfile.ZipFile(SRC) as z:
    styles = z.read("word/styles.xml").decode("utf8")
    names = z.namelist()
    blobs = {n: z.read(n) for n in names}

def sub(pattern, repl, text, count=0):
    out, n = re.subn(pattern, repl, text, count=count, flags=re.S)
    assert n > 0, f"pattern not found: {pattern[:60]}"
    return out

# 1) Document defaults: Times/宋体, 12pt (24 half-points)
styles = sub(
    r'<w:docDefaults>.*?<w:rPr>',
    '<w:docDefaults><w:rPrDefault><w:rPr>'
    '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体" w:cs="Times New Roman"/>'
    '<w:sz w:val="24"/><w:szCs w:val="24"/>',
    styles, 1)

# 2) Helper: inject eastAsia font + size + color into a style block by styleId
def patch_style(text, sid, rpr=None, ppr=None):
    m = re.search(r'(<w:style [^>]*w:styleId="%s".*?</w:style>)' % sid, text, re.S)
    assert m, sid
    block = m.group(1)
    new = block
    if rpr:
        if '<w:rPr>' in new:
            new = re.sub(r'<w:rPr>', '<w:rPr>' + rpr, new, count=1)
        else:
            new = new.replace('</w:style>', '<w:rPr>' + rpr + '</w:rPr></w:style>')
    if ppr:
        if '<w:pPr>' in new:
            new = re.sub(r'<w:pPr>', '<w:pPr>' + ppr, new, count=1)
        else:
            new = new.replace('<w:rPr>', '<w:pPr>' + ppr + '</w:pPr><w:rPr>', 1) if '<w:rPr>' in new else \
                new.replace('</w:style>', '<w:pPr>' + ppr + '</w:pPr></w:style>')
    return text.replace(block, new)

HEI = '<w:rFonts w:eastAsia="黑体" w:ascii="Arial" w:hAnsi="Arial"/>'
SONG = '<w:rFonts w:eastAsia="宋体"/>'
TEAL_DARK = '<w:color w:val="102B37"/>'
TEAL = '<w:color w:val="087F8C"/>'

# 3) Headings: 黑体 + sizes H1 18pt/H2 15pt/H3 13pt/H4 12pt + brand colors
for sid, sz, col in [("Heading1", "36", TEAL_DARK), ("Heading2", "30", TEAL_DARK),
                     ("Heading3", "26", TEAL), ("Heading4", "24", TEAL),
                     ("Heading5", "24", TEAL_DARK), ("Heading6", "24", TEAL_DARK)]:
    styles = patch_style(styles, sid, rpr=HEI + col + f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>',
                         ppr='<w:spacing w:before="280" w:after="160"/>')

# 4) Title / Subtitle / Author / Date: centered cover block
CENTER = '<w:jc w:val="center"/>'
for sid, rpr in [
    ("Title", HEI + TEAL_DARK + '<w:sz w:val="56"/><w:szCs w:val="56"/>'),
    ("Subtitle", SONG + TEAL + '<w:sz w:val="32"/><w:szCs w:val="32"/>'),
    ("Author", SONG + '<w:sz w:val="26"/><w:szCs w:val="26"/>'),
    ("Date", SONG + '<w:sz w:val="26"/><w:szCs w:val="26"/>'),
]:
    styles = patch_style(styles, sid, rpr=rpr, ppr=CENTER + '<w:spacing w:before="200" w:after="160"/>')

# 5) Body Text + Compact + First Paragraph: 1.5 line spacing
LINE = '<w:spacing w:line="360" w:lineRule="auto"/>'
for sid in ("BodyText", "Compact", "FirstParagraph"):
    styles = patch_style(styles, sid, ppr=LINE)

# 6) Table style: explicit single borders (grid) + header shading
m = re.search(r'(<w:style [^>]*w:styleId="Table".*?</w:style>)', styles, re.S)
table_block = m.group(1)
tblpr = ('<w:tblPr><w:tblBorders>'
         '<w:top w:val="single" w:sz="4" w:color="9FB3BC"/>'
         '<w:left w:val="single" w:sz="4" w:color="9FB3BC"/>'
         '<w:bottom w:val="single" w:sz="4" w:color="9FB3BC"/>'
         '<w:right w:val="single" w:sz="4" w:color="9FB3BC"/>'
         '<w:insideH w:val="single" w:sz="4" w:color="C7D6DB"/>'
         '<w:insideV w:val="single" w:sz="4" w:color="C7D6DB"/>'
         '</w:tblBorders><w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>'
         '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr>')
new_block = re.sub(r'<w:tblPr>.*?</w:tblPr>', tblpr, table_block, count=1, flags=re.S)
# banded header shading: first row teal-tinted
if '<w:tblStylePr w:type="firstRow">' in new_block:
    new_block = new_block.replace('<w:tblStylePr w:type="firstRow">',
        '<w:tblStylePr w:type="firstRow"><w:tcPr><w:shd w:val="clear" w:fill="E4F1F2"/></w:tcPr>', 1)
styles = styles.replace(table_block, new_block)

# 7) Captions: centered, 10.5pt, 宋体, gray-teal
for sid in ("ImageCaption", "TableCaption", "Caption"):
    try:
        styles = patch_style(styles, sid,
                             rpr=SONG + '<w:color w:val="5B7180"/><w:sz w:val="21"/><w:szCs w:val="21"/><w:i w:val="0"/>',
                             ppr=CENTER)
    except AssertionError:
        pass

# 8) TOC Heading styled like Heading1
styles = patch_style(styles, "TOCHeading", rpr=HEI + TEAL_DARK + '<w:sz w:val="36"/><w:szCs w:val="36"/>')

blobs["word/styles.xml"] = styles.encode("utf8")
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for n in names:
        z.writestr(n, blobs[n])
print("reference.docx written")
