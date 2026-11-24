# -*- coding: utf-8 -*-
"""Pipeline md -> HTML -> PDF (Edge headless) para la EP3.

Rutas resueltas desde la ubicacion de este script (cwd-independiente):
  informe/EP3_Informe.md  ->  herramientas/EP3_Informe.html  ->  entregables/EP3_Equipo1_HigueraDuranSalazar.pdf

Ademas del PDF:
  - numera las figuras automaticamente (Figura 1, Figura 2, ...)
  - valida que el PDF no exceda 10 paginas
  - informa cuantas figuras se incrustaron

Uso:  python herramientas/generar_pdf_ep3.py
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
SRC = ROOT / "informe" / "EP3_Informe.md"
HTML_OUT = ROOT / "herramientas" / "EP3_Informe.html"
PDF_OUT = ROOT / "entregables" / "EP3_Equipo1_HigueraDuranSalazar.pdf"
MAX_PAGINAS = 10
MIN_FIGURAS = 0

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

CSS = """
  @page { size: A4; margin: 0.9cm 1.35cm 1.0cm 1.35cm; }
  * { box-sizing: border-box; }
  body { font-family: Georgia, "Times New Roman", serif; font-size: 10.6pt;
         line-height: 1.25; color: #111; margin: 0; }
  h1 { font-size: 15.5pt; margin: 0.55em 0 0.3em; color: #0b3d6b;
       border-bottom: 1.6px solid #0b3d6b; padding-bottom: 2px;
       break-after: avoid; page-break-after: avoid; }
  h2 { font-size: 11.6pt; margin: 0.75em 0 0.25em; color: #12456f;
       break-after: avoid; page-break-after: avoid; }
  h3 { font-size: 10.2pt; margin: 0.6em 0 0.18em; color: #1b4f7a;
       break-after: avoid; page-break-after: avoid; }
  p { margin: 0.28em 0; text-align: justify; hyphens: auto; }
  table { border-collapse: collapse; width: 100%; margin: 0.3em 0 0.4em;
          font-size: 9.2pt; line-height: 1.15; }
  th, td { border: 0.6px solid #7a7a7a; padding: 1.6px 3.5px; vertical-align: top; }
  th { background: #e8eef5; text-align: left; font-weight: bold; }
  thead { display: table-header-group; }
  tr { break-inside: avoid; page-break-inside: avoid; }
  table.nobreak { break-inside: avoid; page-break-inside: avoid; }
  ul, ol { margin: 0.25em 0 0.3em 1.15em; padding-left: 0.35em; }
  li { margin: 0.06em 0; text-align: justify; }
  code { font-family: Consolas, "Courier New", monospace; font-size: 8.6pt;
         background: #f3f4f6; padding: 0 1.5px; border-radius: 2px; }
  pre { background: #f7f8fa; border: 0.6px solid #ccd; border-left: 3px solid #12456f;
        padding: 5px 7px; margin: 0.4em 0; font-size: 8.1pt; line-height: 1.15;
        break-inside: avoid; page-break-inside: avoid; overflow: visible; }
  pre code { background: none; font-size: 8.1pt; padding: 0; }
  figure { margin: 0.35em 0 0.45em; text-align: center;
           break-inside: avoid; page-break-inside: avoid; }
  figure img { max-width: 100%; max-height: 11.4cm; height: auto;
               display: block; margin: 0 auto; }
  figure img.fig-n1 { max-width: 84%; }
  figcaption { font-size: 8.2pt; font-style: italic; color: #333;
               margin-top: 2px; text-align: center; }
  .formula { font-family: "Cambria Math", Cambria, Georgia, serif; font-size: 10.4pt;
             text-align: center; margin: 0.45em 0; background: #f6f8fb;
             border-left: 3px solid #12456f; padding: 4px 6px; }
  .refs { column-count: 2; column-gap: 0.7cm; }
  .refs p { margin: 0 0 0.3em 0; text-align: left; font-size: 8.3pt;
            line-height: 1.13; text-indent: 0; break-inside: avoid; }
  p.ref { text-indent: -0.45cm; margin: 0 0 0.26em 0.45cm; text-align: left;
          font-size: 8.3pt; line-height: 1.13; }
  .portada { text-align: center; border-top: 2.5px solid #0b3d6b;
             border-bottom: 2.5px solid #0b3d6b; padding: 6px 0; margin-bottom: 0.6em; }
  .portada .sigla { font-size: 9pt; letter-spacing: 0.9px; text-transform: uppercase;
                    color: #12456f; }
  .portada .titulo { font-size: 17pt; font-weight: bold; color: #0b3d6b;
                     line-height: 1.15; margin: 4px 0; }
  .portada .sub { font-size: 11pt; font-style: italic; }
  div[style*="page-break"] { break-after: page; page-break-after: always; height: 0; }
  strong { font-weight: bold; }
  em { font-style: italic; }
"""


def main() -> int:
    md_text = SRC.read_text(encoding="utf-8")

    # Portada: se sustituye el titulo en el Markdown (antes de convertir),
    # porque despues ya es un <h1> y no coincide.
    md_text = md_text.replace(
        "# EP3 — Despliegue y Optimización de Sistema IA Empresarial",
        '<div class="portada"><div class="sigla">ITY1102 · Arquitectura de Sistemas de '
        'Inteligencia Artificial · Sección 002D</div>'
        '<div class="titulo">Despliegue y optimización de un recomendador<br>'
        'de productos en AWS</div>'
        '<div class="sub">Sistema de recomendación de productos para ShopFast<br>'
        'Informe técnico · Evaluación Parcial N.º 3 · Equipo 1</div></div>',
    )

    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
    )

    # 1) Las imagenes se referencian como diagramas/xxx.png, pero el HTML vive en
    #    herramientas/ -> hay que subir un nivel.
    body = re.sub(
        r'src="(?!http|file:|\.\./|/)([^"]+)"',
        lambda m: f'src="../{m.group(1)}"',
        body,
    )

    # 2) Envolver cada imagen en <figure> con pie numerado.
    contador = {"n": 0}

    def figura(m: re.Match) -> str:
        contador["n"] += 1
        n = contador["n"]
        img = m.group(1)
        alt = m.group(2).strip() or f"Figura {n}"
        return (
            f'<figure>{img}'
            f'<figcaption>Figura {n}. {alt}</figcaption></figure>'
        )

    body = re.sub(
        r"<p>\s*(<img[^>]*?alt=\"([^\"]*)\"[^>]*?>)\s*</p>",
        figura,
        body,
    )
    # Imagenes sin atributo alt
    body = re.sub(
        r"<p>\s*(<img(?![^>]*alt=)[^>]*?>)\s*</p>",
        lambda m: (contador.__setitem__("n", contador["n"] + 1)
                   or f'<figure>{m.group(1)}'
                      f'<figcaption>Figura {contador["n"]}.</figcaption></figure>'),
        body,
    )

    # 3) Referencias: los parrafos entre el titulo 9 y el titulo 10 reciben la
    #    clase .ref (sangria francesa APA), desde el encabezado "N. Referencias"
    #    (h1 o h2) hasta el siguiente encabezado. Se hace aqui y no en el Markdown
    #    porque un <div> contenedor impide que Markdown genere los <p>.
    m_ref = re.search(r"<h[12]>\d+\. Referencias</h[12]>", body)
    if m_ref:
        m_fin = re.search(r"<h[12]>", body[m_ref.end():])
        j = m_ref.end() + m_fin.start() if m_fin else len(body)
        bloque = body[m_ref.start():j].replace("<p>", '<p class="ref">')
        body = body[:m_ref.start()] + bloque + body[j:]

    # 4) Tablas cortas: no se parten entre paginas (evita la fila huerfana).
    def _no_partir(m):
        tabla = m.group(0)
        if tabla.count("<tr>") <= 6:
            return tabla.replace("<table>", '<table class="nobreak">', 1)
        return tabla

    body = re.sub(r"<table>.*?</table>", _no_partir, body, flags=re.S)

    # 4) Portada ya aplicada en el Markdown; nada que hacer aqui.

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>EP3 Equipo 1 - Despliegue de Sistema IA</title>
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>"""

    HTML_OUT.parent.mkdir(parents=True, exist_ok=True)
    HTML_OUT.write_text(html, encoding="utf-8")
    print(f"HTML: {HTML_OUT.relative_to(ROOT)}  ({contador['n']} figuras)")

    edge = next((p for p in EDGE_CANDIDATES if pathlib.Path(p).exists()),
                shutil.which("msedge"))
    if not edge:
        print("ERROR: no se encontro Microsoft Edge")
        return 1

    PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    if PDF_OUT.exists():
        PDF_OUT.unlink()
    perfil = tempfile.mkdtemp(prefix="edge-pdf-")
    try:
        proc = subprocess.run(
            [edge, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--user-data-dir={perfil}", f"--print-to-pdf={PDF_OUT}",
             HTML_OUT.as_uri()],
            capture_output=True, text=True, timeout=180,
        )
        for _ in range(60):
            if PDF_OUT.exists() and PDF_OUT.stat().st_size > 0:
                break
            time.sleep(0.5)
        if not PDF_OUT.exists() or PDF_OUT.stat().st_size == 0:
            print(f"ERROR: Edge no genero el PDF (exit={proc.returncode})\n"
                  f"{proc.stderr[-600:]}")
            return 1
    finally:
        shutil.rmtree(perfil, ignore_errors=True)

    n_paginas = len(PdfReader(str(PDF_OUT)).pages)
    kb = PDF_OUT.stat().st_size // 1024
    rel = PDF_OUT.relative_to(ROOT)
    print(f"PDF:  {rel}  ->  {n_paginas} paginas, {kb} KB")
    print(f"      figuras incrustadas: {contador['n']} (minimo {MIN_FIGURAS})")

    problemas = []
    if n_paginas > MAX_PAGINAS:
        problemas.append(f"excede el limite de {MAX_PAGINAS} paginas ({n_paginas})")
    if contador["n"] < MIN_FIGURAS:
        problemas.append(f"solo {contador['n']} figuras (minimo {MIN_FIGURAS})")
    if problemas:
        for p in problemas:
            print(f"  FALLA: {p}")
        return 1
    print("  OK: dentro de los limites")
    return 0


if __name__ == "__main__":
    sys.exit(main())
