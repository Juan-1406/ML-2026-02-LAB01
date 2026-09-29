"""Limpieza de HTML a texto plano, según la guía del laboratorio."""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

# La fecha de publicación casi nunca está en el texto visible del artículo
# (los medios la ponen en <meta>/JSON-LD, que get_text() no captura); por eso
# se busca aparte, directo en el HTML crudo.
_META_FECHA = (
    "article:published_time",
    "og:article:published_time",
    "datePublished",
    "page_publish_time",
    "publish-date",
    "date",
)
_FECHA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?")


class LimpiadorHTML:
    """Quita ruido (menús, scripts, publicidad) y deja párrafo útiles."""

    ETIQUETAS_RUIDO = ("script", "style", "nav", "footer", "aside", "noscript", "iframe")
    LARGO_MINIMO_LINEA = 40

    def limpiar(self, html: str) -> str:
        """HTML crudo → texto listo para enviar a un LLM."""
        soup = BeautifulSoup(html, "lxml")
        for etiqueta in soup(list(self.ETIQUETAS_RUIDO)):
            etiqueta.decompose()

        texto = soup.get_text("\n")
        lineas = [linea.strip() for linea in texto.splitlines()]
        lineas = [linea for linea in lineas if len(linea) > self.LARGO_MINIMO_LINEA]
        return "\n".join(lineas)

    def extraer_fecha(self, html: str) -> str | None:
        """Busca la fecha de publicación en <meta>, <time> o JSON-LD del HTML crudo."""
        soup = BeautifulSoup(html, "lxml")

        for nombre in _META_FECHA:
            etiqueta = soup.find("meta", attrs={"property": nombre}) or soup.find(
                "meta", attrs={"name": nombre}
            )
            if etiqueta and etiqueta.get("content"):
                coincidencia = _FECHA_ISO.search(etiqueta["content"])
                if coincidencia:
                    return coincidencia.group(0)

        etiqueta_time = soup.find("time", attrs={"datetime": True})
        if etiqueta_time:
            coincidencia = _FECHA_ISO.search(etiqueta_time["datetime"])
            if coincidencia:
                return coincidencia.group(0)

        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            for bloque in data if isinstance(data, list) else [data]:
                if isinstance(bloque, dict) and bloque.get("datePublished"):
                    coincidencia = _FECHA_ISO.search(str(bloque["datePublished"]))
                    if coincidencia:
                        return coincidencia.group(0)
        return None
