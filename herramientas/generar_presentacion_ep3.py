"""Genera la presentacion 16:9 (EP3) en PDF.

Uso:  python herramientas/generar_presentacion_ep3.py

Pipeline: Markdown -> HTML con CSS de diapositiva -> Edge headless -> PDF.
Las diapositivas se separan con una linea que contenga solo '---'.
Valida que no excedan el maximo de 6 laminas.
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

import markdown
from pypdf import PdfReader

ROOT = pathlib.Path(__file__).resolve().parent.parent
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# --- CSS de diapositiva 16:9 (33,87 x 19,05 cm) ---------------------------
CSS_SLIDE = """
  @page { size: 33.87cm 19.05cm; margin: 0; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: "Segoe UI", Calibri, Arial, sans-serif;
         color: #14181d; }
  .slide { width: 33.87cm; height: 19.05cm; padding: 1.15cm 1.5cm 1.0cm;
           page-break-after: always; position: relative; background: #fff;
           display: flex; flex-direction: column; }
  .slide:last-of-type { page-break-after: auto; }
  .cab { border-bottom: 3px solid #0b3d6b; padding-bottom: 5px;
         margin-bottom: 0.55cm; display: flex; align-items: flex-end; gap: 12px;
         flex: 0 0 auto; }
  .cab .num { font-size: 12pt; font-weight: bold; color: #fff; background: #0b3d6b;
              border-radius: 3px; padding: 1px 7px; }
  .cab h2 { font-size: 25pt; margin: 0; color: #0b3d6b; line-height: 1.1; }
  .cuerpo { font-size: 17pt; line-height: 1.34; flex: 1 1 auto;
            display: flex; flex-direction: column; justify-content: safe center; }
  .cuerpo p { margin: 0.25em 0; }
  .cuerpo ul, .cuerpo ol { margin: 0.2em 0 0.2em 0.9em; padding-left: 0.3em; }
  .cuerpo li { margin: 0.22em 0; }
  .cuerpo strong { color: #0b3d6b; }
  .cuerpo table { border-collapse: collapse; width: 100%; font-size: 13.5pt;
                  margin: 0.15em 0 0.3em; }
  .cuerpo th, .cuerpo td { border: 0.6px solid #8a97a5; padding: 6px 9px;
                           vertical-align: top; text-align: left; }
  .cuerpo th { background: #e8eef5; }
  .cuerpo code { font-family: Consolas, monospace; font-size: 11.5pt;
                 background: #f2f4f7; padding: 0 2px; }
  .cuerpo .mini { font-size: 11.5pt; color: #2b3742; }
  .cuerpo pre { background: #f6f8fb; border-left: 4px solid #0b3d6b;
                padding: 8px 11px; margin: 0.3em 0; }
  .cuerpo pre code { background: none; font-size: 12.5pt; }
  .cuerpo p:has(> img) { margin: 0.1em 0; text-align: center; }
  .cuerpo img { display: block; margin: 0 auto; width: 28cm; height: 11.9cm;
                object-fit: contain; }
  .cuerpo img.mitad { height: 8.4cm; }
  footer { position: absolute; bottom: 0.55cm; left: 1.5cm; right: 1.5cm;
           display: flex; justify-content: space-between;
           font-size: 9.5pt; color: #6b7785;
           border-top: 0.8px solid #c9d2dc; padding-top: 3px; }
  /* Portada */
  .slide.portada { display: flex; flex-direction: column; justify-content: center;
                   background: #0b3d6b; color: #fff; padding: 2cm 2.6cm; }
  .slide.portada .cuerpo { flex: 0 0 auto; justify-content: flex-start;
                           font-size: 17pt; }
  .slide.portada h1 { font-size: 40pt; margin: 0 0 0.25cm; line-height: 1.1;
                      color: #fff; border: 0; }
  .slide.portada p { font-size: 17pt; margin: 0.18cm 0; color: #dce8f4; }
  .slide.portada strong { color: #fff; }
  .slide.portada footer { display: none; }
  /* Diapositiva de cierre */
  .slide.cierre { background: #0b3d6b; color: #fff; }
  .slide.cierre .cuerpo { color: #e8f0f8; }
  .slide.cierre .cuerpo strong { color: #fff; }
  .slide.cierre .cab { border-bottom-color: #fff; }
  .slide.cierre .cab h2 { color: #fff; }
  .slide.cierre .cab .num { background: #fff; color: #0b3d6b; }
  .slide.cierre footer { color: #b9cde0; border-top-color: #2c5a85; }
"""

# --- CSS de documento A4 (guion) -----------------------------------------
CSS_DOC = """
  @page { size: A4; margin: 1.5cm 1.7cm 1.4cm 1.7cm; }
  body { font-family: Georgia, "Times New Roman", serif; font-size: 9.7pt;
         line-height: 1.23; color: #111; margin: 0; }
  h1 { font-size: 16pt; color: #0b3d6b; border-bottom: 2.5px solid #0b3d6b;
       padding-bottom: 4px; margin: 0 0 0.5em; }
  h2 { font-size: 12.5pt; color: #12456f; margin: 0.9em 0 0.25em; }
  h3 { font-size: 10.4pt; color: #1b4f7a; margin: 0.55em 0 0.18em; }
  p { margin: 0.28em 0; text-align: justify; }
  table { border-collapse: collapse; width: 100%; margin: 0.35em 0 0.5em;
          font-size: 8.6pt; }
  th, td { border: 0.6px solid #7a7a7a; padding: 2px 4px; vertical-align: top; }
  th { background: #e8eef5; text-align: left; }
  ul, ol { margin: 0.25em 0 0.3em 1.1em; padding-left: 0.3em; }
  li { margin: 0.1em 0; text-align: justify; }
  blockquote { margin: 0.4em 0; padding: 5px 10px; background: #f6f8fb;
               border-left: 3px solid #0b3d6b; font-style: italic; }
  h2.salto { page-break-before: always; }
  h2, h3 { page-break-after: avoid; }
  table, blockquote, ul, ol { page-break-inside: avoid; }
  code { font-family: Consolas, monospace; font-size: 8.8pt; background: #f2f4f7; }
"""


def reducir_imagenes(cuerpo_html):
    """Copia las imagenes a _pres/ con ancho <= 1100 px.

    Edge escala todo el documento cuando una imagen tiene un ancho intrinseco
    mayor que la pagina; reducirlas antes de imprimir evita ese escalado y
    ademas baja el peso del PDF.
    """
    from PIL import Image

    destino = ROOT / "herramientas" / "_pres"
    destino.mkdir(parents=True, exist_ok=True)
    cache = {}

    def reemplazo(m):
        ruta = m.group(1)
        if ruta in cache:
            return f'src="{cache[ruta]}"'
        origen = (ROOT / ruta).resolve()
        if not origen.exists():
            return m.group(0)
        im = Image.open(origen)
        if im.width > 1100:
            alto = round(im.height * 1100 / im.width)
            im = im.convert("RGB").resize((1100, alto), Image.LANCZOS)
        else:
            im = im.convert("RGB")
        salida = destino / origen.name
        im.save(salida, "PNG", optimize=True)
        rel = f"_pres/{origen.name}"
        cache[ruta] = rel
        return f'src="{rel}"'

    return re.sub(r'src="(?!http|file:|\.\./|/)([^"]+)"', reemplazo, cuerpo_html)


def a_html(texto, css, es_slide):
    if es_slide:
        partes = re.split(r"^\s*---\s*$", texto, flags=re.M)
        slides = []
        for i, parte in enumerate(p for p in partes if p.strip()):
            parte = parte.strip()
            m = re.search(r"^#{1,3}\s+(.*)$", parte, re.M)
            titulo = m.group(1).strip() if m else ""
            cuerpo_md = parte[m.end():] if m else parte
            cuerpo = markdown.markdown(
                cuerpo_md,
                extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
            )
            cuerpo = cuerpo.replace('class="fig-mitad"', 'class="mitad"')
            cuerpo = reducir_imagenes(cuerpo)
            clases = "slide"
            if i == 0:
                clases += " portada"
            elif "Gracias" in cuerpo:
                clases += " cierre"
            if i == 0:
                cab = ""
                h1 = titulo
            else:
                cab = (f'<div class="cab"><span class="num">{i + 1}</span>'
                       f'<h2>{titulo}</h2></div>')
                h1 = ""
            pie = (f"<footer><span>EP3 · Equipo 1 · ITY1102</span>"
                   f"<span>{i + 1}</span></footer>") if i > 0 else ""
            encabezado = f"<h1>{h1}</h1>" if h1 else ""
            slides.append(f'<section class="{clases}">{cab}{encabezado}'
                          f'<div class="cuerpo">{cuerpo}</div>{pie}</section>')
        cuerpo_html = "\n".join(slides)
    else:
        cuerpo_html = markdown.markdown(
            texto,
            extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
        )
        cuerpo_html = reducir_imagenes(cuerpo_html)

    return (f'<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
            f'<style>{css}</style></head><body>{cuerpo_html}</body></html>')


def imprimir(html_path, pdf_path):
    edge = next((p for p in EDGE_CANDIDATES if pathlib.Path(p).exists()),
                shutil.which("msedge"))
    if not edge:
        print("ERROR: no se encontro Microsoft Edge")
        return False
    if pdf_path.exists():
        pdf_path.unlink()
    perfil = tempfile.mkdtemp(prefix="edge-pres-")
    try:
        subprocess.run(
            [edge, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             "--window-size=1280,720", "--force-device-scale-factor=1",
             f"--user-data-dir={perfil}", f"--print-to-pdf={pdf_path}",
             html_path.as_uri()],
            capture_output=True, text=True, timeout=180,
        )
        for _ in range(60):
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                return True
            time.sleep(0.5)
        return False
    finally:
        shutil.rmtree(perfil, ignore_errors=True)


MAX_LAMINAS = 6


def construir():
    entrada = ROOT / "presentacion" / "EP3_Presentacion.md"
    html_out = ROOT / "herramientas" / "EP3_Presentacion.html"
    pdf_out = ROOT / "entregables" / "EP3_Presentacion_Equipo1.pdf"

    texto = entrada.read_text(encoding="utf-8")
    html = a_html(texto, CSS_SLIDE, True)
    html_out.parent.mkdir(parents=True, exist_ok=True)
    html_out.write_text(html, encoding="utf-8")

    pdf_out.parent.mkdir(parents=True, exist_ok=True)
    if not imprimir(html_out, pdf_out):
        print("ERROR: no se pudo generar el PDF")
        return 1

    paginas = len(PdfReader(str(pdf_out)).pages)
    kb = pdf_out.stat().st_size // 1024
    print(f"PDF: {pdf_out.relative_to(ROOT)} -> {paginas} laminas, {kb} KB")
    if paginas > MAX_LAMINAS:
        print(f"FALLA: excede el maximo de {MAX_LAMINAS} laminas ({paginas})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(construir())
