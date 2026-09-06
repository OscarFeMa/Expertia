import argparse
import json
import math
import sys
from pathlib import Path

import torch
from datasets import load_dataset
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from tqdm import tqdm


def format_example(ex):
    return f"<|system|>\n{ex.get('system','')}\n<|user|>\n{ex.get('instruction','')}\n<|assistant|>\n{ex.get('output','')}"


def perplexity(model, tok, texts, seq_len, stride=512):
    model.eval()
    num = 0.0
    den = 0
    with torch.no_grad():
        for t in tqdm(texts, desc="eval"):
            ids = tok(t, return_tensors="pt").input_ids[0]
            for i in range(0, len(ids), stride):
                chunk = ids[i:i + seq_len]
                if len(chunk) < 16:
                    continue
                inp = chunk.unsqueeze(0).to(model.device)
                out = model(inp, labels=inp)
                num += out.loss.item() * len(chunk)
                den += len(chunk)
    return math.exp(num / max(den, 1)) if den else float("nan")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--adapter", default="")
    p.add_argument("--val", required=True)
    p.add_argument("--seq-len", type=int, default=1024)
    p.add_argument("--max-samples", type=int, default=500)
    p.add_argument("--out", default="")
    args = p.parse_args()

    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True, use_fast=False)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model, quantization_config=bnb,
                                                 device_map={"": 0}, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16)
    tag = "base"
    if args.adapter:
        model = PeftModel.from_pretrained(model, args.adapter)
        tag = "adapter"
    ds = load_dataset("json", data_files=args.val, split="train")
    texts = [format_example(ds[i]) for i in range(min(args.max_samples, len(ds)))]
    ppl = perplexity(model, tok, texts, args.seq_len)
    rep = {"tag": tag, "model": args.model, "adapter": args.adapter,
           "val_samples": len(texts), "perplexity": ppl}
    print(json.dumps(rep, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps(rep, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
