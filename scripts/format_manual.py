import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
import os

doc_path = "/home/sam3/sam/docs/SAM_Robot_User_Manual_v1.0.docx"
out_path = "/home/sam3/sam/docs/SAM_Robot_User_Manual_v1.0_Final_Organized.docx"
screenshots_dir = "/home/sam3/sam/docs/screenshots"

fig9_path = os.path.join(screenshots_dir, "Figure_09_Network_Manager.png")
fig10_path = os.path.join(screenshots_dir, "Figure_10_Main_Dashboard.png")

doc = Document(doc_path)
print(f"Loaded document. Paragraphs: {len(doc.paragraphs)}, Tables: {len(doc.tables)}")

# Helper to add image paragraph before a target paragraph
def insert_image_before(paragraph, img_path, width_in):
    new_p = paragraph.insert_paragraph_before()
    new_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    new_p.paragraph_format.space_before = Pt(10)
    new_p.paragraph_format.space_after = Pt(4)
    run = new_p.add_run()
    run.add_picture(img_path, width=Inches(width_in))
    return new_p

# Helper to set table borders
def set_table_borders(table, color="CBD5E1"):
    tblPr = table._tbl.tblPr
    borders = parse_xml(f'''
        <w:tblBorders {nsdecls("w")}>
            <w:top w:val="single" w:sz="4" w:space="0" w:color="{color}"/>
            <w:left w:val="none"/>
            <w:bottom w:val="single" w:sz="4" w:space="0" w:color="{color}"/>
            <w:right w:val="none"/>
            <w:insideH w:val="single" w:sz="4" w:space="0" w:color="{color}"/>
            <w:insideV w:val="none"/>
        </w:tblBorders>
    ''')
    tblPr.append(borders)

# 1. Insert screenshots
inserted_9 = False
inserted_10 = False

for i, p in enumerate(doc.paragraphs):
    txt = p.text.strip()
    if "Figure 9" in txt and not inserted_9:
        insert_image_before(p, fig9_path, 5.5)
        inserted_9 = True
        print(f"Inserted Figure 9 above P[{i}]")
    elif "Figure 10" in txt and not inserted_10:
        insert_image_before(p, fig10_path, 6.2)
        inserted_10 = True
        print(f"Inserted Figure 10 above P[{i}]")

# 2. Organize Typography, Indentation, and Spacing
for p in doc.paragraphs:
    txt = p.text.strip()
    
    # Clean up empty paragraphs with huge spacing
    if not txt:
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.0
        continue
        
    # Figure captions
    if txt.startswith("Figure ") or txt.startswith("Fig. "):
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(12)
        p.paragraph_format.keep_with_next = False
        for r in p.runs:
            r.font.italic = True
            r.font.size = Pt(9.5)
            r.font.color.rgb = RGBColor(71, 85, 105)
            
    # Major Section Numbered Headings ("1. ", "2. ", ..., "22. ")
    elif any(txt.startswith(f"{n}. ") for n in range(1, 25)):
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(16)
        p.paragraph_format.space_after = Pt(6)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for r in p.runs:
            r.font.bold = True
            r.font.size = Pt(13)
            r.font.color.rgb = RGBColor(10, 42, 107) # Brand Navy
            
    # Part Titles ("PART I", "PART II")
    elif txt.startswith("PART I") or txt.startswith("PART II"):
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(22)
        p.paragraph_format.space_after = Pt(8)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for r in p.runs:
            r.font.bold = True
            r.font.size = Pt(15)
            r.font.color.rgb = RGBColor(10, 42, 107)

    # Subheadings ("Step 1:", "Method A:", etc.)
    elif txt.startswith("Step ") or txt.startswith("Method ") or txt in ["Battery requirement", "READY TO USE", "NOT INCLUDED", "General safety rules"]:
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(4)
        for r in p.runs:
            r.font.bold = True
            r.font.size = Pt(11)
            r.font.color.rgb = RGBColor(30, 41, 59)
            
    # Warnings / Cautions
    elif txt.startswith("WARNING") or txt.startswith("CAUTION"):
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        for r in p.runs:
            r.font.bold = True
            r.font.color.rgb = RGBColor(185, 28, 28) # Crimson Red
            
    # Normal Body Paragraphs
    else:
        # Standard professional paragraph spacing
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(5)

# 3. Organize Tables
for table in doc.tables:
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table, "CBD5E1")
    
    for row_idx, row in enumerate(table.rows):
        trPr = row._tr.get_or_add_trPr()
        trPr.append(parse_xml(r'<w:cantSplit xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'))
        
        # Table Header
        if row_idx == 0:
            trPr.append(parse_xml(r'<w:tblHeader xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'))
            for cell in row.cells:
                # Add light navy tint to header cells if not shaded
                shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="E8EEF9"/>')
                cell._tc.get_or_add_tcPr().append(shd)
                for p in cell.paragraphs:
                    p.paragraph_format.space_before = Pt(4)
                    p.paragraph_format.space_after = Pt(4)
                    for r in p.runs:
                        r.font.bold = True
                        r.font.color.rgb = RGBColor(10, 42, 107)
        else:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.space_before = Pt(3)
                    p.paragraph_format.space_after = Pt(3)

doc.save(out_path)
print(f"Successfully saved professionally organized document to: {out_path}")

