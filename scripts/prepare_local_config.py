"""Generate machine-specific configs without changing upstream server configs."""
import json
from pathlib import Path
import shutil
import os

def executable_path(command, project_root, platform_name=None):
    """Resolve tool launchers for the current OS, not another member's machine."""
    windows = (platform_name or os.name) == 'nt'
    suffix = '.exe' if windows else ''
    venv_bin = 'Scripts' if windows else 'bin'
    if command in ['uv', 'uvx']:
        local = project_root / '.venv' / venv_bin / (command + suffix)
        if local.is_file():
            return str(local)
    executable = command + '.cmd' if windows and command in ['npm', 'npx'] else command
    return shutil.which(executable) or command

def main():
    root = Path(__file__).resolve().parents[1]
    output = root / 'config' / 'local'
    output.mkdir(parents=True, exist_ok=True)
    replacements = {
        '/path/to/workspace/': root.as_posix() + '/',
        '/path/to/iter3-servers': (root/'servers/iter3_servers').as_posix(),
        '/path/to/iter5-servers': (root/'servers/iter5_servers').as_posix(),
    }
    def rewrite(value):
        if isinstance(value, str):
            for old, new in replacements.items():
                value = value.replace(old, new)
            return value
        if isinstance(value, list): return [rewrite(item) for item in value]
        if isinstance(value, dict): return {key: rewrite(item) for key, item in value.items()}
        return value
    for stage in ['original', 'iter3', 'iter5']:
        data = rewrite(json.loads((root/f'servers/1mcp_config/{stage}/mcp.json').read_text(encoding='utf-8')))
        middle = rewrite(json.loads((root/'servers/1mcp_config/iter3/mcp.json').read_text(encoding='utf-8')))
        for name, config in data['mcpServers'].items():
            if stage == 'original' and config.get('command') == 'npx':
                reference = middle['mcpServers'].get(name, {})
                if reference.get('command') == 'node' and reference.get('args'):
                    candidate = reference['args'][0].replace('/iter3_servers/', '/original_servers/')
                    if Path(candidate).is_file():
                        original_args = config.get('args', [])
                        package_index = next((i for i, value in enumerate(original_args) if not value.startswith('-')), None)
                        if package_index is not None:
                            config['command'] = shutil.which('node') or 'node'
                            config['args'] = [candidate] + original_args[package_index + 1:]
            if config.get('command') in ['npx', 'npm', 'uv', 'uvx']:
                config['command'] = executable_path(config['command'], root)
            config.setdefault('cwd', str(root))
        (output/f'{stage}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'{stage}: wrote {len(data["mcpServers"])} server entries')
        entry = root / 'servers' / f'{stage}_servers' / 'node_modules/@modelcontextprotocol/server-sequential-thinking/dist/index.js'
        if entry.is_file():
            smoke = {'mcpServers': {'sequential-thinking': {'command': shutil.which('node') or 'node', 'args': [str(entry)], 'cwd': str(root)}}}
            smoke_name = 'smoke' if stage == 'original' else f'smoke-{stage}'
            (output/f'{smoke_name}.json').write_text(json.dumps(smoke, indent=2), encoding='utf-8')


if __name__ == "__main__":
    main()
