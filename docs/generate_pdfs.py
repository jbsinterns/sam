import os
import subprocess
import markdown

DOCS_DIR = r"c:\Users\Jbs\Downloads\sam\docs"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

CSS_STYLES = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

@page {
    size: A4;
    margin: 18mm 16mm 18mm 16mm;
    @bottom-right {
        content: counter(page);
    }
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    color: #1e293b;
    line-height: 1.65;
    font-size: 10.5pt;
    background: #ffffff;
    margin: 0;
    padding: 0;
}

h1 {
    font-size: 22pt;
    font-weight: 700;
    color: #0f172a;
    border-bottom: 2.5px solid #0284c7;
    padding-bottom: 8px;
    margin-top: 0;
    margin-bottom: 16px;
    page-break-after: avoid;
}

h2 {
    font-size: 14pt;
    font-weight: 600;
    color: #0369a1;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 5px;
    margin-top: 24px;
    margin-bottom: 12px;
    page-break-after: avoid;
}

h3 {
    font-size: 11.5pt;
    font-weight: 600;
    color: #0f172a;
    margin-top: 18px;
    margin-bottom: 8px;
    page-break-after: avoid;
}

p, li {
    color: #334155;
    font-size: 10pt;
}

ul, ol {
    padding-left: 22px;
    margin-top: 6px;
    margin-bottom: 12px;
}

li {
    margin-bottom: 4px;
}

hr {
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 20px 0;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 14px 0;
    font-size: 9pt;
    page-break-inside: avoid;
}

th, td {
    padding: 8px 10px;
    border: 1px solid #cbd5e1;
    text-align: left;
}

th {
    background-color: #f1f5f9;
    color: #0f172a;
    font-weight: 600;
}

tr:nth-child(even) td {
    background-color: #f8fafc;
}

code {
    font-family: 'JetBrains Mono', Consolas, 'Courier New', monospace;
    font-size: 9pt;
    background-color: #f1f5f9;
    color: #0369a1;
    padding: 2px 5px;
    border-radius: 4px;
    border: 1px solid #e2e8f0;
}

pre {
    background-color: #0f172a;
    color: #f8fafc;
    padding: 12px 14px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 8.5pt;
    line-height: 1.5;
    page-break-inside: avoid;
    margin: 12px 0;
}

pre code {
    background: transparent;
    color: #f8fafc;
    padding: 0;
    border: none;
    font-size: 8.5pt;
}

blockquote {
    border-left: 4px solid #0284c7;
    margin: 14px 0;
    padding: 8px 14px;
    background-color: #f0f9ff;
    color: #0369a1;
    border-radius: 0 6px 6px 0;
    page-break-inside: avoid;
}

blockquote p {
    color: #0369a1;
    margin: 0;
}

.footer {
    margin-top: 30px;
    border-top: 1px solid #e2e8f0;
    padding-top: 8px;
    font-size: 8pt;
    color: #94a3b8;
    display: flex;
    justify-content: space-between;
}
"""

def convert_md_to_pdf(md_filename, pdf_filename):
    md_path = os.path.join(DOCS_DIR, md_filename)
    pdf_path = os.path.join(DOCS_DIR, pdf_filename)
    temp_html = os.path.join(DOCS_DIR, md_filename.replace(".md", ".temp.html"))

    print(f"\nProcessing {md_filename} -> {pdf_filename}...")
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    html_content = markdown.markdown(
        md_text,
        extensions=[
            "extra",
            "codehilite",
            "tables",
            "toc",
            "nl2br"
        ]
    )

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{md_filename.replace('.md', '')}</title>
<style>
{CSS_STYLES}
</style>
</head>
<body>
{html_content}
<div class="footer">
    <span>SAM Rover Autonomous Robotics Platform</span>
    <span>Alpha Build Documentation</span>
</div>
</body>
</html>
"""

    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(full_html)

    # Invoke headless Edge to print PDF
    cmd = [
        EDGE_EXE,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        temp_html
    ]

    print(f"Running Microsoft Edge headless to generate vector PDF...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if os.path.exists(temp_html):
        try:
            os.remove(temp_html)
        except Exception:
            pass

    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
        size_kb = round(os.path.getsize(pdf_path) / 1024, 1)
        print(f"SUCCESS: Generated {pdf_path} ({size_kb} KB)")
        return True
    else:
        print(f"ERROR: Failed to generate {pdf_path}")
        print("Stderr:", result.stderr)
        return False

if __name__ == "__main__":
    docs = [
        ("TECHNICAL_DEPLOYMENT_SOP.md", "TECHNICAL_DEPLOYMENT_SOP.pdf"),
        ("USER_OPERATOR_GUIDE.md", "USER_OPERATOR_GUIDE.pdf"),
    ]
    for md_file, pdf_file in docs:
        convert_md_to_pdf(md_file, pdf_file)
