"""Orquestación OOP del laboratorio (CRISP-DM adaptado).

Etapas implementadas: descubrimiento, captura/limpieza, extracción Gemini
con validación y vault Obsidian. Etapa pendiente del alumno: análisis.
"""

from __future__ import annotations

import csv
from pathlib import Path

from src.adquisicion.fabrica import FabricaCapturadores
from src.adquisicion.google_news import DescubridorGoogleNews
from src.adquisicion.http import ClienteHTTP
from src.adquisicion.repositorio import RepositorioNoticias
from src.analisis.explorador import ExploradorDatos
from src.config import DIR_JSON, DIR_RAW, GEMINI_API_KEY, RUTA_URLS
from src.conocimiento.obsidian import EscritorVaultObsidian
from src.excepciones import EtapaPendienteAlumno
from src.extraccion.gemini import ExtractorGemini
from src.limpieza.limpiador import LimpiadorHTML
from src.modelos import NoticiaFuente
from src.validacion.validador import ValidadorJSON


class PipelineLaboratorio:
    """Coordina las etapas sin mezclar responsabilidades de cada módulo."""

    def __init__(
        self,
        cliente: ClienteHTTP | None = None,
        descubridor: DescubridorGoogleNews | None = None,
        fabrica: FabricaCapturadores | None = None,
        repositorio: RepositorioNoticias | None = None,
        limpiador: LimpiadorHTML | None = None,
        extractor: ExtractorGemini | None = None,
        validador: ValidadorJSON | None = None,
        escritor: EscritorVaultObsidian | None = None,
        explorador: ExploradorDatos | None = None,
        ruta_urls: Path = RUTA_URLS,
    ) -> None:
        self.cliente = cliente or ClienteHTTP()
        self.descubridor = descubridor or DescubridorGoogleNews(
            cliente=self.cliente)
        self.limpiador = limpiador or LimpiadorHTML()
        self.fabrica = fabrica or FabricaCapturadores(
            cliente=self.cliente, limpiador=self.limpiador
        )
        self.repositorio = repositorio or RepositorioNoticias()
        self.extractor = extractor or ExtractorGemini()
        self.validador = validador or ValidadorJSON()
        self.escritor = escritor or EscritorVaultObsidian()
        self.explorador = explorador or ExploradorDatos()
        self.ruta_urls = ruta_urls

    def _leer_urls(self) -> list[NoticiaFuente]:
        if not self.ruta_urls.exists():
            raise FileNotFoundError(
                f"No existe {self.ruta_urls}. Ejecute primero: python main.py descubrir"
            )
        with self.ruta_urls.open(encoding="utf-8", newline="") as fh:
            filas = list(csv.DictReader(fh))
        return [
            NoticiaFuente(
                id_noticia=fila["id_noticia"],
                fuente=fila.get("fuente", ""),
                url=fila["url"],
                categoria_busqueda=fila.get("categoria_busqueda", ""),
            )
            for fila in filas
            if fila.get("url")
        ]

    def ejecutar_descubrimiento(self) -> int:
        """Google News RSS → actualiza data/urls.csv."""
        print("== Etapa: descubrir (Google News RSS) ==")
        nuevos = self.descubridor.actualizar_urls_csv()
        print(f"URLs nuevas agregadas: {len(nuevos)}")
        return len(nuevos)

    def ejecutar_captura(self) -> tuple[int, int]:
        """Descarga HTML, extrae cuerpo (adaptador o fallback) y guarda texto."""
        print("== Etapa: capturar (HTML + limpieza) ==")
        noticias = self._leer_urls()
        ok, fallos = 0, 0
        for noticia in noticias:
            print(f"  [{noticia.id_noticia}] {noticia.fuente} → {noticia.url}")
            try:
                capturador = self.fabrica.para(noticia.url, noticia.fuente)
                html = capturador.obtener_html(noticia.url)
                self.repositorio.guardar_html(noticia, html)

                cuerpo = capturador.extraer_cuerpo(html)
                uso_fallback = False
                if not cuerpo.strip():
                    # Fallback: el selector del medio no encontró el artículo.
                    cuerpo = self.fabrica.generico.extraer_cuerpo(html)
                    uso_fallback = True

                if not cuerpo.strip():
                    print("    Sin texto útil; se omite.")
                    fallos += 1
                    continue

                self.repositorio.guardar_texto(noticia, cuerpo)
                noticia.html = html
                noticia.texto_limpio = cuerpo
                extra = " (fallback genérico)" if uso_fallback else f" ({type(capturador).__name__})"
                print(f"    OK{extra}: {len(cuerpo)} caracteres")
                ok += 1
            except Exception as exc:  # noqa: BLE001 — una URL no debe tumbar el lote
                fallos += 1
                print(f"    Error: {exc}")
        print(
            f"Captura finalizada: {ok} ok, {fallos} fallos, {len(noticias)} total")
        return ok, fallos

    def ejecutar_extraccion(self) -> tuple[int, int]:
        """Gemini: texto limpio → JSON en data/json/, validado contra el contrato."""
        print("== Etapa: extraer (Gemini) ==")
        noticias = self._leer_urls()
        ok, fallos = 0, 0
        for noticia in noticias:
            print(f"  [{noticia.id_noticia}] {noticia.fuente}")
            try:
                noticia.texto_limpio = self.repositorio.leer_texto(
                    noticia.id_noticia)
            except FileNotFoundError:
                print(
                    "    Sin texto en data/processed/; ejecute primero: python main.py capturar")
                fallos += 1
                continue

            ruta_html = DIR_RAW / f"{noticia.id_noticia}.html"
            if ruta_html.exists():
                # La fecha rara vez está en el texto visible (vive en <meta>/JSON-LD),
                # así que se busca aparte en el HTML crudo en vez de pedírsela al LLM.
                noticia.fecha_publicacion = self.limpiador.extraer_fecha(
                    ruta_html.read_text(encoding="utf-8")
                )

            try:
                self.extractor.extraer(noticia)
                self.validador.validar(DIR_JSON / f"{noticia.id_noticia}.json")
                print(
                    f"    OK: guardado y validado en data/json/{noticia.id_noticia}.json")
                ok += 1
            except EtapaPendienteAlumno as pendiente:
                print(pendiente)
                fallos += 1
                break
            except Exception as exc:  # noqa: BLE001 — una noticia no debe tumbar el lote
                print(f"    Error: {exc}")
                fallos += 1
        print(
            f"Extracción finalizada: {ok} ok, {fallos} fallos, {len(noticias)} total")
        return ok, fallos

    def _cargar_json_validados(self) -> list[dict]:
        """JSON de noticias que cumplen el contrato; los inválidos se omiten."""
        noticias = []
        for ruta in sorted(DIR_JSON.glob("N[0-9]*.json")):
            try:
                noticias.append(self.validador.validar(ruta, registrar=False))
            except ValueError as exc:
                print(f"  Omitido {ruta.name}: {exc}")
        return noticias

    def ejecutar_obsidian(self) -> int:
        """JSON validados → notas Markdown enlazadas en obsidian_vault/."""
        print("== Etapa: obsidian (vault) ==")
        noticias = self._cargar_json_validados()
        if not noticias:
            print("No hay JSON válidos en data/json/. Ejecute primero: python main.py extraer")
            return 0
        self.escritor.escribir_vault(noticias)
        notas = len(list(self.escritor.vault.rglob("*.md")))
        print(
            f"Vault generado en {self.escritor.vault}: {len(noticias)} noticias, {notas} notas, "
            f"{self.escritor.variantes_unificadas} variantes unificadas (data/equivalencias.csv)"
        )
        return len(noticias)

    def ejecutar_analisis(self) -> None:
        """TODO(alumno): Data Understanding y visualizaciones."""
        print("== Etapa: analizar (Data Understanding) ==")
        try:
            self.explorador.ejecutar()
        except EtapaPendienteAlumno as pendiente:
            print(pendiente)

    def ejecutar_pipeline(self) -> None:
        """Corre lo implementado y avisa las etapas que el alumno debe completar."""
        self.ejecutar_descubrimiento()
        self.ejecutar_captura()
        self.ejecutar_extraccion()
        self.ejecutar_obsidian()
        self.ejecutar_analisis()
