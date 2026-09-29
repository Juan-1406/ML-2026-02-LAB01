"""Persistencia final: red de notas Markdown para Obsidian.

No se usa SQLite, MongoDB ni Neo4j. Cada noticia y cada entidad tiene su
propia nota, enlazada con [[wiki-links]]. Las entidades se unifican entre
noticias por su nombre normalizado (sin tildes ni mayúsculas), de modo que
"Región Metropolitana" y "región Metropolitana" son la misma nota. Las
variantes que no se resuelven así (siglas, plurales, sinónimos) se unifican
con la tabla de data/equivalencias.csv (ver `Equivalencias`). Los extremos de
una relación se enlazan solo si coinciden con una entidad extraída; si no,
quedan como texto plano (no se inventan notas).
"""

from __future__ import annotations

import csv
import json
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from src.config import DIR_VAULT, RUTA_EQUIVALENCIAS
from src.conocimiento.utilidades import enlace_obsidian, slugify

CARPETAS = {
    "delitos": "Delitos",
    "personas": "Personas",
    "organizaciones": "Organizaciones",
    "lugares": "Lugares",
    "objetos": "Objetos",
}
ETIQUETAS = {
    "delitos": "delito",
    "personas": "persona",
    "organizaciones": "organizacion",
    "lugares": "lugar",
    "objetos": "objeto",
}
NOMBRES_VISIBLES = {
    "delitos": "Delito",
    "personas": "Persona",
    "organizaciones": "Organización",
    "lugares": "Lugar",
    "objetos": "Objeto",
}
ROTULOS_ASOCIADAS = {
    "delitos": "Delitos asociados",
    "personas": "Personas relacionadas",
    "organizaciones": "Organizaciones relacionadas",
    "lugares": "Lugares",
    "objetos": "Objetos",
}
CARPETA_NOTICIAS = "Noticias"
CARPETA_RELACIONES = "Relaciones"
# Si un mismo texto es entidad de varias categorías, gana la primera.
PRIORIDAD = ("personas", "organizaciones", "lugares", "delitos", "objetos")
MARCA = "generado: true"


def _texto(valor) -> str:
    return str(valor).strip() if valor is not None else ""


def _archivo(nombre: str) -> str:
    """Nombre de archivo legible (espacios y tildes) sin los caracteres que Obsidian no admite."""
    limpio = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", nombre)
    return re.sub(r"\s+", " ", limpio).strip(" .") or "sin nombre"


def _clave(nombre: str) -> str:
    return slugify(nombre).lower()


def _alias(texto: str) -> str:
    """Quita los caracteres que rompen [[carpeta/archivo|alias]]."""
    return re.sub(r"\s+", " ", re.sub(r"[\[\]|]", " ", texto)).strip()


def _celda(texto: str) -> str:
    return texto.replace("|", "/").replace("\n", " ")


def _yaml(valor) -> str:
    """Escalar YAML válido (una cadena JSON entre comillas también lo es)."""
    if valor is None or _texto(valor) == "":
        return "null"
    return json.dumps(_texto(valor), ensure_ascii=False)


_FECHA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?$")


def _yaml_fecha(valor) -> str:
    """Fecha ISO sin comillas para que Obsidian la trate como propiedad de fecha."""
    texto = _texto(valor)
    return texto if _FECHA_ISO.match(texto) else _yaml(valor)


def _es_generado(ruta: Path) -> bool:
    return MARCA in ruta.read_text(encoding="utf-8", errors="ignore")[:300]


CATEGORIAS_EQUIVALENCIA = (*CARPETAS, "relaciones")


