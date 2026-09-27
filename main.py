#!/usr/bin/env python3
"""Orquestador del laboratorio (punto de entrada).

Uso (con el entorno conda activado):

    python main.py descubrir   # Google News RSS → data/urls.csv
    python main.py capturar    # URLs → data/raw + data/processed
    python main.py extraer     # Gemini → data/json (requiere GEMINI_API_KEY)
    python main.py obsidian    # TODO(alumno) vault Markdown
    python main.py analizar    # TODO(alumno) Data Understanding
    python main.py pipeline    # descubrir + capturar + extraer; avisa pendientes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite `python main.py` sin instalar el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.pipeline import PipelineLaboratorio  # noqa: E402


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pipeline de noticias delictuales → JSON → Obsidian (LAB01).",
    )
    parser.add_argument(
        "etapa",
        choices=["descubrir", "capturar", "extraer", "obsidian", "analizar", "pipeline"],
        help="Etapa del laboratorio a ejecutar.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    pipeline = PipelineLaboratorio()
    acciones = {
        "descubrir": pipeline.ejecutar_descubrimiento,
        "capturar": pipeline.ejecutar_captura,
        "extraer": pipeline.ejecutar_extraccion,
        "obsidian": pipeline.ejecutar_obsidian,
        "analizar": pipeline.ejecutar_analisis,
        "pipeline": pipeline.ejecutar_pipeline,
    }
    acciones[args.etapa]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
