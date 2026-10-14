"""Prepare task 9 with local frozen tools and an isolated writable workspace."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from custom.utils.result_paths import run_directory

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    run = run_directory(stage='original', run_id=args.run_id)
    workspace = run / 'workspace'
    if (run / 'answers').exists() or (workspace / 'tasks.json').exists():
        parser.error('This run already has data. Choose a new run ID; existing results are preserved.')
    (workspace / 'txt').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'anotation_path/txt/log_yesterday.txt', workspace / 'txt/log_yesterday.txt')
    base = json.loads((ROOT / 'config/local/original.json').read_text(encoding='utf-8'))
    names = ['@modelcontextprotocol/server-filesystem', '@kazuph/mcp-taskmanager']
    servers = {name: base['mcpServers'][name] for name in names}
    for name, entry in servers.items():
        package = ROOT / 'servers/original_servers/node_modules' / name / 'dist/index.js'
        if not package.is_file():
            parser.error(f'Missing frozen tool: {package}')
        entry.update(command=shutil.which('node'), args=[package.as_posix()], cwd=workspace.as_posix())
    if not shutil.which('node'):
        parser.error('Node.js must be on PATH')
    servers[names[0]]['args'].append(workspace.as_posix())
    servers[names[1]].setdefault('env', {})['TASK_MANAGER_FILE_PATH'] = (workspace / 'tasks.json').as_posix()
    config = ROOT / 'config/local' / f'baseline-{args.run_id}' / 'mcp.json'
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({'mcpServers':servers}, indent=2), encoding='utf-8')
    print(f'Config: {config}\nWorkspace: {workspace}')

if __name__ == '__main__':
    main()
