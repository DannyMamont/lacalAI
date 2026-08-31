import os
import sys
import time
import subprocess
import requests

import systemPromts as s
import core
import skill_analyzer
import skill_planner
import skill_coder
import re

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_PLANNER = "llama3.2:3b"
MODEL_CODER = "bonsai-fast:latest"
TODO_FILE = "TODO.md"

SYSTEM_PROMPT_ANALYZER = s.SYSTEM_PROMPT_ANALYZER
SYSTEM_PROMPT_PLANNER = s.SYSTEM_PROMPT_PLANNER
SYSTEM_PROMPT_CODER = s.SYSTEM_PROMPT_CODER

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TODO_PATH = os.path.join(WORKSPACE_ROOT, TODO_FILE)

def init_ollama_cuda():
    print("[Движок] Проверка и подготовка графического сервера Ollama...")
    if sys.platform == "win32":
        subprocess.run("taskkill /f /im ollama.exe 2>nul", shell=True)
    else:
        subprocess.run("pkill -f ollama 2>/dev/null", shell=True)
        
    os.environ["OLLAMA_VULKAN"] = "0"
    os.environ["OLLAMA_LLM_LIBRARY"] = "cuda_v12"
    os.environ["OLLAMA_NUM_PARALLEL"] = "1"
    
    try:
        if sys.platform == "win32":
            subprocess.Popen(["ollama", "serve"], creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[Ошибка]: {e}"); sys.exit(1)
        
    for _ in range(15):
        try:
            res = requests.get("http://localhost:11434/", timeout=(3, 5))
            if res.status_code == 200:
                print("[Движок] Сервер Ollama успешно запущен на GPU (CUDA)!")
                return
        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
            time.sleep(1)
    print("[Критическая ошибка] Сервер Ollama не ответил."); sys.exit(1)

def run_pipeline(initial_idea):
    print("\n================ ВХОДНОЙ АНАЛИЗ И КРИТИКА ================")
    
    current_todo_content = ""
    if os.path.exists(TODO_PATH):
        with open(TODO_PATH, 'r', encoding='utf-8') as f:
            current_todo_content = f.read()

    dialog_history = f"Initial Raw Idea: {initial_idea}\n"
    current_input = initial_idea
    detected_mode = "PLAN"
    
    while True:
        analysis = skill_analyzer.run_analyzer_mode(
            OLLAMA_URL, MODEL_PLANNER, current_input, SYSTEM_PROMPT_ANALYZER, dialog_history, current_todo_content
        )
        
        if "[MODE: PLAN]" in analysis:
            detected_mode = "PLAN"
            break
        elif "[MODE: APPEND]" in analysis:
            detected_mode = "APPEND"
            break
            
        print("\n========================================================")
        print("[Система] Модель запрашивает уточнения по доработке.")
        user_answers = input("[REPL] Введите ответы (или 'ок' для старта): ").strip()
        
        if user_answers.lower() in ['ok', 'ок', 'go']:
            detected_mode = "APPEND" if current_todo_content else "PLAN"
            break
            
        dialog_history += f"Model Questions:\n{analysis}\nUser Answers:\n{user_answers}\n"
        current_input = f"User clarifications: {user_answers}"

    structure = core.get_project_structure(WORKSPACE_ROOT, TODO_FILE)
    planner_success = skill_planner.run_planner_mode(
        OLLAMA_URL, MODEL_PLANNER, SYSTEM_PROMPT_PLANNER, dialog_history, TODO_PATH, structure, mode=detected_mode
    )
    if not planner_success: 
        print("[Движок] Ошибка на этапе генерации плана."); return

    with open(TODO_PATH, 'r', encoding='utf-8') as f:
        final_todo = f.read()
        
    skill_coder.run_coder_mode(
        OLLAMA_URL, MODEL_CODER, SYSTEM_PROMPT_CODER, final_todo, WORKSPACE_ROOT, TODO_FILE
    )

def main():
    init_ollama_cuda()
    print("=== Модульный ИИ-Агент с инкрементальной памятью запущен ===")
    print("Для выхода напишите 'exit'\n")
    
    try:
        while True:
            user_idea = input("\n[REPL] Введите вашу идею/доработку: ").strip()
            if not user_idea: continue
            if user_idea.lower() == 'exit': 
                print("[Движок] Сессия закрыта.")
                break
            run_pipeline(user_idea)
            print("\n================ ЦИКЛ ЗАВЕРШЕН ================")
    except KeyboardInterrupt: 
        print("\n[Движок] Принудительный выход.")
    finally:
        print("[Движок] Завершение работы фоновых серверов...")
        if sys.platform == "win32": subprocess.run("taskkill /f /im ollama.exe 2>nul", shell=True)
        else: subprocess.run("pkill -f ollama 2>/dev/null", shell=True)

if __name__ == "__main__":
    main()
