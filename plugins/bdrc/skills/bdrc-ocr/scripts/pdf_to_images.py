#!/usr/bin/env python3
"""Convert PDF pages to images for OCR processing."""
import os
import sys
from pdf2image import convert_from_path

def main():
    if len(sys.argv) < 2:
        print("Usage: pdf_to_images.py <pdf_path> [output_dir] [dpi]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(pdf_path), "_ocr_images"
    )
    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 300

    if not os.path.isfile(pdf_path):
        print(f"Error: {pdf_path} not found")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    images = convert_from_path(pdf_path, dpi=dpi)
    for i, img in enumerate(images, 1):
        out_path = os.path.join(output_dir, f"page_{i:04d}.png")
        img.save(out_path, "PNG")
    print(f"Converted {len(images)} pages → {output_dir}")

if __name__ == "__main__":
    main()
