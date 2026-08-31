import sys
import json
import requests
import re
import core

CODER_CONTEXT_LENGTH = 8192

def run_coder_mode(ollama_url, model_name, system_prompt, final_todo, workspace_root, todo_file):
    print("\n================ ЭТАП АВТОНОМНОГО КОДИНГА (GPU-STREAM) ================")
    
    context_turns = []
    workspace_file_cache = {}
    
    base_context = (
        f"Project Structure:\n{core.get_project_structure(workspace_root, todo_file)}\n\n"
        f"Requirements (TODO.md):\n{final_todo}\n"
    )
    
    coder_prompt = "Execute the next milestone from TODO.md. Output your thoughts, show the code, and trigger the terminal action using 'RUN: your_command' at the very end."

    for turn in range(15):
        print(f"\n--- Итерация кодинга {turn + 1}/15 ---")
        
        cache_summary = ""
        if workspace_file_cache:
            cache_summary = "\n### YOUR CURRENTLY ACCUMULATED FILE MEMORY CACHE:\n"
            for cached_file, content_blocks in workspace_file_cache.items():
                cache_summary += f"File: {cached_file}\n---\n{''.join(content_blocks)}\n---\n"

        active_history = "\n".join(context_turns[-4:]) if context_turns else ""
        current_context = f"{base_context}{cache_summary}\nRecent Steps:\n{active_history}"
        
        full_prompt = (
            f"### SYSTEM INSTRUCTIONS (MANDATORY):\n{system_prompt}\n\n"
            f"### CONTEXT WINDOW MEMORY:\n{current_context}\n\n"
            f"### CURRENT TASK:\n{coder_prompt}\n\n"
            f"REMEMBER: Speak normally, show code blocks, and always put 'RUN: your_command' at the absolute end to execute actions."
        )
        
        # ЖЕСТКИЙ СТРИМИНГ БЕЗ ИНСТРУМЕНТОВ
        payload = {
            "model": model_name, 
            "prompt": full_prompt, 
            "stream": True,
            "options": {"temperature": 0.1, "num_ctx": CODER_CONTEXT_LENGTH, "num_gpu": 99, "keep_alive": 0}
        }
        
        response_text = ""
        try:
            # Используем исходный URL (http://localhost:11434/api/generate)
            response = requests.post(ollama_url, json=payload, stream=True)
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    text = chunk.get("response", "")
                    response_text += text
                    sys.stdout.write(text)
                    sys.stdout.flush()
            print()
        except Exception as e:
            print(f"\n[Скилл Кодера] Ошибка запроса к API Ollama: {e}"); return

        if "@@@DONE" in response_text:
            if turn < 3:
                coder_prompt = "You output @@@DONE too early. Verify TODO.md milestones and finalize implementation."
                continue
            print("\n[Движок] Работа успешно завершена."); break
            
        result = core.execute_command(response_text, workspace_root)
        
        if result:
            print(result)
            context_turns.append(f"Turn {turn} Terminal Action Output:\n{result}\n")
            coder_prompt = "Analyze the terminal output. If the command successfully created or updated the file, move to the next task in TODO.md."
        else:
            print("\n[Внимание] Ошибка синтаксиса команды!")
            coder_prompt = "CRITICAL ERROR: No terminal action triggered. You MUST end your response with 'RUN: your_command' to impact the project!"
