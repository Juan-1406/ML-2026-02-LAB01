"""Modelo de conocimiento del laboratorio.

Las dataclasses reflejan el JSON esperado: noticia, personas, objetos y
relaciones. Extraer solo lo explícito en el texto; si falta un dato, usar
None o listas vacías.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NoticiaFuente:
    """Fila de data/urls.csv más metadatos de captura."""

    id_noticia: str
    fuente: str
    url: str
    categoria_busqueda: str = ""
    html: Optional[str] = None
    texto_limpio: Optional[str] = None
    fecha_publicacion: Optional[str] = None


@dataclass
class Persona:
    """Persona nombrada en la noticia, con el rol que el texto atribuye."""

    nombre: str
    rol: Optional[str] = None


@dataclass
class ObjetoIncautado:
    """Arma, sustancia, vehículo, dinero u otro elemento mencionado."""

    tipo: str
    nombre: str
    cantidad: Optional[float] = None
    unidad: Optional[str] = None


@dataclass
class Relacion:
    """Enlace explícito entre dos entidades (origen -- tipo --> destino)."""

    origen: str
    tipo: str
    destino: str


@dataclass
class NoticiaEstructurada:
    """Contrato JSON que debe producir el extractor LLM."""

    id_noticia: str
    titulo: Optional[str]
    fecha_publicacion: Optional[str]
    fuente: Optional[str]
    url: Optional[str]
    resumen: Optional[str]
    delitos: list[str] = field(default_factory=list)
    personas: list[Persona] = field(default_factory=list)
    organizaciones: list[str] = field(default_factory=list)
    lugares: list[str] = field(default_factory=list)
    objetos: list[ObjetoIncautado] = field(default_factory=list)
    relaciones: list[Relacion] = field(default_factory=list)

    def a_dict(self) -> dict:
        """Convierte el objeto al diccionario del esquema JSON."""
        return {
            "id_noticia": self.id_noticia,
            "titulo": self.titulo,
            "fecha_publicacion": self.fecha_publicacion,
            "fuente": self.fuente,
            "url": self.url,
            "resumen": self.resumen,
            "delitos": list(self.delitos),
            "personas": [
                {"nombre": p.nombre, "rol": p.rol} for p in self.personas
            ],
            "organizaciones": list(self.organizaciones),
            "lugares": list(self.lugares),
            "objetos": [
                {
                    "tipo": o.tipo,
                    "nombre": o.nombre,
                    "cantidad": o.cantidad,
                    "unidad": o.unidad,
                }
                for o in self.objetos
            ],
            "relaciones": [
                {"origen": r.origen, "tipo": r.tipo, "destino": r.destino}
                for r in self.relaciones
            ],
        }
