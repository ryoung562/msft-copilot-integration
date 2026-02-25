#!/usr/bin/env python3
"""Generate PDF from HTML using weasyprint or pdfkit."""

import subprocess
import sys
from pathlib import Path

def main():
    html_file = "PARTNER_DATA_COLLECTION_GUIDE.html"
    pdf_file = "PARTNER_DATA_COLLECTION_GUIDE.pdf"

    if not Path(html_file).exists():
        print(f"Error: {html_file} not found")
        sys.exit(1)

    # Try weasyprint first (better quality)
    try:
        import weasyprint
        print("Using WeasyPrint for PDF generation...")
        weasyprint.HTML(filename=html_file).write_pdf(pdf_file)
        print(f"✅ PDF generated: {pdf_file}")
        return
    except ImportError:
        print("WeasyPrint not available, trying pdfkit...")

    # Try pdfkit (wkhtmltopdf wrapper)
    try:
        import pdfkit
        print("Using pdfkit for PDF generation...")
        pdfkit.from_file(html_file, pdf_file)
        print(f"✅ PDF generated: {pdf_file}")
        return
    except (ImportError, OSError):
        print("pdfkit not available...")

    # Fallback: use macOS print command if available
    print("\nInstalling WeasyPrint for high-quality PDF generation...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "weasyprint"],
                      check=True, capture_output=True)
        import weasyprint
        weasyprint.HTML(filename=html_file).write_pdf(pdf_file)
        print(f"✅ PDF generated: {pdf_file}")
        return
    except Exception as e:
        print(f"Failed to install WeasyPrint: {e}")

    print("\n" + "="*70)
    print("MANUAL CONVERSION REQUIRED")
    print("="*70)
    print(f"\n{html_file} has been generated.")
    print("\nTo convert to PDF:")
    print("1. Open the HTML file in your browser:")
    print(f"   open {html_file}")
    print("2. Press Cmd+P to print")
    print("3. Select 'Save as PDF' from the destination dropdown")
    print(f"4. Save as '{pdf_file}'")
    print("\n" + "="*70)

if __name__ == "__main__":
    main()
