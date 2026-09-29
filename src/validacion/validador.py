"""Validación del JSON producido por el LLM.

El LLM no es la fuente de verdad: el código debe verificar el esquema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
    
    def __init__(self, ruta_metricas: str | Path = "data/json/metricas_validadcion.json") -> None:
        self.ruta_metricas = Path(ruta_metricas)
        self.ruta_metricas.parent.mkdir(parents=True, exist_ok=True)
        self.cargar_metricas()
    
    def cargar_metricas(self) -> None:
        if self.ruta_metricas.exists():
            self.metricas = json.loads(self.ruta_metricas.read_text(encoding="utf-8"))
        else:
            self.metricas = {
                "total_procesados": 0, "errores_parseo": 0, "errores_esquema": 0,
                "conteo_nulosOvacios": {campo: 0 for campo in self.CAMPOS_OBLIGATORIOS}    
            }
    
    def guardar_metricas(self) -> None:
        self.ruta_metricas.write_text(json.dumps(self.metricas, indent=2, ensure_ascii=False), encoding="utf-8")

    def registrar_error(self, tipo: str) -> None:
        self.metricas[tipo] += 1
        self.guardar_metricas()
    
    def validar(self, ruta: str | Path) -> dict:
        """Lee, parsea y valida un JSON. Lanza ValueError si el contrato no se cumple.

        TODO(alumno): registrar JSON inválidos para Data Understanding
        (conteos de campos nulos, tipos incorrectos, entidades inventadas).
        """
        archivo = Path(ruta)
        self.metricas["total_procesados"] += 1
        
        try:
            data = json.loads(archivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inválido en {archivo}: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"{archivo} no contiene un objeto JSON.")

        faltantes = [campo for campo in self.CAMPOS_OBLIGATORIOS if campo not in data]
        if faltantes:
            self.registrar_error("errores_esquema")
            raise ValueError(f"{archivo}: faltan campos {faltantes}")

        for campo in self.CAMPOS_LISTA:
            if not isinstance(data[campo], list):
                self.registrar_error("errores_esquema")
                raise ValueError(f"{archivo}: '{campo}' debe ser una lista")

        try:
            self.validar_-esquemas_anidados(data)
        except ValueError as exc:
            self.registrar_error("errores_esquema")
            raise ValueError(f"{archivo}: error de esquema interno -> {exc}")
        self.actualizar_conteo_nulos(data)
        selg.guardar_metricas()
    
        return data

    def validar_esquemas_anidados(self, data: dict[str, Any]) -> None:
        """Verifica que los elementos de las listas posean las claves correspondientes"""
        for i, persona in enumerate(data.get("personas", [])):
            if not isinstance(persona, dict) or "nombre" not in persona or "rol" not in persona:
                raise ValueError(f"El elemento {i} en 'personas' debe tener 'nombre' y 'rol'")
            
        for i, obj in enumerate(data.get("objetos", [])):
            claves_req = {"tipo", "nombre", "cantidad", "unidad"}
            if not isinstance(obj, dict) or not claves_req.issubset(obj.keys()):
                raise ValueError(f"El elemento {i} en 'objetos' debe tener {claves_req}.")

        for i, rel in enumerate(data.get("relaciones", [])):
            claves_req = {"origen", "tipo", "destino"}
            if not isinstance(rel, dict) or not claves_req.issubset(rel.keys()):
                raise ValueError(f"El elemento {i} en 'relaciones' debe tener {claves_req}.")
    
    def actualizar_conteo_nulos(self, data: dic[str, Any]) -> None:
        """Cuenta nulos explicitos, string vacios o listas sin elementos"""
        
        for campo in self.CAMPOS_OBLIGATORIOS:
            valor = data.get(campo)
            if valor is None or valor == "" or (isinstance(valor, list) and len(valor) == 0):
                self.metricas["conteo_nulosOvacios"][campo] += 1