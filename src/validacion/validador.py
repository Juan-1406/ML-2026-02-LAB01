"""Validación del JSON producido por el LLM.

El LLM no es la fuente de verdad: el código debe verificar el esquema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import DIR_JSON


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

    # Un origen/destino real es un nombre propio, no una oración explicativa;
    # más de esta cantidad de palabras casi siempre es texto de contexto que
    # el LLM confundió con una entidad (ver informe_relaciones.md).
    MAX_PALABRAS_ENTIDAD_RELACION = 6

    # Una noticia con más personas que esto suele indicar contaminación
    # (nombres de una sección de "noticias relacionadas" o publicidad que
    # se coló en el texto limpio), no un caso real con tantos involucrados.
    MAX_PERSONAS_ESPERADAS = 12

    def __init__(self, ruta_metricas: str | Path = DIR_JSON / "metricas_validacion.json") -> None:
        self.ruta_metricas = Path(ruta_metricas)
        self.ruta_metricas.parent.mkdir(parents=True, exist_ok=True)
        self.cargar_metricas()
    
    def cargar_metricas(self) -> None:
        if self.ruta_metricas.exists():
            self.metricas = json.loads(self.ruta_metricas.read_text(encoding="utf-8"))
        else:
            self.metricas = {}
        self.metricas.setdefault("total_procesados", 0)
        self.metricas.setdefault("errores_parseo", 0)
        self.metricas.setdefault("errores_esquema", 0)
        self.metricas.setdefault(
            "conteo_nulosOvacios", {campo: 0 for campo in self.CAMPOS_OBLIGATORIOS}
        )
        # Señales de calidad además de nulos: relaciones con una oración en vez
        # de una entidad, y noticias con listas de personas anormalmente largas.
        self.metricas.setdefault("relaciones_descartadas", 0)
        self.metricas.setdefault("noticias_con_personas_sospechosas", 0)

    def guardar_metricas(self) -> None:
        self.ruta_metricas.write_text(json.dumps(self.metricas, indent=2, ensure_ascii=False), encoding="utf-8")

    def registrar_error(self, tipo: str) -> None:
        self.metricas[tipo] += 1
        self.guardar_metricas()

    def validar(self, ruta: str | Path, registrar: bool = True) -> dict:
        """Lee, parsea y valida un JSON. Lanza ValueError si el contrato no se cumple.

        Con registrar=False valida sin tocar las métricas (revalidaciones).

        Además de comprobar el esquema, sanea `relaciones` (descarta las que
        traen una oración como origen/destino en vez de una entidad) y deja
        registro de noticias con listas de personas sospechosamente largas,
        para que Data Understanding pueda mostrar estos problemas de calidad.
        """
        archivo = Path(ruta)
        registrar_error = self.registrar_error if registrar else (lambda tipo: None)
        if registrar:
            self.metricas["total_procesados"] += 1
        
        try:
            data = json.loads(archivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            registrar_error("errores_parseo")
            raise ValueError(f"JSON inválido en {archivo}: {exc}") from exc

        if not isinstance(data, dict):
            registrar_error("errores_esquema")
            raise ValueError(f"{archivo} no contiene un objeto JSON.")

        faltantes = [campo for campo in self.CAMPOS_OBLIGATORIOS if campo not in data]
        if faltantes:
            registrar_error("errores_esquema")
            raise ValueError(f"{archivo}: faltan campos {faltantes}")

        for campo in self.CAMPOS_LISTA:
            if not isinstance(data[campo], list):
                registrar_error("errores_esquema")
                raise ValueError(f"{archivo}: '{campo}' debe ser una lista")

        try:
            self.validar_esquemas_anidados(data)
        except ValueError as exc:
            registrar_error("errores_esquema")
            raise ValueError(f"{archivo}: error de esquema interno -> {exc}") from exc

        descartadas = self.sanear_relaciones(data)
        sospechosa = self.es_sospechosa_por_personas(data)
        if registrar:
            self.actualizar_conteo_nulos(data)
            self.metricas["relaciones_descartadas"] += descartadas
            if sospechosa:
                self.metricas["noticias_con_personas_sospechosas"] += 1
            self.guardar_metricas()

        return data

    @classmethod
    def _parece_entidad(cls, texto: str) -> bool:
        """Un nombre propio es corto; una oración de contexto no lo es."""
        palabras = texto.split()
        return 0 < len(palabras) <= cls.MAX_PALABRAS_ENTIDAD_RELACION

    def sanear_relaciones(self, data: dict[str, Any]) -> int:
        """Descarta relaciones cuyo origen/destino/tipo es una oración, no una entidad.

        Modifica `data["relaciones"]` en el sitio y devuelve cuántas se descartaron.
        """
        buenas, descartadas = [], 0
        for rel in data.get("relaciones") or []:
            origen, tipo, destino = rel.get("origen"), rel.get("tipo"), rel.get("destino")
            if all(isinstance(v, str) and self._parece_entidad(v) for v in (origen, tipo, destino)):
                buenas.append(rel)
            else:
                descartadas += 1
        data["relaciones"] = buenas
        return descartadas

    def es_sospechosa_por_personas(self, data: dict[str, Any]) -> bool:
        """Muchas más personas que lo habitual suele ser contaminación del texto limpio."""
        return len(data.get("personas") or []) > self.MAX_PERSONAS_ESPERADAS

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
    
    def actualizar_conteo_nulos(self, data: dict[str, Any]) -> None:
        """Cuenta nulos explicitos, string vacios o listas sin elementos"""
        
        for campo in self.CAMPOS_OBLIGATORIOS:
            valor = data.get(campo)
            if valor is None or valor == "" or (isinstance(valor, list) and len(valor) == 0):
                self.metricas["conteo_nulosOvacios"][campo] += 1