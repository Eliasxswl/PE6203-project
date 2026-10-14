"""Start 1mcp with absolute config paths on Windows and macOS."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', default='smoke')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--port', type=int, default=3050)
    args = parser.parse_args()
    config = args.config.resolve() if args.config else ROOT / 'config/local' / f'{args.stage}.json'
    if not config.is_file():
        parser.error(f'Missing config: {config}')
    command = ['node', str(ROOT / '.runtime/node_modules/@1mcp/agent/build/index.js'),
               'serve', '--host', '127.0.0.1', '--port', str(args.port),
               '--config', str(config), '--config-dir', str(config.parent)]
    raise SystemExit(subprocess.call(command, cwd=ROOT))

if __name__ == '__main__':
    main()
