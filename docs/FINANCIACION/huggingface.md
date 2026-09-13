# Publicación Hugging Face (reputación + backup off-site)

Preparado en `training/hf_cards/` + `training/hf_cards/upload_hf.py` (dry-run OK).

## Pasos del usuario (15 min, único trabajo manual)

1. Crear cuenta en https://huggingface.co (email + verificar).
2. Settings → Access Tokens → New token (write) → copiar.
3. En SOBREMESA: `set HF_TOKEN=... && set HF_USER=<tu-usuario>`.
4. Ejecutar `python training/hf_cards/upload_hf.py` (yo lo lanzo).

## Qué se publica

- `ExpertiaMath-Q4` / `ExpertiaPhysics-Q4` (GGUF 2.5GB c/u + README con evals).
- `ExpertiaMath-r16` / `ExpertiaPhysics-r16` (adapters, sin checkpoints).
- `expertia-domain-datasets` (6 JSONL ~140MB + datasheet).
- Licencia CC-BY-NC-4.0 (comunidad) — la vía comercial queda reservada
  (dual-license futura, sin prisa).

## GitHub (código)

Repo local ya con `.gitignore` (secretos excluidos). Crear repo vacío en
github.com + `git remote add origin ...` + `git push` (yo lo hago contigo).
