"""Data Understanding sobre el corpus estructurado.

Las visualizaciones no son decoración; revelan cobertura, sesgos y
problemas de calidad (nulos, JSON inválidos, nombres inconsistentes).
"""

from __future__ import annotations
from src.validacion.validador import ValidadorJSON
from src.config import DATA_DIR, DIR_JSON
import matplotlib.pyplot as plt

from collections import Counter
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")


DIR_ANALISIS = DATA_DIR / "analisis"
CAMPOS_LISTA = ["delitos", "personas", "organizaciones",
                "lugares", "objetos", "relaciones"]
CAMPOS_OBLIGATORIOS = ["fecha_publicacion",
                       "fuente", "url", "resumen", *CAMPOS_LISTA]


class ExploradorDatos:
    """Estadísticas y gráficos mínimos del laboratorio."""

    def __init__(self, validador: ValidadorJSON | None = None, dir_salida: Path = DIR_ANALISIS) -> None:
        self.validador = validador or ValidadorJSON()
        self.dir_salida = dir_salida
        self.dir_salida.mkdir(parents=True, exist_ok=True)
        self._noticias: list[dict] | None = None

    def _cargar_noticias(self) -> list[dict]:
        """JSON válidos en data/json/; los inválidos se omiten (ya se cuentan en metricas)."""
        if self._noticias is not None:
            return self._noticias
        noticias = []
        for ruta in sorted(DIR_JSON.glob("N[0-9]*.json")):
            try:
                noticias.append(self.validador.validar(ruta, registrar=False))
            except ValueError as exc:
                print(f"  Omitido {ruta.name}: {exc}")
        self._noticias = noticias
        return noticias

    def _guardar(self, fig, nombre: str) -> Path:
        ruta = self.dir_salida / nombre
        fig.tight_layout()
        fig.savefig(ruta, dpi=120)
        plt.close(fig)
        return ruta

    def noticias_por_fuente(self) -> None:
        noticias = self._cargar_noticias()
        conteo = pd.Series(
            [n.get("fuente") or "sin fuente" for n in noticias]).value_counts()
        fig, ax = plt.subplots(figsize=(8, 5))
        conteo.plot(kind="bar", ax=ax, color="steelblue")
        ax.set_title("Noticias por fuente")
        ax.set_xlabel("Fuente")
        ax.set_ylabel("Cantidad de noticias")
        ruta = self._guardar(fig, "noticias_por_fuente.png")
        print(f"  Guardado: {ruta}")
        print(conteo.to_string())

    def delitos_frecuentes(self, top: int = 15) -> None:
        noticias = self._cargar_noticias()
        delitos = [d for n in noticias for d in (n.get("delitos") or [])]
        conteo = pd.Series(delitos).value_counts().head(top)
        fig, ax = plt.subplots(figsize=(8, 5))
        conteo.sort_values().plot(kind="barh", ax=ax, color="indianred")
        ax.set_title(f"Top {top} delitos más frecuentes")
        ax.set_xlabel("Menciones")
        ruta = self._guardar(fig, "delitos_frecuentes.png")
        print(f"  Guardado: {ruta}")
        print(conteo.to_string())

    def lugares_frecuentes(self, top: int = 15) -> None:
        noticias = self._cargar_noticias()
        lugares = [l for n in noticias for l in (n.get("lugares") or [])]
        conteo = pd.Series(lugares).value_counts().head(top)
        fig, ax = plt.subplots(figsize=(8, 5))
        conteo.sort_values().plot(kind="barh", ax=ax, color="seagreen")
        ax.set_title(f"Top {top} lugares más mencionados")
        ax.set_xlabel("Menciones")
        ruta = self._guardar(fig, "lugares_frecuentes.png")
        print(f"  Guardado: {ruta}")
        print(conteo.to_string())

    def campos_faltantes(self) -> None:
        noticias = self._cargar_noticias()
        total = len(noticias) or 1
        vacios = Counter()
        for n in noticias:
            for campo in CAMPOS_OBLIGATORIOS:
                valor = n.get(campo)
                if not valor:
                    vacios[campo] += 1
        porcentajes = pd.Series(
            {campo: 100 * vacios.get(campo, 0) /
             total for campo in CAMPOS_OBLIGATORIOS}
        ).sort_values(ascending=False)
        fig, ax = plt.subplots(figsize=(8, 5))
        porcentajes.plot(kind="bar", ax=ax, color="darkorange")
        ax.set_title("Campos vacíos/nulos por noticia (%)")
        ax.set_ylabel("% de noticias con el campo vacío")
        ruta = self._guardar(fig, "campos_faltantes.png")
        print(f"  Guardado: {ruta}")
        print(porcentajes.to_string())

    def evolucion_temporal(self) -> None:
        noticias = self._cargar_noticias()
        fechas = pd.to_datetime(
            [n.get("fecha_publicacion") for n in noticias], errors="coerce"
        )
        con_fecha = fechas.notna().sum()
        print(
            f"  Noticias con fecha_publicacion válida: {con_fecha}/{len(noticias)} "
            f"({100 * con_fecha / (len(noticias) or 1):.1f}%)"
        )
        serie = pd.Series(1, index=fechas).dropna()
        if serie.empty:
            print("  Sin fechas válidas para graficar evolución temporal.")
            return
        por_mes = serie.resample("MS").count()
        fig, ax = plt.subplots(figsize=(8, 5))
        por_mes.plot(kind="line", marker="o", ax=ax, color="purple")
        ax.set_title("Noticias por mes")
        ax.set_xlabel("Mes")
        ax.set_ylabel("Cantidad de noticias")
        ruta = self._guardar(fig, "evolucion_temporal.png")
        print(f"  Guardado: {ruta}")
        print(por_mes.to_string())

    def tipos_relacion_frecuentes(self, top: int = 15) -> None:
        """Cuenta tipos de relación (normalizados) y qué tan repartidos están.

        Antes de contar, descarta las relaciones donde origen/tipo/destino
        es una oración en vez de una entidad (mismo criterio que
        ValidadorJSON.sanear_relaciones) para no mezclar ruido de extracción
        con tipos de relación reales.
        """
        noticias = self._cargar_noticias()
        tipos = Counter()
        descartadas = 0
        for n in noticias:
            for rel in n.get("relaciones") or []:
                valores = (rel.get("origen"), rel.get("tipo"), rel.get("destino"))
                if not all(isinstance(v, str) and self.validador._parece_entidad(v) for v in valores):
                    descartadas += 1
                    continue
                tipos[" ".join(rel["tipo"].replace("_", " ").lower().split())] += 1

        if not tipos:
            print("  Sin relaciones utilizables para graficar.")
            return
        unicos = sum(1 for c in tipos.values() if c == 1)
        print(
            f"  Tipos de relación distintos: {len(tipos)} ({unicos} aparecen una sola vez) · "
            f"{descartadas} relaciones descartadas por no ser una entidad real"
        )
        conteo = pd.Series(tipos).sort_values(ascending=False).head(top)
        fig, ax = plt.subplots(figsize=(8, 5))
        conteo.sort_values().plot(kind="barh", ax=ax, color="teal")
        ax.set_title(f"Top {top} tipos de relación más frecuentes")
        ax.set_xlabel("Ocurrencias")
        ruta = self._guardar(fig, "tipos_relacion_frecuentes.png")
        print(f"  Guardado: {ruta}")
        print(conteo.to_string())

    def conectividad_entidades(self) -> None:
        """Qué porcentaje de cada tipo de entidad aparece en una sola noticia.

        Un vault pensado para mostrar una red debería tener bastantes nodos
        compartidos entre noticias; si casi todo aparece una sola vez, el
        grafo es en realidad una colección de casos sueltos.
        """
        noticias = self._cargar_noticias()
        extractores = {
            "delitos": lambda n: n.get("delitos") or [],
            "personas": lambda n: [p.get("nombre") for p in (n.get("personas") or []) if isinstance(p, dict)],
            "organizaciones": lambda n: n.get("organizaciones") or [],
            "lugares": lambda n: n.get("lugares") or [],
            "objetos": lambda n: [o.get("nombre") for o in (n.get("objetos") or []) if isinstance(o, dict)],
        }
        porcentajes = {}
        for categoria, extraer in extractores.items():
            apariciones = Counter()
            for n in noticias:
                for valor in {str(v).strip().lower() for v in extraer(n) if v}:
                    apariciones[valor] += 1
            total = len(apariciones) or 1
            solo_una = sum(1 for c in apariciones.values() if c == 1)
            porcentajes[categoria] = 100 * solo_una / total

        serie = pd.Series(porcentajes).sort_values(ascending=False)
        fig, ax = plt.subplots(figsize=(8, 5))
        serie.plot(kind="bar", ax=ax, color="slategray")
        ax.set_title("Entidades que solo aparecen en una noticia (%)")
        ax.set_ylabel("% del total de esa categoría")
        ruta = self._guardar(fig, "conectividad_entidades.png")
        print(f"  Guardado: {ruta}")
        print(serie.to_string())

    def ejecutar(self) -> None:
        """Corre todas las visualizaciones pedidas en la guía."""
        noticias = self._cargar_noticias()
        print(f"Noticias válidas cargadas: {len(noticias)}")
        if not noticias:
            print(
                "No hay JSON válidos en data/json/. Ejecute primero: python main.py extraer")
            return
        print("-- Noticias por fuente --")
        self.noticias_por_fuente()
        print("-- Delitos frecuentes --")
        self.delitos_frecuentes()
        print("-- Lugares frecuentes --")
        self.lugares_frecuentes()
        print("-- Campos faltantes --")
        self.campos_faltantes()
        print("-- Evolución temporal --")
        self.evolucion_temporal()
        print("-- Tipos de relación frecuentes --")
        self.tipos_relacion_frecuentes()
        print("-- Conectividad de entidades --")
        self.conectividad_entidades()
        print(f"Gráficos guardados en {self.dir_salida}")
