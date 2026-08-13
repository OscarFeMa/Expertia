# Manual de Uso - Sistema de Destilación de Conocimiento con Ollama

## Tabla de Contenidos

1. [Introducción](#introducción)
2. [Requisitos Previos](#requisitos-previos)
3. [Instalación de Ollama](#instalación-de-ollama)
4. [Configuración del Sistema](#configuración-del-sistema)
5. [Uso del Sistema de Destilación](#uso-del-sistema-de-destilación)
6. [Estructura de Datos](#estructura-de-datos)
7. [Ejemplos Prácticos](#ejemplos-prácticos)
8. [Solución de Problemas](#solución-de-problemas)
9. [Optimización de Rendimiento](#optimización-de-rendimiento)

---

## Introducción

El **Sistema de Destilación de Conocimiento con Ollama** es una extensión del Async Expert Incubator que utiliza modelos de lenguaje local (LLMs) para sintetizar y estructurar conocimiento extraído de fuentes web.

### Características Principales

- **Procesamiento Local**: Todo el procesamiento se realiza localmente usando Ollama
- **Síntesis Interdisciplinaria**: Clasificación automática de dominios de conocimiento
- **Estructuración Inteligente**: Extracción de conceptos clave, argumentos y evidencia
- **Generación de Evaluaciones**: Creación automática de 5 pares de preguntas-respuestas
- **Persistencia en Base de Datos**: Almacenamiento estructurado en SQLite
- **Procesamiento Secuencial**: Respeto de límites de RAM/VRAM del sistema

---

## Requisitos Previos

### Hardware

- **Sistema Operativo**: Windows 11 (Native execution)
- **Python**: 3.10 o superior
- **RAM**: Mínimo 8 GB (recomendado 16 GB para modelos 3B)
- **VRAM**: 4-8 GB para aceleración GPU (opcional pero recomendado)
- **Espacio en Disco**: 10 GB para modelos Ollama

### Software

- Python 3.10+
- Ollama (instalado localmente)
- Acceso a internet para búsqueda web inicial

---

## Instalación de Ollama

### Paso 1: Descargar Ollama

Visite [https://ollama.ai](https://ollama.ai) y descargue Ollama para Windows.

### Paso 2: Instalar Ollama

Ejecute el instalador descargado y siga las instrucciones del asistente.

### Paso 3: Verificar Instalación

Abra una terminal y ejecute:

```bash
ollama --version
```

Debería ver la versión de Ollama instalada.

### Paso 4: Iniciar Ollama

Ollama se inicia automáticamente como servicio en Windows. Verifique que esté ejecutándose:

```bash
ollama list
```

### Paso 5: Descargar un Modelo

Descargue un modelo ligero para destilación:

```bash
# Modelo Qwen 2.5 (3B parámetros) - Recomendado
ollama pull qwen2.5:3b

# Alternativa: Llama 3.2 (3B parámetros)
ollama pull llama3.2:3b

# Alternativa: Phi-3 (3.8B parámetros)
ollama pull phi3
```

### Paso 6: Verificar el Modelo

```bash
ollama run qwen2.5:3b "Hola, ¿puedes presentarte?"
```

---

## Configuración del Sistema

### Instalar Dependencias de Python

```bash
cd d:/proyectos/expertia/incubator-root
pip install -r requirements.txt
```

Esto instalará:
- `ddgs>=4.0.0` - Motor de búsqueda
- `trafilatura>=1.6.0` - Extracción de contenido
- `aiohttp>=3.9.0` - Cliente HTTP asíncrono para Ollama

### Configurar el Modelo en `incubator_ingestion.py`

Edite el archivo `incubator_ingestion.py` y modifique la línea:

```python
# Para habilitar destilación con Ollama
orchestrator = IncubatorOrchestrator(use_distillation=True, model_name="qwen2.5:3b")

# Para deshabilitar destilación (modo demo)
orchestrator = IncubatorOrchestrator(use_distillation=False, model_name="qwen2.5:3b")
```

### Configurar el Endpoint de Ollama (Opcional)

Si Ollama está en un puerto diferente, edite `crawler/distiller.py`:

```python
async def distill_markdown_with_ollama(
    markdown_content: str,
    model_name: str = "qwen2.5:3b",
    ollama_url: str = "http://localhost:11434/api/generate"  # Cambiar si es necesario
) -> Dict:
```

---

## Uso del Sistema de Destilación

### Ejecución Básica

```bash
cd d:/proyectos/expertia/incubator-root
python incubator_ingestion.py
```

### Flujo de Trabajo

1. **Test de Conectividad**: Verifica búsqueda y extracción web
2. **Auditoría de Registro**: Revisa expertos locales existentes
3. **Búsqueda Web**: Busca URLs relevantes para el tema
4. **Extracción de Markdown**: Convierte HTML a Markdown limpio
5. **Destilación con Ollama**: Sintetiza conocimiento estructurado
6. **Almacenamiento en BD**: Guarda paquetes en SQLite
7. **Generación de Resumen**: Muestra resultados en consola

### Habilitar/Deshabilitar Destilación

**Para habilitar destilación** (producción):

```python
orchestrator = IncubatorOrchestrator(use_distillation=True, model_name="qwen2.5:3b")
```

**Para deshabilitar destilación** (desarrollo/pruebas):

```python
orchestrator = IncubatorOrchestrator(use_distillation=False, model_name="qwen2.5:3b")
```

---

## Estructura de Datos

### Salida de Destilación (JSON)

El sistema genera un objeto JSON con la siguiente estructura:

```json
{
    "domain_classification": "Science",
    "thesis_or_core_objective": "Understanding the fundamental principles of quantum computing",
    "structured_knowledge": {
        "key_concepts": [
            "Quantum superposition",
            "Entanglement",
            "Quantum gates",
            "Qubits",
            "Quantum algorithms"
        ],
        "main_arguments": [
            "Quantum computers solve certain problems exponentially faster",
            "Superposition enables parallel computation",
            "Entanglement provides quantum correlations"
        ],
        "supporting_evidence": [
            "Shor's algorithm for factoring",
            "Grover's algorithm for search",
            "Experimental quantum supremacy demonstrations"
        ],
        "implications": [
            "Cryptography revolution",
            "Drug discovery acceleration",
            "Optimization problems solved efficiently"
        ]
    },
    "evaluation_exam": [
        {
            "question": "What is quantum superposition?",
            "answer": "Quantum superposition is the ability of quantum systems to exist in multiple states simultaneously..."
        },
        // ... 5 pares QA en total
    ]
}
```

### Esquema de Base de Datos

**Tabla `knowledge_packages`**:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER | ID único auto-incremental |
| topic | TEXT | Tema de investigación |
| source_url | TEXT | URL de origen del contenido |
| domain | TEXT | Dominio de conocimiento |
| structured_knowledge | TEXT (JSON) | Conocimiento estructurado |
| exam_dataset | TEXT (JSON) | 5 pares QA de evaluación |
| created_at | TIMESTAMP | Fecha de creación |

---

## Ejemplos Prácticos

### Ejemplo 1: Destilación de Artículo Técnico

```python
import asyncio
from incubator_ingestion import IncubatorOrchestrator

async def main():
    # Crear orquestador con destilación habilitada
    orchestrator = IncubatorOrchestrator(
        use_distillation=True, 
        model_name="qwen2.5:3b"
    )
    
    # Ejecutar pipeline
    result = await orchestrator.run_pipeline("machine learning neural networks")
    
    # Ver resultados
    print(f"Packages destilados: {len(result['distilled_packages'])}")
    for pkg in result['distilled_packages']:
        print(f"Domain: {pkg['domain']}")
        print(f"Thesis: {pkg['thesis']}")

asyncio.run(main())
```

### Ejemplo 2: Consultar Paquetes por Dominio

```python
from database.queries import get_knowledge_packages_by_domain

# Obtener todos los paquetes de Ciencia
science_packages = get_knowledge_packages_by_domain("Science")

for pkg in science_packages:
    print(f"Topic: {pkg['topic']}")
    print(f"Domain: {pkg['domain']}")
    print(f"Concepts: {pkg['structured_knowledge']['key_concepts']}")
```

### Ejemplo 3: Consultar Paquetes por Tema

```python
from database.queries import get_knowledge_packages_by_topic

# Buscar paquetes relacionados con "quantum"
quantum_packages = get_knowledge_packages_by_topic("quantum")

for pkg in quantum_packages:
    print(f"Source: {pkg['source_url']}")
    print(f"Thesis: {pkg['thesis_or_core_objective']}")
```

### Ejemplo 4: Destilación Manual de Markdown

```python
import asyncio
from crawler.distiller import distill_markdown_with_ollama

async def main():
    markdown_content = """
    # Quantum Computing Fundamentals
    
    Quantum computing harnesses quantum phenomena like superposition 
    and entanglement to process information in fundamentally new ways...
    """
    
    result = await distill_markdown_with_ollama(
        markdown_content,
        model_name="qwen2.5:3b"
    )
    
    print(f"Domain: {result['domain_classification']}")
    print(f"Thesis: {result['thesis_or_core_objective']}")
    print(f"Concepts: {result['structured_knowledge']['key_concepts']}")

asyncio.run(main())
```

---

## Solución de Problemas

### Problema 1: Ollama No Responde

**Síntoma**: Timeout error al conectar con Ollama

**Soluciones**:
```bash
# Verificar que Ollama esté ejecutándose
ollama list

# Reiniciar Ollama
# En Windows: Reiniciar el servicio Ollama desde Services.msc

# Verificar el puerto
netstat -an | findstr 11434
```

### Problema 2: Modelo No Encontrado

**Síntoma**: Error "model not found"

**Solución**:
```bash
# Descargar el modelo
ollama pull qwen2.5:3b

# Verificar modelos disponibles
ollama list
```

### Problema 3: JSON Parse Error

**Síntoma**: Error al parsear respuesta JSON del modelo

**Causa**: El modelo no devolvió JSON válido

**Solución**:
- El sistema incluye manejo de errores y retorna estructura fallback
- Considere usar un modelo más robusto (llama3.2:3b)
- Reduzca la longitud del contenido de entrada

### Problema 4: Memoria Insuficiente

**Síntoma**: Error de memoria o rendimiento lento

**Soluciones**:
- Use modelos más pequeños (3B en lugar de 7B)
- Procese URLs secuencialmente (ya implementado)
- Cierre otras aplicaciones que consuman RAM
- Considere usar GPU si está disponible

### Problema 5: Base de Datos No Se Inicializa

**Síntoma**: Error al insertar paquetes de conocimiento

**Solución**:
```python
from database.connection import initialize_database
initialize_database()
```

### Problema 6: Timeout en Destilación

**Síntoma**: La destilación tarda demasiado

**Solución**:
- Aumente el timeout en `crawler/distiller.py`
- Use un modelo más rápido
- Reduzca la longitud del contenido de entrada

---

## Optimización de Rendimiento

### Selección de Modelos

| Modelo | Parámetros | RAM Mínima | Velocidad | Calidad |
|-------|------------|------------|-----------|---------|
| qwen2.5:3b | 3B | 4 GB | Rápido | Buena |
| llama3.2:3b | 3B | 4 GB | Rápido | Excelente |
| phi3 | 3.8B | 6 GB | Medio | Excelente |
| qwen2.5:7b | 7B | 8 GB | Lento | Superior |

### Configuración de Timeout

Edite `crawler/distiller.py` para ajustar tiempos:

```python
timeout=aiohttp.ClientTimeout(total=PARSER_TIMEOUT + 120)  # Aumentar para modelos más lentos
```

### Procesamiento por Lotes

Para procesar múltiples temas:

```python
topics = ["machine learning", "quantum computing", "neural networks"]

for topic in topics:
    orchestrator = IncubatorOrchestrator(use_distillation=True)
    result = await orchestrator.run_pipeline(topic)
    # Guardar resultados...
```

### Monitoreo de Recursos

```python
import psutil

# Verificar uso de RAM antes de destilación
ram_usage = psutil.virtual_memory().percent
print(f"RAM usage: {ram_usage}%")

if ram_usage > 80:
    print("Advertencia: Alta uso de RAM")
```

---

## Dominios de Conocimiento Soportados

El sistema clasifica automáticamente el contenido en estos dominios:

- **Science**: Física, Química, Biología, Matemáticas
- **Technology**: Ingeniería, Computación, IA, Robótica
- **Philosophy**: Ética, Lógica, Metafísica, Epistemología
- **Economics**: Microeconomía, Macroeconomía, Finanzas
- **History**: Historia mundial, Historia regional
- **Geopolitics**: Relaciones internacionales, Política global
- **Literature**: Análisis literario, Teoría literaria
- **Art**: Historia del arte, Crítica de arte
- **Medicine**: Medicina clínica, Investigación médica
- **Law**: Derecho constitucional, Derecho internacional

---

## Buenas Prácticas

### 1. Preparación del Contenido

- Asegúrese de que el contenido de entrada sea relevante y de calidad
- Evite contenido muy corto (< 500 caracteres)
- Trunque contenido muy largo (> 12000 caracteres)

### 2. Gestión de Modelos

- Use modelos 3B para destilación rápida
- Use modelos 7B para mayor profundidad analítica
- Mantenga solo los modelos necesarios instalados

### 3. Almacenamiento

- Realice backups regulares de `storage/incubator.db`
- Limpie paquetes antiguos periódicamente
- Use índices de base de datos para consultas eficientes

### 4. Monitoreo

- Revise los logs en `logs/` regularmente
- Monitoree el uso de RAM durante destilación
- Verifique la calidad de las salidas JSON

### 5. Escalabilidad

- Procese temas secuencialmente para evitar sobrecarga
- Considere procesamiento por lotes para grandes volúmenes
- Use GPU si está disponible para aceleración

---

## Referencias de API

### Función Principal

```python
async def distill_markdown_with_ollama(
    markdown_content: str,
    model_name: str = "qwen2.5:3b",
    ollama_url: str = "http://localhost:11434/api/generate"
) -> Dict
```

**Parámetros**:
- `markdown_content`: Contenido Markdown a destilar
- `model_name`: Nombre del modelo Ollama
- `ollama_url`: URL del endpoint de Ollama

**Retorna**:
- `Dict`: Paquete de conocimiento estructurado

### Funciones de Base de Datos

```python
def add_knowledge_package(
    topic: str,
    source_url: str,
    domain: str,
    structured_knowledge: Dict,
    exam_dataset: Dict
) -> int

def get_knowledge_packages_by_topic(topic: str) -> List[Dict]

def get_knowledge_packages_by_domain(domain: str) -> List[Dict]
```

---

## Apéndice: Comandos Útiles de Ollama

```bash
# Listar modelos disponibles
ollama list

# Descargar modelo
ollama pull qwen2.5:3b

# Ejecutar modelo interactivo
ollama run qwen2.5:3b

# Ver información del modelo
ollama show qwen2.5:3b

# Eliminar modelo
ollama rm qwen2.5:3b

# Verificar versión
ollama --version

# Ver logs de Ollama
# En Windows: Ver Event Viewer
```

---

**Última Actualización**: 23 de Mayo de 2026
**Versión**: 2.0.0 (con Ollama Integration)
