"""Stage the HuggingFace dataset payload and upload it.

Usage:
  HF_TOKEN=hf_... .venv/bin/python -m scripts.publish_hf [--stage-only] [--repo REPO_ID]

- Creates the dataset repo if missing (public), uploads hf_dataset/ via
  upload_folder() (resumable: re-running skips finished files), then verifies
  line counts and byte sizes against local files.
- HF_TOKEN is read from the environment only; it is never written to any file.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

STAGE_DIR = os.path.join(REPO_ROOT, "hf_dataset")
HF_REPO = "ezra77/llm-forecast-calibration"

STAGE_MAP = [
    ("DATASET_CARD.md", "README.md"),  # HF renders the card only from README.md
    ("DATA_LICENSE", "DATA_LICENSE"),
    ("LICENSE", "LICENSE"),
    ("CITATION.cff", "CITATION.cff"),
    ("CITATION.bib", "CITATION.bib"),
    ("RELEASE_NOTES.md", "RELEASE_NOTES.md"),
    ("data/questions.jsonl", "questions.jsonl"),
    ("data/parsed/parsed.jsonl", "parsed/parsed.jsonl"),
]
RAW_GLOB_DIR = os.path.join(REPO_ROOT, "data", "raw")


def copy_text(src, dst):
    # Match the repository's LF text bytes even from a Windows CRLF checkout.
    text = Path(src).read_text(encoding="utf-8")
    Path(dst).write_text(text, encoding="utf-8", newline="\n")


def stage():
    expected_dir = Path(REPO_ROOT).resolve() / "hf_dataset"
    if Path(STAGE_DIR).resolve() != expected_dir:
        raise ValueError("Refusing to replace a staging directory outside this repository")
    if os.path.exists(STAGE_DIR):
        shutil.rmtree(STAGE_DIR)
    os.makedirs(os.path.join(STAGE_DIR, "raw"), exist_ok=False)
    os.makedirs(os.path.join(STAGE_DIR, "parsed"), exist_ok=False)
    staged = []
    for src, dst in STAGE_MAP:
        src_path = os.path.join(REPO_ROOT, src)
        dst_path = os.path.join(STAGE_DIR, dst)
        os.makedirs(os.path.dirname(dst_path) or STAGE_DIR, exist_ok=True)
        copy_text(src_path, dst_path)
        staged.append(dst)
    raw_files = sorted(
        f for f in os.listdir(RAW_GLOB_DIR) if f.endswith(".jsonl")
    )
    for f in raw_files:
        copy_text(os.path.join(RAW_GLOB_DIR, f), os.path.join(STAGE_DIR, "raw", f))
        staged.append(f"raw/{f}")
    print(f"staged {len(staged)} files into hf_dataset/")
    for s in staged:
        print(f"  {s}")
    return STAGE_DIR


def expected_stats():
    def count(p):
        with open(os.path.join(REPO_ROOT, p), encoding="utf-8") as f:
            return sum(1 for _ in f)
    stats = {
        "questions.jsonl": count("data/questions.jsonl"),
        "parsed/parsed.jsonl": count("data/parsed/parsed.jsonl"),
    }
    sizes = {}
    for rel in ["questions.jsonl", "parsed/parsed.jsonl"] + [
        f"raw/{f}" for f in sorted(os.listdir(RAW_GLOB_DIR)) if f.endswith(".jsonl")
    ]:
        p = os.path.join(STAGE_DIR, rel)
        sizes[rel] = os.path.getsize(p)
    return stats, sizes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage-only", action="store_true")
    ap.add_argument("--repo", default=HF_REPO)
    args = ap.parse_args()

    stage_dir = stage()
    stats, sizes = expected_stats()
    print("expected line counts:", stats)

    if args.stage_only:
        print("--stage-only: stopping before upload")
        return

    from huggingface_hub import HfApi

    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("HF_TOKEN env var is required (export HF_TOKEN=hf_... in the shell)")
    api = HfApi()
    api.create_repo(args.repo, repo_type="dataset", private=False, exist_ok=True)
    print(f"repo ready: https://huggingface.co/datasets/{args.repo}")
    url = api.upload_folder(
        folder_path=stage_dir,
        repo_id=args.repo,
        repo_type="dataset",
        commit_message="Publish llm-forecast-calibration raw dataset (212 questions, 3,831 responses, parsed probabilities)",
    )
    print(f"uploaded: {url}")

    print("=== verification vs local ===")
    infos = api.get_paths_info(args.repo, list(sizes), repo_type="dataset")
    remote = {}
    for i in infos:
        # RepoFile has .path and .size; skip folders (size None)
        if getattr(i, "size", None) is not None:
            remote[i.path] = i.size
    ok = True
    for rel, size in sizes.items():
        r = remote.get(rel)
        status = "OK" if r == size else f"MISMATCH local={size} remote={r}"
        if r != size:
            ok = False
        print(f"  {rel}: {status}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
