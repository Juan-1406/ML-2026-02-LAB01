# Laboratorio: noticias delictuales, LLM y Obsidian

Pipeline académico para transformar **noticias delictuales no estructuradas** en un grafo de conocimiento en Obsidian.

El repositorio cubre dos entregas:

1. **Lab 01:** captura (Google News + medios chilenos) y limpieza de texto.
2. **Lab 02:** extracción con Gemini y validación JSON. El **vault de Obsidian** y las visualizaciones siguen siendo `TODO(alumno)`.

La implementación de Gemini es **mínima y ejecutable**: el alumno debe mejorar el prompt, el parseo y el manejo de errores.

No se entrena clustering. Los grupos de noticias se forman por **relaciones explícitas** (mismo delito, persona, organización o lugar).

## Requisitos

- [Conda](https://docs.conda.io/) (Miniconda o Anaconda)
- Uso académico de sitios de prensa: respetar términos de uso, no sobrecargar servidores
- Cuenta de [Google AI Studio](https://aistudio.google.com/) y `GEMINI_API_KEY` para `python main.py extraer`

## Entorno conda

No use `pip install` ni `requirements.txt`. El entorno oficial es `environment.yml`.

```bash
conda env create -f environment.yml
conda activate lab-noticias-obsidian
```

Para recrearlo:

```bash
conda env update -f environment.yml --prune
```

Copie las variables de entorno (la clave de Gemini **nunca** se sube a Git):

```bash
cp .env.example .env
# edite .env y complete GEMINI_API_KEY
```

## Cómo ejecutar

Desde la raíz del repositorio, con el entorno activado:

```bash
python main.py descubrir   # RSS de Google News → actualiza data/urls.csv
python main.py capturar    # URLs → data/raw/*.html y data/processed/*.txt
python main.py extraer     # Gemini → data/json/*.json (requiere GEMINI_API_KEY)
python main.py obsidian    # TODO(alumno): vault Markdown
python main.py analizar    # TODO(alumno): Data Understanding
python main.py pipeline    # descubrir + capturar + extraer; avisa etapas pendientes
```

El identificador `id_noticia` se conserva en todo el flujo: `N001.html` → `N001.txt` → `N001.json` → `Noticias/N001.md`.

Para probar el escritor de Obsidian **sin** llamar a Gemini, use el fixture [data/json/ejemplo_N001.json](data/json/ejemplo_N001.json).

## Qué está implementado y qué debe completar

| Módulo | Estado | Qué hace |
| --- | --- | --- |
| `src/adquisicion/` | Listo | Google News (RSS), fábrica de capturadores, adaptadores BioBio / Cooperativa / La Tercera, fallback genérico |
| `src/limpieza/` | Listo | `LimpiadorHTML`: quita menús, scripts y líneas cortas |
| `src/modelos.py` | Listo | Dataclasses del contrato JSON |
| `src/pipeline.py` + `main.py` | Listo | Orquestación por etapas |
| `src/conocimiento/utilidades.py` | Listo | `slugify` y `[[wiki-links]]` para cuando complete Obsidian |
| `src/extraccion/` | Listo (simple) | Prompt + llamada a Gemini + `data/json/`; el alumno puede mejorarlo |
| `src/validacion/` | Listo (simple) | `json.loads`, campos obligatorios y tipos lista |
| `src/conocimiento/obsidian.py` | `TODO(alumno)` | Notas Markdown enlazadas |
| `src/analisis/` | `TODO(alumno)` | Gráficos de calidad y cobertura |

Si ejecuta una etapa pendiente, el programa imprime una pista y **no falla en silencio**.

## Diseño en breve

`PipelineLaboratorio` coordina:

1. `DescubridorGoogleNews` consulta el RSS público (`hl=es-419`, `gl=CL`). **No scrapea** el HTML de `news.google.com`. Resuelve redirects hasta la URL del medio y agrega filas a `data/urls.csv` sin duplicar.
2. `FabricaCapturadores.para(url, fuente)` elige un adaptador por dominio. Si el selector CSS no encuentra el artículo, usa `CapturadorGenerico` (fallback).
3. El HTML queda en `data/raw/` y el texto útil en `data/processed/`.
4. `ExtractorGemini` lee el texto, llama a Gemini y guarda JSON en `data/json/`. `ValidadorJSON` comprueba el contrato.
5. El alumno completa el vault en `obsidian_vault/`.

Clases principales: `PipelineLaboratorio` coordina descubridor, fábrica de capturadores, extractor Gemini, validador y escritor Obsidian.

## Contrato JSON

Cada noticia extraída debe incluir: `id_noticia`, `titulo`, `fecha_publicacion`, `fuente`, `url`, `resumen`, `delitos`, `personas` (nombre y rol), `organizaciones`, `lugares`, `objetos`, `relaciones` (`origen`, `tipo`, `destino`).

Si un dato no aparece en el texto, use `null` o una lista vacía. **No invente** entidades ni culpabilidad.

## Vault de Obsidian (objetivo del alumno)

```
obsidian_vault/
├── 00_Indice.md
├── Noticias/
├── Delitos/
├── Personas/
├── Organizaciones/
├── Lugares/
├── Objetos/
└── Relaciones/
```

Las relaciones se expresan con enlaces `[[...]]`. No se usa SQLite, MongoDB ni Neo4j.

## Datos de ejemplo

- [data/consultas.csv](data/consultas.csv): búsquedas semilla para Google News
- [data/urls.csv](data/urls.csv): cuatro noticias públicas (BioBioChile, Cooperativa, La Tercera)
- [data/json/ejemplo_N001.json](data/json/ejemplo_N001.json): JSON de ejemplo para implementar Obsidian sin API

Las URLs de prensa cambian con el tiempo. Si una descarga falla, el lote continúa y registra el error. Puede ampliar `urls.csv` a mano (30–50 URLs verificadas, como pide la guía).

## Ética

- El análisis es académico y exploratorio.
- Cite siempre la fuente y conserve la URL.
- Los roles (detenido, imputado, acusado, condenado, víctima, testigo) **no son equivalentes**.
- No afirme culpabilidad si la noticia no lo dice de forma explícita.
- Respete los términos de uso de cada medio y de Google News (solo RSS).

## Presentación del laboratorio

Las presentaciones Beamer y los Colab viven en `docs/` **solo en la copia local** (la carpeta está en `.gitignore` y no se publica en GitHub).

## Estructura del repositorio

```
main.py                 Orquestador CLI
environment.yml         Entorno conda
src/pipeline.py         PipelineLaboratorio
src/adquisicion/        Captura (implementada)
src/limpieza/           Limpieza HTML (implementada)
src/extraccion/         Gemini (implementación simple)
src/validacion/         Validación JSON (implementación simple)
src/conocimiento/       Interfaz Obsidian + slugify
src/analisis/           Interfaz Data Understanding
data/                   URLs, HTML, texto, JSON
obsidian_vault/         Bóveda (a generar por el alumno)
```
