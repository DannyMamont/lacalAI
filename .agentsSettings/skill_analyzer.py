import sys
import json
import requests

def run_analyzer_mode(ollama_url, model_name, user_idea, system_prompt, context_history, current_todo_content):
    """
    Анализирующий скилл. Защищен от бесконечных повторений строк (Repetition Penalty).
    """
    full_prompt = (
        f"### SYSTEM INSTRUCTIONS:\n{system_prompt}\n\n"
        f"### CURRENT EXISTING TODO.md:\n{current_todo_content if current_todo_content else '[None]'}\n\n"
        f"### DISCUSSION TURN HISTORY:\n{context_history}\n\n"
        f"### USER NEW INPUT:\n{user_idea}\n\n"
        "Critically analyze the input and output your response with the mandatory mode tag at the absolute end:"
    )

    payload = {
        "model": model_name, 
        "prompt": full_prompt, 
        "stream": True,
        "options": {
            "temperature": 0.3, 
            "num_ctx": 4048,
            "keep_alive": 0,
            # АНТИ-ЦИКЛ ПАРАМЕТРЫ:
            "repeat_penalty": 1.2,     # Запрещает модели повторять одинаковые фразы
            "frequency_penalty": 0.8,  # Штрафует за частое использование одних и тех же слов
            "presence_penalty": 0.5    # Стимулирует модель писать новые темы
        }
    }

    full_response = ""
    try:
        response = requests.post(ollama_url, json=payload, stream=True)
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
        print(f"\n[Скилл Анализа] Ошибка: {e}"); return ""
