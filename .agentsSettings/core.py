import os
import subprocess

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
