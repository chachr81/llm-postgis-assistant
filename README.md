# LLM PostGIS Assistant

Asistente inteligente que transforma lenguaje natural en consultas SQL espaciales para PostgreSQL + PostGIS. Funciona 100% localmente utilizando modelos LLM servidos con [Ollama](https://ollama.com/).

---

## Características

- Traducción automática de preguntas en español a SQL seguro.
- Soporte completo para funciones espaciales de PostGIS:
  - `ST_Intersects`, `ST_DWithin`, `ST_Buffer`, `ST_Area`, `ST_Transform`, `ST_Centroid`, `ST_ClusterKMeans`, entre otros.
- Corrección automática de consultas:
  - Normaliza SRID si detecta unidades métricas o hectáreas.
  - Detecta campos geométricos e identificadores reales desde el catálogo.
  - Ajusta `geom` → `geometria`, `id` → `id_presonalizados`, etc.
- Funciona completamente offline:
  - No envía datos a servidores externos.
  - Puede conectarse a cualquier base de datos PostgreSQL/PostGIS local o remota.

---

## Requisitos

- Python ≥ 3.10
- PostgreSQL con extensión PostGIS
- [Ollama](https://ollama.com) instalado y ejecutando un modelo compatible (ej: `sqlcoder`)
- [`sqlcoder-7b`](https://huggingface.co/defog/sqlcoder-7b) (recomendado)

---
## Estructura del Proyecto
```bash
├── app/
│   ├── main.py              ← FastAPI App
│   ├── routers/chat.py      ← Endpoint /api/chat
│   └── ...
├── db/
│   ├── introspect.py        ← Inspección de tablas, columnas, SRIDs
│   ├── schema_cache.py      ← Catálogo para resolver referencias espaciales
│   └── sql_fixup.py         ← Correcciones automáticas de SQL generadas
├── llm/
│   ├── prompts.py           ← Plantilla de sistema e instructivos para el LLM
│   └── models/              ← Modelos locales (no incluidos en el repo)
├── requirements.txt
└── README.md
```
---
## Notas Adicionales

- El proyecto no expone tu base de datos ni requiere conexión a internet.
- Se recomienda personalizar las funciones en sql_fixup.py para adaptarse a tu modelo de datos y SRIDs locales.

---

## Instalación rápida

```bash
git clone https://github.com/tu_usuario/llm-postgis-assistant.git
cd llm-postgis-assistant

# Activar entorno virtual
python -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

```
---
## Licencia

- MIT © 2025 – Christian Chacón Romero \n
- Este proyecto es de código abierto y puedes modificarlo, adaptarlo y compartirlo con la comunidad.

---