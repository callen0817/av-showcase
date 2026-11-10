import os
import json
import shutil
import re
from pathlib import Path

brain_dir = Path(r"C:\Users\ChristopherAllen\.gemini\antigravity\brain\bffdea0e-bfe6-4494-bace-4b4c7a0fda4e")
workspace_dir = Path(r"c:\Users\ChristopherAllen\OneDrive - Reisource\Desktop\AV_Walkthrough")
target_dir = workspace_dir / "docs" / "antigravity-history"

target_dir.mkdir(parents=True, exist_ok=True)

# 1. Copy markdown artifacts
artifacts = [
    ("project_review.md", "01_project_review.md"),
    ("implementation_plan.md", "02_implementation_plan.md"),
    ("task.md", "03_task_checklist.md"),
    ("walkthrough.md", "04_project_walkthrough.md"),
]

for src_name, dst_name in artifacts:
    src_file = brain_dir / src_name
    dst_file = target_dir / dst_name
    if src_file.exists():
        shutil.copy2(src_file, dst_file)
        print(f"Copied: {src_name} -> {dst_name}")

# 2. Copy scratch directory
scratch_src = brain_dir / "scratch"
scratch_dst = target_dir / "scratch"
if scratch_src.exists():
    shutil.copytree(scratch_src, scratch_dst, dirs_exist_ok=True)
    print(f"Copied scratch scripts: {scratch_src} -> {scratch_dst}")

# 3. Copy raw transcript
raw_transcript_src = brain_dir / ".system_generated" / "logs" / "transcript.jsonl"
raw_transcript_dst = target_dir / "raw_transcript.jsonl"
if raw_transcript_src.exists():
    shutil.copy2(raw_transcript_src, raw_transcript_dst)
    print(f"Copied raw transcript: {raw_transcript_src} -> {raw_transcript_dst}")

# 4. Generate readable session transcripts markdown
def clean_user_prompt(text):
    if not text:
        return ""
    # Extract content inside <USER_REQUEST> if present
    match = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", text, re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
    else:
        cleaned = text.strip()
    # Strip out any remaining prompt envelope metadata
    cleaned = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", cleaned, flags=re.DOTALL).strip()
    return cleaned

turns = []
cur_user = None
cur_assistant_texts = []

with open(raw_transcript_src, "r", encoding="utf-8") as f:
    for line in f:
        try:
            obj = json.loads(line)
            t = obj.get("type")
            if t == "USER_INPUT":
                if cur_user:
                    turns.append((cur_user, "\n\n".join(cur_assistant_texts).strip()))
                    cur_assistant_texts = []
                cur_user = {
                    "step": obj.get("step_index"),
                    "time": obj.get("created_at"),
                    "content": clean_user_prompt(obj.get("content", ""))
                }
            elif t == "PLANNER_RESPONSE":
                c = obj.get("content", "")
                if c and c.strip():
                    cur_assistant_texts.append(c.strip())
        except Exception:
            pass

if cur_user:
    turns.append((cur_user, "\n\n".join(cur_assistant_texts).strip()))

print(f"Extracted {len(turns)} conversation turns.")

output_md_path = target_dir / "05_session_transcripts.md"
with open(output_md_path, "w", encoding="utf-8") as f:
    f.write("# AV Walkthrough: Antigravity Session Transcripts & Evolutionary Log\n\n")
    f.write("> **Overview**: This document compiles the chronological conversation transcripts, requirements, design alignments, and problem-solving milestones recorded by Antigravity during the architecture, implementation, bug resolution, and multi-level floor detection evolution of AV Walkthrough.\n\n")
    f.write("---\n\n")
    
    for i, (u, a) in enumerate(turns):
        f.write(f"## Turn {i+1} — Step {u['step']} ({u['time']})\n\n")
        f.write("### 👤 User Request\n\n")
        user_content = u['content'] if u['content'] else "*(Blank / Trigger input)*"
        f.write(f"{user_content}\n\n")
        
        f.write("### 🤖 Antigravity Assistant Response & Actions\n\n")
        if a:
            f.write(f"{a}\n\n")
        else:
            f.write("*(System actions, tool executions, and state transitions recorded in raw transcript)*\n\n")
            
        f.write("---\n\n")

print(f"Successfully generated readable session transcript at: {output_md_path}")
