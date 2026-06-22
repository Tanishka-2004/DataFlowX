import os
import importlib.util
import sys

def validate_imports(directory):
    success = True
    for root, _, files in os.walk(directory):
        if "venv" in root or "__pycache__" in root or ".pytest_cache" in root:
            continue
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                module_name = file[:-3]
                
                # Setup path so it acts like a real import
                sys.path.insert(0, root)
                sys.path.insert(0, directory) # Add project root
                
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                try:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    print(f"OK: {file_path}")
                except Exception as e:
                    print(f"ERROR in {file_path}: {type(e).__name__} - {e}")
                    success = False
                
                sys.path.pop(0)
                sys.path.pop(0)
    return success

if __name__ == "__main__":
    import sys
    success = validate_imports(os.getcwd())
    if not success:
        sys.exit(1)
