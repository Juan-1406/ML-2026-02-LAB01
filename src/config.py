"""Rutas y constantes compartidas del laboratorio.

Toda ruta se calcula desde la raíz del repositorio para que el pipeline
funcione igual si se ejecuta `python main.py` desde cualquier cwd.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Raíz del repositorio (un nivel sobre src/).
RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

DATA_DIR = RAIZ / "data"
RUTA_URLS = DATA_DIR / "urls.csv"
RUTA_CONSULTAS = DATA_DIR / "consultas.csv"
DIR_RAW = DATA_DIR / "raw"
DIR_PROCESSED = DATA_DIR / "processed"
DIR_JSON = DATA_DIR / "json"
DIR_VAULT = RAIZ / "obsidian_vault"

# Identificación educada ante los servidores (uso académico).
USER_AGENT = (
    "Mozilla/5.0 (compatible; LabNoticiasUCN/1.0; "
    "+https://www.ucn.cl; MachineLearning-LAB01)"
)
TIMEOUT_HTTP = 20
PAUSA_ENTRE_REQUESTS = 1.5

# RSS de Google News restringido a Chile / español latinoamericano.
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
GOOGLE_NEWS_PARAMS_BASE = {
    "hl": "es-419",
    "gl": "CL",
    "ceid": "CL:es-419",
}

COLUMNAS_URLS = ["id_noticia", "fuente", "url", "categoria_busqueda"]

# Gemini: la clave vive en .env (nunca en el código ni en Git).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"
