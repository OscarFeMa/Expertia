import argparse
import json
import os
from pathlib import Path

import time
import torch
from datasets import load_dataset
from peft import LoraConfig, prepare_model_for_kbit_training, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments, TrainerCallback
from trl import SFTTrainer

STATUS_FILE = Path(os.environ.get("TRAIN_STATUS_FILE", r"D:\proyectos\expertia\training\logs\train_status.json"))


class StatusCallback(TrainerCallback):
    def __init__(self):
        self.t0 = time.time()
        self.history = []

    def on_log(self, args, state, control, logs=None, **kwargs):
        try:
            STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
            if logs and logs.get("loss") is not None:
                self.history.append({"step": state.global_step, "loss": round(float(logs["loss"]), 4)})
                self.history = self.history[-120:]
            elapsed = int(time.time() - self.t0)
            payload = {
                "phase": "training",
                "step": state.global_step,
                "max_steps": state.max_steps,
                "epoch": round(state.epoch or 0, 2),
                "loss": logs.get("loss") if logs else None,
                "lr": logs.get("learning_rate") if logs else None,
                "elapsed_s": elapsed,
                "steps_per_min": round(state.global_step / max(elapsed / 60, 0.01), 2),
                "loss_history": self.history,
                "ts": time.time(),
            }
            STATUS_FILE.write_text(json.dumps(payload), encoding="utf-8")
        except Exception:
            pass

BASE_MODEL = "microsoft/Phi-4-mini-reasoning"
DEFAULT_TRAIN = r"D:\proyectos\expertia\training\datasets\expertia-math-puro.jsonl"
DEFAULT_OUT = r"D:\proyectos\expertia\training\adapters\expertia-math-r16"
DEFAULT_OFFLOAD = r"D:\proyectos\expertia\training\offload"

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")


def format_example(ex):
    system = ex.get("system", "")
    instruction = ex.get("instruction", "")
    output = ex.get("output", "")
    return f"<|system|>\n{system}\n<|user|>\n{instruction}\n<|assistant|>\n{output}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=BASE_MODEL)
    p.add_argument("--train", default=DEFAULT_TRAIN)
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--offload", default=DEFAULT_OFFLOAD)
    p.add_argument("--epochs", type=float, default=3.0)
    p.add_argument("--seq-len", type=int, default=1024)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--accum", type=int, default=16)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--rank", type=int, default=16)
    p.add_argument("--alpha", type=int, default=32)
    p.add_argument("--max-steps", type=int, default=0)
    p.add_argument("--save-steps", type=int, default=200)
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--bf16", action="store_true")
    p.add_argument("--no-offload", action="store_true")
    args = p.parse_args()
    dtype = torch.bfloat16 if args.bf16 else torch.float16

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    Path(args.offload).mkdir(parents=True, exist_ok=True)

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=dtype,
        bnb_4bit_use_double_quant=True,
    )

    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True, use_fast=False)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.model_max_length = args.seq_len
    tok.truncation_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=bnb,
        device_map={"": 0} if args.no_offload else "auto",
        offload_folder=args.offload,
        trust_remote_code=True,
        torch_dtype=dtype,
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    lora = LoraConfig(
        r=args.rank,
        lora_alpha=args.alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora)

    ds = load_dataset("json", data_files=args.train, split="train")
    ds = ds.map(lambda ex: {"text": format_example(ex)}, remove_columns=ds.column_names)

    targs = TrainingArguments(
        output_dir=str(out_dir),
        num_train_epochs=args.epochs,
        max_steps=args.max_steps if args.max_steps > 0 else -1,
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.accum,
        learning_rate=args.lr,
        fp16=not args.bf16,
        bf16=args.bf16,
        optim="paged_adamw_8bit",
        logging_steps=10,
        save_steps=args.save_steps,
        save_total_limit=3,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        max_grad_norm=1.0,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=ds,
        args=targs,
        max_seq_length=args.seq_len,
        dataset_text_field="text",
    )
    trainer.add_callback(StatusCallback())
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps({"phase": "starting", "step": 0, "ts": time.time()}), encoding="utf-8")
    except Exception:
        pass
    resume = None
    if not args.no_resume:
        ckpts = sorted(out_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[-1]))
        if ckpts:
            resume = str(ckpts[-1])
    try:
        STATUS_FILE.write_text(json.dumps({"phase": "resuming" if resume else "starting", "step": 0, "resume_from": resume, "ts": time.time()}), encoding="utf-8")
    except Exception:
        pass
    trainer.train(resume_from_checkpoint=resume)
    try:
        STATUS_FILE.write_text(json.dumps({"phase": "done", "step": trainer.state.global_step, "ts": time.time()}), encoding="utf-8")
    except Exception:
        pass
    trainer.save_model(str(out_dir))
    tok.save_pretrained(str(out_dir))

    with open(out_dir / "train_info.json", "w", encoding="utf-8") as f:
        json.dump({"model": args.model, "train": args.train, "seq_len": args.seq_len, "rank": args.rank, "alpha": args.alpha}, f, ensure_ascii=False)

    print(json.dumps({"saved": str(out_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
