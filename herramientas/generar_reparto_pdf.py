import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import generar_pdf_ep3 as base

ROOT = base.ROOT
base.SRC = ROOT / "presentacion" / "EP3_Reparto_Video.md"
base.HTML_OUT = ROOT / "herramientas" / "EP3_Reparto_Video.html"
base.PDF_OUT = ROOT / "entregables" / "EP3_Reparto_Video.pdf"

if __name__ == "__main__":
    sys.exit(base.main())
