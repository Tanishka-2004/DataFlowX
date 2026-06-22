import os

def get_stats():
    total_files = 0
    total_py_files = 0
    total_loc = 0
    
    for root, _, files in os.walk('.'):
        if 'venv' in root or '__pycache__' in root or '.git' in root or '.pytest_cache' in root:
            continue
        for file in files:
            total_files += 1
            if file.endswith('.py'):
                total_py_files += 1
            
            try:
                with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                    total_loc += sum(1 for _ in f)
            except Exception:
                pass
                
    print(f"Total Files: {total_files}")
    print(f"Total Python Files: {total_py_files}")
    print(f"Total Lines of Code: {total_loc}")

if __name__ == '__main__':
    get_stats()
