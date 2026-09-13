# Migracion a disco F: (6TB) — 2026-09-08

Todo Expertia vive en `F:\expertia\`. Las rutas originales son junctions permanentes,
cero cambios de codigo.

## Junctions

| Ruta original | Destino F: | Contenido |
|---|---|---|
| `E:\expertia-data` | `F:\expertia\data` | incubator.db 684GB (viva) |
| `D:\proyectos\expertia` | `F:\expertia\proyecto` | incubator-root, training, llama.cpp |
| `D:\training` | `F:\expertia\training-disk` | Q4 GGUF + Modelfiles |
| `E:\aria2-1.37.0-win-64bit-build1` | `F:\expertia\aria2` | dummy 0B exigido por validate_paths |

## Excluido de la copia

- `storage/incubator.db` 318GB (copia obsoleta 26/08) — queda en `expertia.pre-f`

## Backups pre-migracion (NO borrar sin OK)

`E:\expertia-data.pre-f`, `D:\proyectos\expertia.pre-f`, `D:\training.pre-f`,
`E:\aria2-....pre-f`, mas `F:\expertia\pre\specialist_registry.json` y `pipeline_state.json`.

## Rollback

Borrar junctions + renombrar `.pre-f` de vuelta + arrancar API y pipeline.

## Notas

- Defender exclusion: `F:\expertia` (admin, aplicada 2026-09-08).
- Letra F: disco externo fijo en su puerto; si cambia la letra, recrear junctions.
- GGUF ExpertiaMath usa pre-tokenizer `gpt-2` (Ollama 0.33.3 no conoce `phi-3`).
  Misma correccion aplicada en 3070 (`C:\training\merged\*.pre-gpt2.bak`).
- Rollback ExpertiaMath->Qwen: `backup_Mathematics.json` + `orchestrator.py.pre-expertiamath.backup`.
- Lanzamiento blindado 3070 (2026-09-11): NUNCA `Start-Process` directo en sesion
  WinRM (el teardown mata hijos al cerrarla). Usar `training/Start-Training-3070.ps1`
  (tarea SYSTEM `ExpertiaTrainPhysics` + `Run-Physics.cmd`) o doble clic local.
  El auto-relaunch de `sync_train_status.ps1` tambien va por tarea + guarda `done`.
- 3070: TdrDelay/TdrDdiDelay 60 (HKLM, verificado), relojes capados 1200MHz,
  offload CPU activo, seq1024. Event 153 = fallo GPU bajo carga sostenida.
- 2026-09-10: EMA manual restore SWE 0.991321 -> 0.9998610471794568 (backup pre-swap).
  Causa: ciclo canario qwen3.5 con thinking ON (0 paquetes) registrado como fallo
  `knowledge` (penalizacion x0.99); era error operativo experimental (debió ser
  `system`, sin penalizacion). Verificado q=0.91 tras fix `think:false` top-level
  en `llm_manager.py`. Trazado en `activity_log` (WARNING).
- Modelos 2026-09-10: Physics/Chemistry/SWE/Electronics/DataScience/Cybersecurity/
  Geopolitics/Sociology `qwen3.5:4b-8k` (+fix `think:false` top-level en
  `llm_manager.py`), Mathematics `ExpertiaMath:latest`.
  Regla: tags qwen3* requieren variante `-8k` (`PARAMETER num_ctx 8192`) por su
  ctx 256K por defecto (trampa 43GB en CPU).
  Backups filas: `backup_<Dominio>.json` + `.pre-qwen3*.backup`.
  Pendientes (genéricos): 6xphi4 (Psych/Env/Philo/Astro/Art/Ling), finance-phi3,
  llama-medx, law_model. Medicine/Legal, últimos.
- 2026-09-12: trio phi4 (Psychology/EnvironmentalScience/PhilosophyHistory) ->
  `qwen3.5:4b-8k`. Canario 2+2+3 ciclos: Philo 0.919, Env 0.885, Psych 0.873
  (vs 0.927/0.894/0.895). Timeout 120min en 1 ciclo Psych (arXiv 429, system).
  Adoptados por éxito 100% + rendimiento ~400 pkgs/ciclo.
