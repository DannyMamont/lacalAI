import sys
import json
import requests
import re
import core
import os
import systemPromts

CODER_CONTEXT_LENGTH = 8192

def run_coder_mode(workspace_root, model_name, todo_file):
    """
    Автономный цикл кодинга.
    На каждой итерации считывает актуальное состояние проекта и TODO.md,
    находит первый невыполненный шаг и отправляет его модели Qwen/DeepSeek.
    """
    print(f"\n==== ЗАПУСК РЕЖИМА КОДЕРА (Модель: {model_name}) ====")
    
    # Исходный контекст выполнения пустой
    current_context = "Project just started. No commands executed yet."
    
    # Лимит итераций для предотвращения бесконечных циклов
    max_turns = 15
    
    for turn in range(1, max_turns + 1):
        print(f"\n--- Итерация кодинга {turn}/{max_turns} ---")
        
        # 1. Проверяем актуальную структуру проекта прямо сейчас
        current_structure = core.get_project_structure(workspace_root, todo_file)
        
        # 2. Динамически вычисляем ТЕКУЩИЙ активный шаг из TODO.md
        current_task = "All tasks completed! Verify the project and output @@@DONE if finished."
        if os.path.exists(todo_file):
            with open(todo_file, 'r', encoding='utf-8') as f:
                todo_lines = f.read().splitlines()
            
            for line in todo_lines:
                stripped = line.strip()
                # Ищем строку, которая начинается с "- [ ]" или просто "- " (но без [x])
                if stripped.startswith("- [ ]") or (stripped.startswith("- ") and not "[x]" in stripped.lower()):
                    # Вытаскиваем чистый текст задачи для модели
                    current_task = stripped.replace("- [ ]", "").replace("- ", "").strip()
                    break

        # 3. Формируем жесткий, сфокусированный промпт без лишнего мусора из истории
        # Это не дает модели читать свои старые вопросы "Хотите я продолжу?"
        full_prompt = (
            f"### CURRENT PROJECT REALITY:\n{current_structure}\n\n"
            f"### SYSTEM INSTRUCTIONS (MANDATORY):\n{system_promts.SYSTEM_PROMPT_CODER}\n\n"
            f"### YOUR EXACT TARGET FOR THIS TURN:\n"
            f"You must strictly work ONLY on this specific step: '{current_task}'.\n"
            f"Look at the project structure above. Do not repeat what is already created.\n\n"
            f"### LAST OPERATION RESULT:\n{current_context}\n"
        )
        
        # 4. Отправляем запрос в Ollama
        payload = {
            "model": model_name,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.1  # Делаем модель максимально послушной и точной
            }
        }
        
        try:
            response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=90)
            if response.status_code != 200:
                print(f"[Ошибка Ollama]: Код ответа {response.status_code}")
                break
                
            response_text = response.json().get("response", "").strip()
            print("\n[Ответ модели]:")
            print(response_text)
            
        except Exception as e:
            print(f"[Ошибка подключения к Ollama]: {e}")
            break
            
        # 5. Проверяем, зафиксировала ли модель финал работы
        if "@@@DONE" in response_text:
            print("\n[Движок]: Кодер успешно завершил все задачи по плану!")
            break
            
        # 6. Передаем ответ в ядро. 
        # Ядро запишет файлы, выполнит тесты и АВТОМАТИЧЕСКИ отметит шаг в TODO.md как [x]
        execution_result = core.execute_command(response_text, workspace_root)
        
        # Обновляем контекст для следующего хода (модель увидит только результат работы файлового движка)
        if execution_result:
            current_context = execution_result
        else:
            current_context = "Files written or checked successfully. No terminal output."

    print("\n==== РЕЖИМ КОДЕРА ЗАВЕРШЕН ====")
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
