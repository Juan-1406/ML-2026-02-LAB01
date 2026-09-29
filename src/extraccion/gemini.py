"""Extractor Gemini: texto limpio → JSON del contrato del laboratorio.

Extrae solo información explícita en la noticia, en JSON válido.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv

from src.config import DIR_JSON
from src.excepciones import EtapaPendienteAlumno
from src.modelos import NoticiaFuente

load_dotenv()


class ExtractorLLM(ABC):
    """Interfaz de cualquier extractor basado en modelo generativo."""

    @abstractmethod
    def construir_prompt(self, noticia: NoticiaFuente) -> str:
        """Arma el prompt con el esquema JSON y el texto de la noticia."""

    @abstractmethod
    def extraer(self, noticia: NoticiaFuente) -> dict:
        """Devuelve un diccionario que cumple el contrato JSON del laboratorio."""


class ExtractorGemini(ExtractorLLM):
    """Extractor oficial del laboratorio (Gemini)."""

    CAMPOS_OBLIGATORIOS = [
        "id_noticia",
        "titulo",
        "fecha_publicacion",
        "fuente",
        "url",
        "resumen",
        "delitos",
        "personas",
        "organizaciones",
        "lugares",
        "objetos",
        "relaciones",
    ]

    def __init__(self, dir_json=DIR_JSON) -> None:
        self.dir_json = dir_json
        self.dir_json.mkdir(parents=True, exist_ok=True)
        self._modelo = None

    def _obtener_modelo(self):
        if self._modelo is None:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise EtapaPendienteAlumno(
                    modulo="src.extraccion.gemini.ExtractorGemini._obtener_modelo",
                    pista=(
                        "Defina GEMINI_API_KEY en un archivo .env "
                        "(copie .env.example) con su clave de Gemini."
                    ),
                )
            genai.configure(api_key=api_key)
            nombre_modelo = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
            self._modelo = genai.GenerativeModel(nombre_modelo)
        return self._modelo

    def construir_prompt(self, noticia: NoticiaFuente) -> str:
        campos = ", ".join(self.CAMPOS_OBLIGATORIOS)
        return f"""Eres un asistente que extrae información estructurada de noticias
sobre delitos publicadas en medios chilenos.

Reglas estrictas:
- Extrae ÚNICAMENTE información explícita en el texto de la noticia.
- NO inventes personas, roles, delitos, objetos ni relaciones que no aparezcan
  literalmente en el texto.
- Ignora pronombres
- Si un dato no aparece en la noticia, usa null (o una lista vacía [] cuando
  corresponda a un campo de lista).
- Ignora nombres que aparezcan en bloques de "noticias relacionadas",
  publicidad, biografías de columnistas o cualquier sección que no sea el
  cuerpo del hecho policial que se relata (por ejemplo, celebridades citadas
  solo como comparación o clickbait). Si dudas si un nombre pertenece al
  hecho narrado, no lo incluyas.
- En "relaciones", "origen" y "destino" deben ser SIEMPRE un nombre propio
  corto (una persona, organización o lugar concreto), nunca una oración,
  una explicación ni una cita textual. Si la conexión entre dos entidades no
  se puede resumir en un nombre propio para cada extremo, no reportes esa
  relación.
- El "tipo" de una relación es una frase verbal corta en minúsculas, con
  espacios (no guiones bajos), por ejemplo "lidera" o "opera en"; usa
  siempre la misma redacción para el mismo tipo de vínculo dentro de la
  noticia (no mezcles "atacó a" con "atacó con un arma de fuego a" si es el
  mismo hecho).
- Responde EXCLUSIVAMENTE con un objeto JSON válido, sin bloques de código
  markdown (nada de ```), sin explicaciones ni texto adicional antes o
  después del JSON.

El JSON debe tener exactamente estas claves: {campos}.

Esquema y tipos esperados:
{{
  "id_noticia": "{noticia.id_noticia}",
  "titulo": "string o null",
  "fecha_publicacion": "string (ISO 8601) o null",
  "fuente": "{noticia.fuente}",
  "url": "{noticia.url}",
  "resumen": "string breve (2-4 frases) o null",
  "delitos": ["lista de strings, tipos de delito mencionados"],
  "personas": [{{"nombre": "string", "rol": "string o null"}}],
  "organizaciones": ["lista de strings"],
  "lugares": ["lista de strings"],
  "objetos": [
    {{"tipo": "string", "nombre": "string", "cantidad": "número o null", "unidad": "string o null"}}
  ],
  "relaciones": [
    {{"origen": "string", "tipo": "string", "destino": "string"}}
  ]
}}

Usa "id_noticia", "fuente" y "url" tal cual se entregan arriba (no los
inventes ni los modifiques).

Texto de la noticia:
\"\"\"
{noticia.texto_limpio}
\"\"\"
"""

    def extraer(self, noticia: NoticiaFuente) -> dict:
        modelo = self._obtener_modelo()
        prompt = self.construir_prompt(noticia)
        respuesta = modelo.generate_content(prompt)
        texto = (respuesta.text or "").strip()

        # Por si el modelo envuelve el JSON en un bloque markdown pese a la instrucción.
        if texto.startswith("```"):
            texto = texto.strip("`")
            if texto.startswith("json"):
                texto = texto[len("json"):]
            texto = texto.strip()

        try:
            datos = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"[{noticia.id_noticia}] Gemini no devolvió JSON válido: {exc}\n"
                f"Respuesta cruda: {texto}"
            ) from exc

        if not datos.get("fecha_publicacion") and noticia.fecha_publicacion:
            # El texto limpio rara vez trae la fecha (vive en <meta>/JSON-LD, no
            # en el cuerpo visible); si el pipeline ya la extrajo del HTML, se usa.
            datos["fecha_publicacion"] = noticia.fecha_publicacion

        for rel in datos.get("relaciones") or []:
            # El prompt pide "tipo" sin guiones bajos, pero no hay que confiar en
            # que el modelo lo respete siempre; se normaliza igual al guardar.
            tipo = rel.get("tipo")
            if isinstance(tipo, str):
                rel["tipo"] = " ".join(tipo.replace("_", " ").split())

        ruta = self.dir_json / f"{noticia.id_noticia}.json"
        ruta.write_text(
            json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return datos
