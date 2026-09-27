"""Validación del JSON producido por el LLM.

El LLM no es la fuente de verdad: el código debe verificar el esquema.
"""

from __future__ import annotations

import json
from pathlib import Path


class ValidadorJSON:
    """Comprueba que cada archivo JSON cumpla el contrato de datos."""

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

    CAMPOS_LISTA = [
        "delitos",
        "personas",
        "organizaciones",
        "lugares",
        "objetos",
        "relaciones",
    ]

    def validar(self, ruta: str | Path) -> dict:
        """Lee, parsea y valida un JSON. Lanza ValueError si el contrato no se cumple.

        TODO(alumno): registrar JSON inválidos para Data Understanding
        (conteos de campos nulos, tipos incorrectos, entidades inventadas).
        """
        archivo = Path(ruta)
        try:
            data = json.loads(archivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inválido en {archivo}: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"{archivo} no contiene un objeto JSON.")

        faltantes = [campo for campo in self.CAMPOS_OBLIGATORIOS if campo not in data]
        if faltantes:
            raise ValueError(f"{archivo}: faltan campos {faltantes}")

        for campo in self.CAMPOS_LISTA:
            if not isinstance(data[campo], list):
                raise ValueError(f"{archivo}: '{campo}' debe ser una lista")

        return data