class Equivalencias:
    """Tabla variante → nombre canónico, por categoría.

    Se lee de un CSV con columnas `categoria,canonico,variante[,nota]` (las
    líneas que empiezan con # son comentarios). La categoría es una de
    delitos, personas, organizaciones, lugares, objetos o relaciones (tipos de
    relación). Se compara sin tildes ni mayúsculas. Unificar dos entidades
    distintas crea conexiones falsas entre noticias, por eso solo se aplican
    las equivalencias declaradas; nada se fusiona por parecido.
    """

    def __init__(self) -> None:
        self._tabla: dict[str, dict[str, str]] = {cat: {} for cat in CATEGORIAS_EQUIVALENCIA}

    @classmethod
    def desde_csv(cls, ruta: Path) -> "Equivalencias":
        eq = cls()
        if not Path(ruta).is_file():
            return eq
        lineas = [
            ln
            for ln in Path(ruta).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        for fila in csv.DictReader(lineas):
            eq.agregar(_texto(fila.get("categoria")).lower(), fila.get("variante"), fila.get("canonico"))
        eq.verificar()
        return eq

    def agregar(self, categoria: str, variante, canonico) -> None:
        if categoria not in self._tabla:
            raise ValueError(
                f"Equivalencia con categoría desconocida {categoria!r}; "
                f"use una de {list(CATEGORIAS_EQUIVALENCIA)}"
            )
        variante, canonico = _texto(variante), _texto(canonico)
        if not variante or not canonico:
            raise ValueError(f"Equivalencia incompleta en {categoria}: {variante!r} -> {canonico!r}")
        clave = _clave(variante)
        if clave == _clave(canonico):
            return
        previo = self._tabla[categoria].get(clave)
        if previo is not None and _clave(previo) != _clave(canonico):
            raise ValueError(
                f"{categoria}: {variante!r} apunta a dos nombres distintos ({previo!r} y {canonico!r})"
            )
        self._tabla[categoria][clave] = canonico

    def verificar(self) -> None:
        """Un nombre canónico no puede ser a su vez variante de otro."""
        for categoria, tabla in self._tabla.items():
            for canonico in set(tabla.values()):
                if _clave(canonico) in tabla:
                    raise ValueError(
                        f"{categoria}: {canonico!r} es nombre canónico y también variante de "
                        f"{tabla[_clave(canonico)]!r}; apunte ambas variantes al nombre final"
                    )

    def canonico(self, categoria: str, nombre: str) -> str:
        return self._tabla[categoria].get(_clave(nombre), nombre)

    def canonico_texto(self, texto: str) -> str:
        """Para extremos de relación, cuya categoría no se conoce."""
        clave = _clave(texto)
        for categoria in PRIORIDAD:
            if clave in self._tabla[categoria]:
                return self._tabla[categoria][clave]
        return texto


def _entidades_de(data: dict, eq: Equivalencias) -> dict[str, list[dict]]:
    """Entidades de una noticia por categoría, unificadas y con su detalle."""
    salida: dict[str, dict[str, dict]] = {cat: {} for cat in CARPETAS}

    def agregar(cat: str, nombre, detalle: str | None = None) -> None:
        original = _texto(nombre)
        if not original:
            return
        canonico = eq.canonico(cat, original)
        clave = _clave(canonico)
        ent = salida[cat].setdefault(
            clave, {"nombre": canonico, "clave": clave, "detalles": [], "originales": set()}
        )
        ent["originales"].add(original)
        if detalle and detalle not in ent["detalles"]:
            ent["detalles"].append(detalle)

    for cat in ("delitos", "organizaciones", "lugares"):
        for valor in data.get(cat) or []:
            agregar(cat, valor)
    for persona in data.get("personas") or []:
        if isinstance(persona, dict):
            rol = _texto(persona.get("rol"))
            agregar("personas", persona.get("nombre"), f"rol: {rol}" if rol else None)
    for obj in data.get("objetos") or []:
        if isinstance(obj, dict):
            tipo = _texto(obj.get("tipo"))
            cantidad = _texto(obj.get("cantidad"))
            unidad = _texto(obj.get("unidad"))
            partes = [
                p
                for p in (
                    f"tipo: {tipo}" if tipo else "",
                    f"cantidad: {cantidad} {unidad}".strip() if cantidad else "",
                )
                if p
            ]
            agregar("objetos", obj.get("nombre"), " · ".join(partes) or None)
    return {cat: list(ents.values()) for cat, ents in salida.items()}


class _Rel(NamedTuple):
    origen: str
    tipo: str
    destino: str
    tipo_original: str


def _relaciones_de(data: dict, eq: Equivalencias) -> list[_Rel]:
    """Relaciones completas y unificadas, sin duplicados ni autorrelaciones."""
    vistas: set[tuple[str, str, str]] = set()
    salida = []
    for rel in data.get("relaciones") or []:
        if not isinstance(rel, dict):
            continue
        origen, tipo, destino = (_texto(rel.get(k)) for k in ("origen", "tipo", "destino"))
        if not (origen and tipo and destino):
            continue
        # Algunos JSON ya extraídos traen el tipo con guión bajo ("es_accionista_en")
        # en vez de frase natural; se normaliza aquí para que la nota y la etiqueta
        # del grafo se vean consistentes sin depender de volver a llamar al LLM.
        tipo = " ".join(tipo.replace("_", " ").split())
        origen, destino = eq.canonico_texto(origen), eq.canonico_texto(destino)
        canonico = eq.canonico("relaciones", tipo)
        llave = (_clave(origen), _clave(canonico), _clave(destino))
        if _clave(origen) == _clave(destino) or llave in vistas:
            continue
        vistas.add(llave)
        salida.append(_Rel(origen, canonico, destino, tipo))
    return salida


def _locales(ents: dict[str, list[dict]]) -> dict[str, str]:
    """clave → categoría para las entidades de una sola noticia."""
    locales: dict[str, str] = {}
    for cat in PRIORIDAD:
        for ent in ents[cat]:
            locales.setdefault(ent["clave"], cat)
    return locales


@dataclass
class _Entidad:
    """Acumula las variantes de escritura y las noticias de una entidad."""

    variantes: Counter = field(default_factory=Counter)
    originales: set[str] = field(default_factory=set)
    noticias: dict[str, list[str]] = field(default_factory=dict)

    @property
    def nombre(self) -> str:
        return self.variantes.most_common(1)[0][0]

    @property
    def slug(self) -> str:
        return _archivo(self.nombre)

    @property
    def otras_variantes(self) -> list[str]:
        """Escrituras distintas al nombre de la nota (incluye las unificadas)."""
        return sorted({*self.variantes, *self.originales} - {self.nombre}, key=str.lower)

    @property
    def unificadas(self) -> list[str]:
        """Variantes que solo se unificaron por la tabla de equivalencias."""
        return [v for v in self.otras_variantes if _clave(v) != _clave(self.nombre)]


@dataclass(frozen=True)
class _Ref:
    """Extremo de una relación: enlazable si se resolvió a una categoría."""

    texto: str
    categoria: str | None

    @property
    def llave(self) -> tuple[str, str]:
        return (self.categoria or "", _clave(self.texto))


@dataclass(frozen=True)
class _Triple:
    noticia: str
    origen: _Ref
    tipo: str
    destino: _Ref


class EscritorObsidian(ABC):
    """Contrato para generar la bóveda a partir de JSON validado."""

    @abstractmethod
    def escribir_noticia(self, data: dict) -> Path:
        """Crea obsidian_vault/Noticias/{id_noticia}.md con frontmatter y enlaces."""

    @abstractmethod
    def escribir_entidades(self, noticias: list[dict]) -> None:
        """Agrega notas de delitos, personas, organizaciones, lugares y objetos."""

    @abstractmethod
    def escribir_indice(self, noticias: list[dict]) -> Path:
        """Crea obsidian_vault/00_Indice.md."""

    @abstractmethod
    def escribir_vault(self, noticias: list[dict]) -> None:
        """Orquesta noticia + entidades + índice."""


class EscritorVaultObsidian(EscritorObsidian):
    """Genera la bóveda:

        obsidian_vault/
        ├── 00_Indice.md
        ├── Noticias/          una nota por noticia (con diagrama mermaid)
        ├── Delitos/
        ├── Personas/
        ├── Organizaciones/
        ├── Lugares/
        ├── Objetos/
        └── Relaciones/        una nota por tipo de relación

    Toda nota generada lleva `generado: true` en el frontmatter; al regenerar
    solo se borran las notas con esa marca (las notas propias no se tocan).
    """

    def __init__(
        self,
        vault: Path = DIR_VAULT,
        equivalencias: Equivalencias | Path | None = None,
    ) -> None:
        self.vault = vault
        if isinstance(equivalencias, Equivalencias):
            self._eq = equivalencias
        else:
            self._eq = Equivalencias.desde_csv(equivalencias or RUTA_EQUIVALENCIAS)
        self.variantes_unificadas = 0
        self._indexado: list[dict] | None = None
        self._reiniciar_indice()

    def _reiniciar_indice(self) -> None:
        self._entidades: dict[str, dict[str, _Entidad]] = {cat: {} for cat in CARPETAS}
        self._tipos: dict[str, _Entidad] = {}
        self._titulos: dict[str, str] = {}
        self._triples: list[_Triple] = []
        self._global: dict[str, str] = {}
        self._coocurrencia: dict[tuple[str, str], dict[str, Counter]] = {}

    # ---------- índice en memoria ----------

    def _indexar(self, noticias: list[dict]) -> None:
        if self._indexado is noticias:
            return
        self._reiniciar_indice()
        presentes: dict[str, set[str]] = {}
        procesadas = []
        for data in noticias:
            id_ = _texto(data.get("id_noticia")) or "sin_id"
            self._titulos[id_] = _texto(data.get("titulo")) or id_
            ents = _entidades_de(data, self._eq)
            for cat, lista in ents.items():
                for e in lista:
                    entidad = self._entidades[cat].setdefault(e["clave"], _Entidad())
                    entidad.variantes[e["nombre"]] += 1
                    entidad.originales.update(e["originales"])
                    detalles = entidad.noticias.setdefault(id_, [])
                    detalles.extend(d for d in e["detalles"] if d not in detalles)
                    presentes.setdefault(e["clave"], set()).add(cat)
            items = [(cat, e["clave"]) for cat, lista in ents.items() for e in lista]
            for cat_a, clave_a in items:
                asociadas = self._coocurrencia.setdefault((cat_a, clave_a), {})
                for cat_b, clave_b in items:
                    if cat_b != cat_a:
                        asociadas.setdefault(cat_b, Counter())[clave_b] += 1
            procesadas.append((id_, ents, data))

        # Un texto solo se enlaza fuera de su noticia si pertenece a una única categoría.
        self._global = {c: next(iter(cats)) for c, cats in presentes.items() if len(cats) == 1}

        for id_, ents, data in procesadas:
            locales = _locales(ents)
            for rel in _relaciones_de(data, self._eq):
                clave_tipo = _clave(rel.tipo)
                entidad = self._tipos.setdefault(clave_tipo, _Entidad())
                entidad.variantes[rel.tipo] += 1
                entidad.originales.add(rel.tipo_original)
                entidad.noticias.setdefault(id_, [])
                self._triples.append(
                    _Triple(
                        id_,
                        self._resolver(rel.origen, locales),
                        clave_tipo,
                        self._resolver(rel.destino, locales),
                    )
                )
        todas = [*(e for ents in self._entidades.values() for e in ents.values()), *self._tipos.values()]
        self.variantes_unificadas = sum(len(e.unificadas) for e in todas)
        self._indexado = noticias

    def _resolver(self, texto: str, locales: dict[str, str]) -> _Ref:
        clave = _clave(texto)
        return _Ref(texto, locales.get(clave) or self._global.get(clave))

    # ---------- enlaces ----------

    def _enlace_entidad(self, categoria: str, nombre: str) -> str:
        ent = self._entidades[categoria].get(_clave(nombre))
        visible = ent.nombre if ent else nombre
        slug = ent.slug if ent else _archivo(nombre)
        return enlace_obsidian(f"{CARPETAS[categoria]}/{slug}|{_alias(visible)}")

    def _enlace_ref(self, ref: _Ref) -> str:
        return self._enlace_entidad(ref.categoria, ref.texto) if ref.categoria else ref.texto

    def _enlace_tipo(self, tipo: str) -> str:
        ent = self._tipos.get(_clave(tipo))
        visible = ent.nombre if ent else tipo
        slug = ent.slug if ent else _archivo(tipo)
        return enlace_obsidian(f"{CARPETA_RELACIONES}/{slug}|{_alias(visible)}")

    @staticmethod
    def _enlace_noticia(id_: str) -> str:
        return enlace_obsidian(f"{CARPETA_NOTICIAS}/{slugify(id_)}|{_alias(id_)}")

    def _enlaces_noticias(self, ids: list[str]) -> str:
        return ", ".join(self._enlace_noticia(i) for i in ids)

    # ---------- escritura ----------

    def _escribir(self, carpeta: str, nombre: str, lineas: list[str]) -> Path:
        ruta = self.vault / carpeta / f"{nombre}.md"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("\n".join(lineas).rstrip("\n") + "\n", encoding="utf-8")
        return ruta

    def _limpiar(self) -> None:
        carpetas = [*CARPETAS.values(), CARPETA_NOTICIAS, CARPETA_RELACIONES]
        for carpeta in carpetas:
            for ruta in (self.vault / carpeta).glob("*.md"):
                if _es_generado(ruta):
                    ruta.unlink()

    @staticmethod
    def _mermaid(relaciones: list[_Rel]) -> list[str]:
        ids: dict[str, str] = {}

        def nodo(texto: str) -> str:
            llave = _clave(texto)
            if llave not in ids:
                ids[llave] = f"n{len(ids)}"
                lineas_nodos.append(f'    {ids[llave]}["{texto.replace(chr(34), chr(39))}"]')
            return ids[llave]

        lineas_nodos: list[str] = []
        aristas = []
        for rel in relaciones:
            etiqueta = re.sub(r"[|\n]", " ", rel.tipo)
            aristas.append(f"    {nodo(rel.origen)} -->|{etiqueta}| {nodo(rel.destino)}")
        return ["```mermaid", "graph LR", *lineas_nodos, *aristas, "```"]

    def escribir_noticia(self, data: dict) -> Path:
        id_ = _texto(data.get("id_noticia")) or "sin_id"
        titulo = _texto(data.get("titulo"))
        ents = _entidades_de(data, self._eq)
        relaciones = _relaciones_de(data, self._eq)
        locales = _locales(ents)
        etiquetas = ["noticia", *(f"delito/{e['clave']}" for e in ents["delitos"])]

        lineas = [
            "---",
            MARCA,
            f"id: {_yaml(id_)}",
            f"titulo: {_yaml(titulo)}",
            f"fecha_publicacion: {_yaml_fecha(data.get('fecha_publicacion'))}",
            f"fuente: {_yaml(data.get('fuente'))}",
            f"url: {_yaml(data.get('url'))}",
            f"tags: [{', '.join(etiquetas)}]",
            "---",
            "",
            f"# {titulo or id_}",
            "",
        ]
        fuente = _texto(data.get("fuente")) or "no indicada"
        fecha = _texto(data.get("fecha_publicacion")) or "no indicada"
        url = _texto(data.get("url"))
        lineas.append(
            f"**Fuente:** {fuente} · **Fecha:** {fecha}"
            + (f" · [Noticia original]({url})" if url else "")
        )
        lineas.append("")
        resumen = _texto(data.get("resumen"))
        if resumen:
            lineas += ["## Resumen", "", resumen.replace("\n", " "), ""]

        def seccion(titulo_seccion: str, items: list[str]) -> None:
            if items:
                lineas.extend([f"## {titulo_seccion}", "", *items, ""])

        def con_detalle(cat: str, e: dict, sep: str) -> str:
            enlace = self._enlace_entidad(cat, e["nombre"])
            return f"- {enlace}{sep}{' · '.join(e['detalles'])}" if e["detalles"] else f"- {enlace}"

        seccion("Delitos", [con_detalle("delitos", e, "") for e in ents["delitos"]])
        seccion("Personas", [con_detalle("personas", e, " — ") for e in ents["personas"]])
        seccion("Organizaciones", [con_detalle("organizaciones", e, "") for e in ents["organizaciones"]])
        seccion("Lugares", [con_detalle("lugares", e, "") for e in ents["lugares"]])
        seccion("Objetos", [con_detalle("objetos", e, " — ") for e in ents["objetos"]])
        seccion(
            "Relaciones",
            [
                f"- {self._enlace_ref(self._resolver(r.origen, locales))} -- "
                f"{self._enlace_tipo(r.tipo)} --> {self._enlace_ref(self._resolver(r.destino, locales))}"
                for r in relaciones
            ],
        )
        if relaciones:
            lineas += ["## Grafo de relaciones", "", *self._mermaid(relaciones), ""]
        return self._escribir(CARPETA_NOTICIAS, slugify(id_), lineas)

    def _agrupar(self, triples: list[_Triple], lado_otro: str) -> list[tuple[str, _Ref, list[str]]]:
        grupos: dict[tuple, tuple[str, _Ref, list[str]]] = {}
        for t in triples:
            otro = t.destino if lado_otro == "destino" else t.origen
            _, _, ids = grupos.setdefault((t.tipo, otro.llave), (t.tipo, otro, []))
            if t.noticia not in ids:
                ids.append(t.noticia)
        return list(grupos.values())

    def _escribir_entidad(self, categoria: str, clave: str, ent: _Entidad) -> Path:
        lineas = ["---", MARCA, f"tipo: {ETIQUETAS[categoria]}", f"nombre: {_yaml(ent.nombre)}"]
        if ent.otras_variantes:
            lineas.append(f"aliases: [{', '.join(_yaml(v) for v in ent.otras_variantes)}]")
        lineas += [
            f"noticias: {len(ent.noticias)}",
            f"tags: [{ETIQUETAS[categoria]}]",
            "---",
            "",
            f"# {ent.nombre}",
            "",
            f"**Tipo:** {NOMBRES_VISIBLES[categoria]} · aparece en {len(ent.noticias)} noticia(s). "
            "Entre paréntesis: noticias compartidas.",
            "",
        ]
        if ent.unificadas:
            lineas += [f"**Variantes unificadas:** {', '.join(ent.unificadas)}", ""]
        lineas += ["## Noticias relacionadas", ""]
        for id_, detalles in ent.noticias.items():
            extra = f" · {' · '.join(detalles)}" if detalles else ""
            lineas.append(f"- {self._enlace_noticia(id_)} — {self._titulos[id_]}{extra}")
        lineas.append("")

        if categoria == "personas":
            roles: Counter = Counter()
            escrituras: dict[str, str] = {}
            for detalles in ent.noticias.values():
                for d in detalles:
                    if d.startswith("rol: "):
                        rol = d[len("rol: "):]
                        roles[rol.lower()] += 1
                        escrituras.setdefault(rol.lower(), rol)
            if roles:
                lineas += ["## Roles observados", ""]
                for clave_rol, n in sorted(roles.items(), key=lambda kv: (-kv[1], kv[0])):
                    lineas.append(f"- {escrituras[clave_rol]} ({n})")
                lineas.append("")

        asociadas = self._coocurrencia.get((categoria, clave), {})
        for otra in ROTULOS_ASOCIADAS:
            contador = asociadas.get(otra)
            if not contador:
                continue
            lineas += [f"## {ROTULOS_ASOCIADAS[otra]}", ""]
            orden = sorted(
                contador.items(),
                key=lambda kv: (-kv[1], self._entidades[otra][kv[0]].nombre.lower()),
            )
            for clave_otra, n in orden:
                nombre = self._entidades[otra][clave_otra].nombre
                lineas.append(f"- {self._enlace_entidad(otra, nombre)} ({n})")
            lineas.append("")

        como_origen = [t for t in self._triples if t.origen.llave == (categoria, clave)]
        como_destino = [t for t in self._triples if t.destino.llave == (categoria, clave)]
        if como_origen:
            lineas += ["## Relaciones como origen", ""]
            for tipo, otro, ids in self._agrupar(como_origen, "destino"):
                lineas.append(
                    f"- **{self._enlace_tipo(tipo)}** → {self._enlace_ref(otro)} · {self._enlaces_noticias(ids)}"
                )
            lineas.append("")
        if como_destino:
            lineas += ["## Relaciones como destino", ""]
            for tipo, otro, ids in self._agrupar(como_destino, "origen"):
                lineas.append(
                    f"- {self._enlace_ref(otro)} → **{self._enlace_tipo(tipo)}** · {self._enlaces_noticias(ids)}"
                )
            lineas.append("")
        return self._escribir(CARPETAS[categoria], ent.slug, lineas)

    def _escribir_tipo_relacion(self, ent: _Entidad) -> Path:
        triples = [t for t in self._triples if _clave(ent.nombre) == t.tipo]
        grupos: dict[tuple, tuple[_Ref, _Ref, list[str]]] = {}
        for t in triples:
            _, _, ids = grupos.setdefault((t.origen.llave, t.destino.llave), (t.origen, t.destino, []))
            if t.noticia not in ids:
                ids.append(t.noticia)
        lineas = ["---", MARCA, "tipo: relacion", f"nombre: {_yaml(ent.nombre)}"]
        if ent.otras_variantes:
            lineas.append(f"aliases: [{', '.join(_yaml(v) for v in ent.otras_variantes)}]")
        lineas += [
            f"ocurrencias: {len(triples)}",
            "tags: [relacion]",
            "---",
            "",
            f"# {ent.nombre}",
            "",
        ]
        if ent.unificadas:
            lineas += [f"**Variantes unificadas:** {', '.join(ent.unificadas)}", ""]
        lineas += [f"## Ocurrencias ({len(triples)})", ""]
        for origen, destino, ids in grupos.values():
            lineas.append(
                f"- {self._enlace_ref(origen)} → {self._enlace_ref(destino)} · {self._enlaces_noticias(ids)}"
            )
        return self._escribir(CARPETA_RELACIONES, ent.slug, lineas)

    def escribir_entidades(self, noticias: list[dict]) -> None:
        self._indexar(noticias)
        for categoria, entidades in self._entidades.items():
            for clave, ent in entidades.items():
                self._escribir_entidad(categoria, clave, ent)
        for ent in self._tipos.values():
            self._escribir_tipo_relacion(ent)

    def escribir_indice(self, noticias: list[dict]) -> Path:
        self._indexar(noticias)
        totales = ", ".join(
            f"{CARPETAS[cat]}: {len(ents)}" for cat, ents in self._entidades.items()
        )
        lineas = [
            "---",
            MARCA,
            "tags: [indice]",
            "---",
            "",
            "# Índice del vault",
            "",
            f"Noticias: {len(noticias)} · {totales} · Tipos de relación: {len(self._tipos)}",
            "",
            "Las entidades que aparecen en varias noticias son las que conectan el grafo; "
            "en cada sección van primero las más frecuentes.",
            "",
            "## Noticias",
            "",
            "| Noticia | Fecha | Fuente | Título |",
            "| --- | --- | --- | --- |",
        ]
        for data in noticias:
            id_ = _texto(data.get("id_noticia")) or "sin_id"
            lineas.append(
                f"| {self._enlace_noticia(id_).replace('|', chr(92) + '|')} | {_celda(_texto(data.get('fecha_publicacion')) or '-')} "
                f"| {_celda(_texto(data.get('fuente')) or '-')} | {_celda(self._titulos[id_])} |"
            )
        lineas.append("")
        for categoria, entidades in self._entidades.items():
            lineas += [f"## {CARPETAS[categoria]}", ""]
            orden = sorted(entidades.items(), key=lambda kv: (-len(kv[1].noticias), kv[1].nombre.lower()))
            for _, ent in orden:
                lineas.append(
                    f"- {self._enlace_entidad(categoria, ent.nombre)} ({len(ent.noticias)})"
                )
            lineas.append("")
        lineas += [f"## {CARPETA_RELACIONES}", ""]
        for clave, ent in sorted(self._tipos.items(), key=lambda kv: (-len(kv[1].noticias), kv[0])):
            lineas.append(f"- {self._enlace_tipo(ent.nombre)} ({len(ent.noticias)})")
        return self._escribir("", "00_Indice", lineas)

    def escribir_vault(self, noticias: list[dict]) -> None:
        self._limpiar()
        self._indexar(noticias)
        for data in noticias:
            self.escribir_noticia(data)
        self.escribir_entidades(noticias)
        self.escribir_indice(noticias)
