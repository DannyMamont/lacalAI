import os
import subprocess
import re

# Глобальное описание инструментов (схемы для Ollama API)
OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Executes ANY bash/terminal command in the workspace root. Use this to create files, overwrite files, apply patches, run tests, or install packages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The exact command to run in the terminal (e.g., 'python -c ...' or 'pytest')."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_chunk",
            "description": "Reads a specific file from the workspace root to inspect its content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "The relative path to the file from the workspace root."
                    }
                },
                "required": ["relative_path"]
            }
        }
    }
]

def get_project_structure(workspace_root, todo_file):
    structure = []
    ignore_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.vscode', '.agentsSettings'}
    try:
        for root, dirs, files in os.walk(workspace_root):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, workspace_root)
                if rel_path != todo_file and rel_path != "patch_tool.py":
                    structure.append(rel_path)
    except Exception as e:
        print(f"[Движок] Ошибка сканирования директории: {e}")
    return "\n".join(structure) if structure else "[Workspace is empty]"

def execute_tool_call(tool_call, workspace_root):
    """
    Принимает структурированный вызов инструмента от Ollama,
    выполняет его и возвращает честный системный ответ.
    """
    func_name = tool_call.get("function", {}).get("name")
    arguments = tool_call.get("function", {}).get("arguments", {})
    
    if func_name == "run_terminal_command":
        command = arguments.get("command", "").strip()
        print(f"\n[Движок -> Вызов Инструмента ГП]: Запуск команды: {command}")
        try:
            result = subprocess.run(
                command, shell=True, cwd=workspace_root, 
                capture_output=True, text=True, timeout=45, 
                encoding='utf-8', errors='ignore'
            )
            # Честно собираем и stdout, и stderr, чтобы модель видела всё, что произошло в консоли
            output = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}".strip()
            return f"[Terminal Execution Result]:\n{output if output else '[Command executed successfully with no output text]'}"
        except subprocess.TimeoutExpired:
            return "[Terminal Error]: Command execution timed out after 45 seconds."
        except Exception as e:
            return f"[Terminal Error]: Failed to execute terminal action: {e}"
            
    elif func_name == "read_file_chunk":
        rel_path = arguments.get("relative_path", "").strip().lstrip("./\\")
        target_path = os.path.normpath(os.path.join(workspace_root, rel_path))
        print(f"\n[Движок] Чтение файла: {rel_path}")
        
        if os.path.exists(target_path):
            try:
                with open(target_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return f"[Content of file '{rel_path}']:\n```\n{content}\n```"
            except Exception as e:
                return f"[Error reading file]: {e}"
        return f"[Error]: File '{rel_path}' not found in workspace."
        
    return f"[Error]: Unknown tool function name '{func_name}'."


    """
    Парсит ответ модели. Находит блоки <WRITE_FILE> и сохраняет их на диск.
    Если есть маркер RUN:, выполняет команду в терминале.
    """
    output_log = []
    
    # 1. Ищем блоки для записи файлов: <WRITE_FILE path="path">content</WRITE_FILE>
    # Флаг re.DOTALL позволяет точке . матчить переносы строк
    file_blocks = re.findall(r'<WRITE_FILE\s+path=["\'](.*?)["\']>(.*?)</WRITE_FILE>', response_text, re.DOTALL)
    
    for rel_path, content in file_blocks:
        rel_path = rel_path.strip().lstrip("./\\")
        target_path = os.path.normpath(os.path.join(workspace_root, rel_path))
        
        # Защита: проверяем, что файл пишется внутри workspace
        if not target_path.startswith(os.path.normpath(workspace_root)):
            output_log.append(f"[Ошибка безопасности]: Попытка записи за пределы workspace: {rel_path}")
            continue
            
        try:
            # Создаем родительские папки, если их нет (mkdir -p)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            
            # Записываем контент (убираем лишние начальные/конечные пустые строки)
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(content.strip('\n'))
                
            print(f"\n[Движок -> Успех]: Файл успешно записан: {rel_path}")
            output_log.append(f"[Success]: File written successfully at '{rel_path}'")
        except Exception as e:
            output_log.append(f"[Error]: Failed to write file '{rel_path}': {e}")

    # 2. Обрабатываем стандартный RUN: для терминала (если он есть)
    if "RUN:" in response_text:
        command = response_text.split("RUN:")[-1].strip().split("\n")[0].strip()
        if command:
            print(f"\n[Движок -> Терминал]: Запуск команды: {command}")
            try:
                result = subprocess.run(
                    command, shell=True, cwd=workspace_root,
                    capture_output=True, text=True, timeout=45,
                    encoding='utf-8', errors='ignore'
                )
                terminal_out = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}".strip()
                output_log.append(f"[Terminal Execution Result]:\n{terminal_out if terminal_out else '[Executed with no output]'}")
            except Exception as e:
                output_log.append(f"[Terminal Error]: {e}")

    # Возвращаем накопленный результат работы для памяти модели
    return "\n".join(output_log) if output_log else None

