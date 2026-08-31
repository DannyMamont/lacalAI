import os
import sys
import json
import requests
import systemPromts as s
import core

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_PLANNER = "llama3.2:3b"
MODEL_CODER = "qwen2.5-coder:3b-instruct-q8_0"
TODO_FILE = "TODO.md"

SYSTEM_PROMPT_PLANNER = s.SYSTEM_PROMPT_PLANNER
SYSTEM_PROMPT_CODER = s.SYSTEM_PROMPT_CODER

# Вычисление путей
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TODO_PATH = os.path.join(WORKSPACE_ROOT, TODO_FILE)

def ask_ollama_stream(model_name, system_prompt, user_prompt, context_history=""):
    full_prompt = (
        f"### SYSTEM INSTRUCTIONS (MANDATORY):\n{system_prompt}\n\n"
        f"### CONTEXT HISTORY:\n{context_history}\n\n"
        f"### CURRENT TASK:\n{user_prompt}\n\n"
        f"REMEMBER: You must ALWAYS use @@@WRITE, @@@READ, or @@@MODIFY to impact files!"
    )
    payload = {
        "model": model_name,
        "prompt": full_prompt,
        "stream": True,
        "options": {"temperature": 0.1, "num_ctx": 4048}
    }
    full_response = ""
    try:
        response = requests.post(OLLAMA_URL, json=payload, stream=True)
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line.decode('utf-8'))
                text = chunk.get("response", "")
                full_response += text
                sys.stdout.write(text)
                sys.stdout.flush()
        print()
        return full_response
    except Exception as e:
        print(f"\n[Ошибка Ollama]: {e}")
        return ""

def run_pipeline(user_idea):
    print("\n================ STEP 1: PLANNING (Llama) ================")
    structure = core.get_project_structure(WORKSPACE_ROOT, TODO_FILE)
    print(f"[Движок] Текущая структура папки проекта:\n{structure}\n")
    
    print("[Llama] Составляет план (TODO.md)...")
    todo_content = ask_ollama_stream(MODEL_PLANNER, SYSTEM_PROMPT_PLANNER, f"Workspace structure:\n{structure}\n\nIdea: {user_idea}")
    if not todo_content: return

    with open(TODO_PATH, 'w', encoding='utf-8') as f:
        f.write(todo_content)
    print(f"\n[Движок] План зафиксирован в корне: {TODO_FILE}")

    while True:
        feedback = input("\n[Система] Внесите правки в ТЗ (или нажмите Enter/'ок' для старта): ").strip()
        if feedback.lower() in ['', 'ok', 'ок', 'go']: break
        
        print("\n[Llama] Перерабатывает ТЗ...")
        with open(TODO_PATH, 'r', encoding='utf-8') as f: current_todo = f.read()
        todo_content = ask_ollama_stream(MODEL_PLANNER, SYSTEM_PROMPT_PLANNER, f"Feedback: {feedback}\nUpdate TODO.md", context_history=current_todo)
        with open(TODO_PATH, 'w', encoding='utf-8') as f: f.write(todo_content)

    print("\n================ STEP 2: CODING (Qwen) ================")
    with open(TODO_PATH, 'r', encoding='utf-8') as f: final_todo = f.read()

    context_turns = []
    base_context = f"Project Structure:\n{core.get_project_structure(WORKSPACE_ROOT, TODO_FILE)}\n\nRequirements (TODO.md):\n{final_todo}\n"
    coder_prompt = "Execute the next step from TODO.md. Use file commands: @@@WRITE, @@@READ, or @@@MODIFY. Do NOT just dump code without system commands!"

    for turn in range(15):
        print(f"\n--- Итерация кодинга {turn + 1}/15 ---")
        active_history = "\n".join(context_turns[-3:]) if context_turns else ""
        current_context = f"{base_context}\nRecent Steps:\n{active_history}"
        
        response = ask_ollama_stream(MODEL_CODER, SYSTEM_PROMPT_CODER, coder_prompt, context_history=current_context)
        
        if "@@@DONE" in response:
            if turn < 4:
                print("\n[Движок] Слишком ранний выход. Принудительно возвращаю к ТЗ...")
                coder_prompt = "You said @@@DONE, but there are still incomplete parts in TODO.md. Review the requirements and continue writing code using commands!"
                continue
            print("\n[Движок] Qwen успешно завершила сессию кодинга.")
            break
            
        result = core.execute_command(response, WORKSPACE_ROOT)
        if result:
            print(result)
            context_turns.append(f"Turn {turn} Model Output:\n{response}\nSystem Output:\n{result}\n")
            coder_prompt = "Perfect. Analyze the result and execute the NEXT step from TODO.md using commands. If finished, output @@@DONE."
        else:
            print("\n[Внимание] Модель написала сырой текст без использования или с поломкой команд!")
            coder_prompt = "CRITICAL ERROR: Your last message contained NO valid file command or markdown was broken. You MUST format your response as @@@WRITE: path/file.txt followed by a code block, or @@@MODIFY. Do not write plain text code!"

def main():
    print("=== Автономный ИИ-Агент запущен ===")
    print(f"Рабочий корень проекта: {WORKSPACE_ROOT}")
    print("Для выхода напишите 'exit'\n")
    
    while True:
        try:
            user_idea = input("\n[REPL] Введите вашу сырую идею: ").strip()
            if not user_idea: continue
            if user_idea.lower() == 'exit':
                print("[Движок] Сессия закрыта.")
                break
            run_pipeline(user_idea)
            print("\n================ ЦИКЛ ЗАВЕРШЕН ================")
        except KeyboardInterrupt:
            print("\n[Движок] Выход.")
            break

if __name__ == "__main__":
    main()
