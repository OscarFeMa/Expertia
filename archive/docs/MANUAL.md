# Manual de Instrucciones - Async Expert Incubator

## Tabla de Contenidos

1. [Introducción](#introducción)
2. [Requisitos del Sistema](#requisitos-del-sistema)
3. [Instalación](#instalación)
4. [Configuración](#configuración)
5. [Estructura del Proyecto](#estructura-del-proyecto)
6. [Uso Básico](#uso-básico)
7. [Funcionalidades Principales](#funcionalidades-principales)
8. [Base de Datos de Expertos](#base-de-datos-de-expertos)
9. [Solución de Problemas](#solución-de-problemas)
10. [Ejemplos de Uso](#ejemplos-de-uso)

---

## Introducción

**Async Expert Incubator** es un motor fundamental para el ecosistema "Pensamiento Coral". Este sistema actúa como un "Bibliotecario/Maestro" responsable de:

- Auditar el inventario local de expertos
- Rastrear datos web confiables de forma segura
- Preparar paquetes de conocimiento prístinos usando LLMs locales

El sistema está optimizado para entornos de bajos recursos en Windows 11, con ejecución nativa (sin Docker ni WSL).

---

## Requisitos del Sistema

### Hardware
- **Sistema Operativo**: Windows 11 (Native execution)
- **Python**: Versión 3.10 o superior
- **Memoria RAM**: Mínimo 4 GB (recomendado 8 GB)
- **Espacio en Disco**: 500 MB para el proyecto y datos

### Software
- Python 3.10+
- pip (gestor de paquetes de Python)
- Acceso a internet para búsqueda web

---

## Instalación

### Paso 1: Navegar al Directorio del Proyecto

```bash
cd d:/proyectos/expertia/incubator-root
```

### Paso 2: Instalar Dependencias

```bash
pip install -r requirements.txt
```

Esto instalará:
- `ddgs>=4.0.0` - Motor de búsqueda DuckDuckGo
- `trafilatura>=1.6.0` - Extracción de contenido HTML a Markdown

### Paso 3: Verificar Instalación

```bash
python -c "import ddgs; import trafilatura; print('Instalación exitosa')"
```

---

## Configuración

### Archivo de Configuración Principal

El archivo `config/settings.py` contiene todos los parámetros configurables:

```python
# Rutas de directorios
BASE_DIR = Path(__file__).parent.parent
STORAGE_DIR = BASE_DIR / "storage"
LOGS_DIR = BASE_DIR / "logs"

# Base de datos
DATABASE_PATH = STORAGE_DIR / "incubator.db"

# Configuración de búsqueda
SEARCH_DELAY_MIN = 2.5  # Retraso mínimo en segundos
SEARCH_DELAY_MAX = 4.5  # Retraso máximo en segundos
MAX_RESULTS_PER_SEARCH = 5  # Máximo de resultados por búsqueda

# User-Agents rotativos (7 opciones)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
    # ... más User-Agents
]

# Umbral de puntuación de adecuación
SUITABILITY_THRESHOLD = 0.85
```

### Personalización

Para personalizar la configuración:

1. Abra `config/settings.py`
2. Modifique los valores según sus necesidades
3. Guarde los cambios

---

## Estructura del Proyecto

```
incubator-root/
├── config/
│   ├── __init__.py
│   └── settings.py         # Configuración del sistema
├── database/
│   ├── __init__.py
│   ├── connection.py       # Conexión SQLite
│   └── queries.py          # Operaciones de registro de expertos
├── crawler/
│   ├── __init__.py
│   ├── search_engine.py    # Búsqueda DuckDuckGo
│   └── parser.py           # Extracción HTML a Markdown
├── logs/                   # Logs operacionales
├── storage/
│   ├── incubator.db        # Base de datos SQLite
│   └── packages/           # Paquetes de conocimiento generados
├── incubator_ingestion.py # Script principal de orquestación
├── requirements.txt        # Dependencias
├── README.md              # Documentación en inglés
└── MANUAL.md              # Este manual
```

---

## Uso Básico

### Ejecutar el Script Principal

```bash
python incubator_ingestion.py
```

### Qué Esperar

1. **Test de Conectividad**: Verifica que el sistema puede buscar y extraer contenido
2. **Auditoría del Registro**: Muestra el inventario local de expertos
3. **Búsqueda Web**: Busca URLs relevantes para el tema
4. **Extracción de Contenido**: Convierte HTML a Markdown limpio
5. **Generación de Paquetes**: Guarda los paquetes de conocimiento

### Salida del Sistema

El sistema genera:
- **Logs**: Archivos en `logs/` con timestamp
- **Paquetes**: Archivos Markdown en `storage/packages/`
- **Base de Datos**: `storage/incubator.db` con registro de expertos

---

## Funcionalidades Principales

### 1. Búsqueda Web Segura

**Función**: `search_topic(query: str, max_results: int = 3)`

**Características**:
- Retrasos aleatorios (2.5-4.5 segundos) para evitar bloqueos
- Rotación de User-Agents (7 opciones)
- Búsqueda asíncrona compatible

**Ejemplo**:
```python
from crawler.search_engine import search_topic

results = await search_topic("Python machine learning", max_results=3)
for result in results:
    print(f"Título: {result['title']}")
    print(f"URL: {result['url']}")
    print(f"Snippet: {result['snippet']}")
```

### 2. Extracción de Contenido

**Función**: `extract_clean_markdown(url: str) -> str`

**Características**:
- Extracción a formato Markdown
- Preservación de tablas y enlaces
- Eliminación de elementos boilerplate
- Manejo robusto de errores

**Ejemplo**:
```python
from crawler.parser import extract_clean_markdown

markdown = extract_clean_markdown("https://example.com/article")
print(markdown[:300])  # Primeros 300 caracteres
```

### 3. Registro de Expertos

**Funciones Principales**:
- `add_expert()` - Agregar nuevo experto
- `get_all_experts()` - Obtener todos los expertos
- `find_best_expert()` - Encontrar el mejor experto para un tema
- `audit_registry()` - Auditoría completa con matriz ASCII

**Ejemplo**:
```python
from database.queries import add_expert, audit_registry

# Agregar experto
expert_id = add_expert(
    name="Dr. PostgreSQL",
    core_domain="Database Optimization",
    tags="postgresql, query, optimization, performance",
    ema_score=0.9
)

# Auditoría
should_halt, expert, score = audit_registry("PostgreSQL query optimization")
```

---

## Base de Datos de Expertos

### Esquema de la Tabla

```sql
CREATE TABLE expert_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    core_domain TEXT NOT NULL,
    tags TEXT,
    ema_score REAL DEFAULT 0.0,
    system_prompt TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### Campos

- **id**: Identificador único auto-incremental
- **name**: Nombre del experto
- **core_domain**: Dominio principal de experiencia
- **tags**: Palabras clave separadas por comas
- **ema_score**: Puntuación EMA (0.0 - 1.0)
- **system_prompt**: Prompt del sistema (opcional)
- **created_at**: Fecha de creación
- **updated_at**: Fecha de última actualización

### Puntuación de Adecuación

La puntuación de adecuación (0.0 - 1.0) se calcula usando:

```
Puntuación = (Ratio de intersección de palabras clave × 0.7) + (Puntuación EMA × 0.3)
```

Si la puntuación > 0.85, el sistema detiene la ingesta web y usa el experto existente.

---

## Solución de Problemas

### Problema 1: Error "duckduckgo_search renamed to ddgs"

**Causa**: Paquete obsoleto instalado

**Solución**:
```bash
pip uninstall duckduckgo-search
pip install ddgs
```

### Problema 2: Error "fetch_url() got an unexpected keyword argument 'timeout'"

**Causa**: API de Trafilatura actual no soporta parámetro timeout

**Solución**: Ya corregido en `crawler/parser.py`. Si persiste, verifique que está usando la versión actual del código.

### Problema 3: No se encuentran resultados de búsqueda

**Causas posibles**:
- Conexión a internet intermitente
- DuckDuckGo bloqueando solicitudes
- Query demasiado específico

**Soluciones**:
- Verifique su conexión a internet
- Aumente los retrasos en `config/settings.py`
- Pruebe con un query más general

### Problema 4: Extracción falla para ciertos sitios

**Causas posibles**:
- Sitio requiere JavaScript
- Sitio bloquea bots
- Contenido protegido

**Soluciones**:
- Verifique si el sitio está en la lista de dominios bloqueados
- Considere usar un User-Agent diferente
- El sitio puede no ser compatible con Trafilatura

### Problema 5: Base de datos no se inicializa

**Causa**: Permisos de escritura insuficientes

**Solución**:
```bash
# Verifique permisos en el directorio storage/
icacls storage /grant Users:F
```

---

## Ejemplos de Uso

### Ejemplo 1: Búsqueda Simple

```python
import asyncio
from crawler.search_engine import search_topic

async def main():
    results = await search_topic("artificial intelligence trends", max_results=3)
    for idx, result in enumerate(results, 1):
        print(f"{idx}. {result['title']}")
        print(f"   {result['url']}")
        print()

asyncio.run(main())
```

### Ejemplo 2: Extracción de Contenido

```python
from crawler.parser import extract_clean_markdown

url = "https://www.postgresql.org/docs/current/planner-optimizer.html"
markdown = extract_clean_markdown(url)

if markdown:
    print(f"Éxito: Extraídos {len(markdown)} caracteres")
    print(f"Preview: {markdown[:200]}...")
else:
    print("Fallo: No se pudo extraer contenido")
```

### Ejemplo 3: Gestión de Expertos

```python
from database.queries import add_expert, find_best_expert

# Agregar experto
add_expert(
    name="Expert AI",
    core_domain="Artificial Intelligence",
    tags="machine learning, neural networks, deep learning",
    ema_score=0.85
)

# Encontrar mejor experto
expert, score = find_best_expert("neural network optimization")
if expert:
    print(f"Mejor experto: {expert['name']} (Score: {score:.2f})")
```

### Ejemplo 4: Pipeline Completo

```python
import asyncio
from incubator_ingestion import IncubatorOrchestrator

async def main():
    orchestrator = IncubatorOrchestrator()
    result = await orchestrator.run_pipeline("quantum computing applications")
    
    if result['status'] == 'completed':
        print(f"Generados {len(result['knowledge_packages'])} paquetes")
        orchestrator.save_knowledge_packages()

asyncio.run(main())
```

---

## Tips y Mejores Prácticas

### 1. Retrasos Anti-Blocking
- Mantenga los retrasos entre 2.5-4.5 segundos
- No reduzca los retrasos para evitar bloqueos IP

### 2. Gestión de Expertos
- Use puntuaciones EMA realistas (0.0 - 1.0)
- Agregue etiquetas específicas y relevantes
- Actualice las puntuaciones basándose en el rendimiento

### 3. Extracción de Contenido
- Verifique siempre si el resultado es no nulo
- Use previews para verificar la calidad del contenido
- Filtre dominios de redes sociales si no son necesarios

### 4. Logs y Monitoreo
- Revise regularmente los logs en `logs/`
- Use timestamps para rastrear ejecuciones
- Mantenga el directorio de logs limpio

### 5. Almacenamiento
- Los paquetes se guardan en `storage/packages/`
- Limpie regularmente paquetes antiguos
- Considere implementar un sistema de rotación

---

## Soporte y Contribuciones

### Reportar Problemas

Si encuentra un problema:
1. Revise la sección de Solución de Problemas
2. Verifique los logs en `logs/`
3. Documente los pasos para reproducir el problema

### Mejoras Futuras

Posibles mejoras:
- Integración con más motores de búsqueda
- Soporte para más formatos de salida
- Sistema de caché para URLs ya procesadas
- Interfaz web para gestión de expertos

---

## Licencia

Este proyecto es parte del ecosistema "Pensamiento Coral".

---

## Apéndice A: Referencias Rápidas

### Comandos Útiles

```bash
# Ejecutar el sistema
python incubator_ingestion.py

# Ver logs
type logs\incubator_*.log

# Limpiar paquetes antiguos
del storage\packages\*.md

# Ver base de datos
sqlite3 storage/incubator.db "SELECT * FROM expert_registry;"
```

### Variables de Entorno

No se requieren variables de entorno adicionales. Toda la configuración está en `config/settings.py`.

### Archivos de Configuración

- `config/settings.py` - Configuración principal
- `requirements.txt` - Dependencias de Python
- `storage/incubator.db` - Base de datos SQLite

---

**Última Actualización**: 23 de Mayo de 2026
**Versión**: 1.0.0