def execute_command(response_text, workspace_root):
    output_log = []
    file_written = False
    
    # 1. Запись файлов (<WRITE_FILE>)
    file_blocks = re.findall(r'<WRITE_FILE\s+path=["\'](.*?)["\']>(.*?)</WRITE_FILE>', response_text, re.DOTALL)
    for rel_path, content in file_blocks:
        rel_path = rel_path.strip().lstrip("./\\")
        target_path = os.path.normpath(os.path.join(workspace_root, rel_path))
        
        if not target_path.startswith(os.path.normpath(workspace_root)):
            output_log.append(f"[Ошибка безопасности]: {rel_path}")
            continue
            
        try:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(content.strip('\n'))
            print(f"\n[Движок -> Успех]: Файл записан: {rel_path}")
            output_log.append(f"[Success]: File written successfully at '{rel_path}'")
            file_written = True # Фиксируем, что работа сделана
        except Exception as e:
            output_log.append(f"[Error]: Failed to write file '{rel_path}': {e}")

    # 2. Обработка RUN:
    command_executed = False
    if "RUN:" in response_text:
        command = response_text.split("RUN:")[-1].strip().split("\n")[0].strip()
        if any(x in command.lower() for x in ["runserver", "npm start", "yarn start", "nodemon"]):
            return f"[System Notice]: Command '{command}' was blocked. Use tests only."
            
        if command:
            print(f"\n[Движок -> Терминал]: Запуск: {command}")
            try:
                result = subprocess.run(command, shell=True, cwd=workspace_root, capture_output=True, text=True, timeout=15, encoding='utf-8', errors='ignore')
                output_log.append(f"[Terminal Result]:\n{result.stdout}\n{result.stderr}")
                command_executed = True
            except Exception as e:
                output_log.append(f"[Terminal Error]: {e}")

    # 3. АВТО-ОБНОВЛЕНИЕ TODO.MD (Продвижение по шагам)
    # Если кодер успешно записал файл или выполнил команду, отмечаем текущий шаг выполненным
    if file_written or command_executed:
        todo_path = os.path.join(workspace_root, "TODO.md")
        if os.path.exists(todo_path):
            try:
                with open(todo_path, 'r', encoding='utf-8') as f:
                    todo_content = f.read()
                
                # Ищем первый попавшийся невыполненный пункт: например, "- [ ] Сделать X" или "- Изменить Y"
                # Заменяем его на выполненный "- [x] ..."
                lines = todo_content.splitlines()
                updated = False
                for i, line in enumerate(lines):
                    # Проверяем маркеры "- [ ]" или просто списки "- ", которые еще не отмечены [x]
                    if (line.strip().startswith("- [ ]") or (line.strip().startswith("- ") and not "[x]" in line.lower())) and not updated:
                        if "[ ]" in line:
                            lines[i] = line.replace("[ ]", "[x]")
                        else:
                            lines[i] = line.replace("- ", "- [x] ")
                        updated = True
                        break
                
                if updated:
                    with open(todo_path, 'w', encoding='utf-8') as f:
                        f.write("\n".join(lines))
                    print("[Движок -> TODO]: План обновлен. Текущий шаг отмечен как выполненный [x].")
                    output_log.append("[System]: TODO.md has been automatically updated. Step marked as COMPLETED.")
            except Exception as e:
                print(f"[Ошибка обновления TODO]: {e}")

    return "\n".join(output_log) if output_log else None