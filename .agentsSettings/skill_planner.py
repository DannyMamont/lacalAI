import os
import sys
import json
import requests

def run_planner_mode(ollama_url, model_name, system_prompt, full_dialog_history, todo_path, workspace_structure, mode="PLAN"):
    existing_todo = ""
    if os.path.exists(todo_path):
        with open(todo_path, 'r', encoding='utf-8') as f:
            existing_todo = f.read()

    # Директивы переводим на английский для идеального понимания моделью 3B
    if mode == "APPEND":
        print("\n[Скилл Планнера] Режим инкрементального дополнения ТЗ...")
        task_directive = (
            f"INCREMENTAL UPDATE REQUIRED.\n"
            f"Analyze the existing TODO.md specification and append new technical milestones at the very end. "
            f"Do NOT duplicate or wipe existing checkpoints.\n\n"
            f"CURRENT EXISTING TODO.md:\n{existing_todo}"
        )
    else:
        print("\n[Скилл Планнера] Режим создания нового ТЗ...")
        task_directive = "NEW PLAN REQUIRED. Generate a fresh, concise, step-by-step TODO.md blueprint from scratch."

    full_prompt = (
        f"### SYSTEM INSTRUCTIONS:\n{system_prompt}\n\n"
        f"### CURRENT WORKSPACE STRUCTURE:\n{workspace_structure}\n\n"
        f"### USER DIALOG & CLARIFICATION HISTORY:\n{full_dialog_history}\n\n"
        f"### EXECUTION DIRECTIVE:\n{task_directive}\n\n"
        "Output ONLY the final markdown content for TODO.md with the correct trailing mode tag:"
    )

    payload = {
        "model": model_name, 
        "prompt": full_prompt, 
        "stream": True,
        "options": {
            "temperature": 0.2,      # Максимальная строгость
            "num_ctx": 5120,
            "repeat_penalty": 1.1,    # Возвращаем к щадящему дефолтному значению
            "num_gpu": 99,
            "keep_alive": 0
        }
    }

    todo_content = ""
    try:
        response = requests.post(ollama_url, json=payload, stream=True)
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line.decode('utf-8'))
                text = chunk.get("response", "")
                todo_content += text
                sys.stdout.write(text)
                sys.stdout.flush()
        print()
        
        with open(todo_path, 'w', encoding='utf-8') as f:
            f.write(todo_content)
        print(f"[Скилл Планнера] Файл TODO.md успешно обновлен.")
        return True
    except Exception as e:
        print(f"\n[Скилл Планнера] Ошибка: {e}"); return False
