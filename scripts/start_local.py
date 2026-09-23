"""Start a local single-user API, worker and functional UI; no cloud deployment.

Exits on occupied ports. Does not kill other services or retry model requests.
"""
import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import secrets

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--api-port',type=int,default=8011)
    parser.add_argument('--web-port',type=int,default=3011)
    parser.add_argument('--admin-port',type=int,default=3021)
    args=parser.parse_args()
    if len({args.api_port,args.web_port,args.admin_port}) != 3:
        parser.error('API, product and internal console ports must be different')
    for port in [args.api_port,args.web_port,args.admin_port]:
        if not 1024<=port<=65535:
            parser.error('Ports must be 1024..65535')
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',port))==0:
                parser.error(f'Port {port} is occupied; existing service was not stopped')
    npm=shutil.which('npm')
    if not npm or not (ROOT/'frontend/node_modules').is_dir():
        parser.error('Install frontend dependencies first')
    token_file=ROOT/'runtime_logs/local-admin.key'
    token_file.parent.mkdir(parents=True,exist_ok=True)
    if token_file.is_symlink():
        parser.error('Admin key path must not be a symlink')
    if not token_file.exists():
        # Runtime credential, never source code or a public environment variable.
        with open(token_file,'x',opener=lambda p,f:os.open(p,f,0o600)) as handle:
            handle.write(secrets.token_urlsafe(36))
    token_file.chmod(0o600)
    admin_token=token_file.read_text().strip()
    if len(admin_token)<32:
        parser.error('Admin key must contain at least 32 characters')
    env={**os.environ,'PYTHONPATH':str(ROOT/'backend'),
         'ADMIN_API_TOKEN':admin_token,
         'ALLOWED_ORIGINS':f'http://127.0.0.1:{args.web_port},http://localhost:{args.web_port}'}
    web_env={**{k:v for k,v in env.items() if k!='ADMIN_API_TOKEN'},
             'TUANHUI_ADMIN_ENABLED':'0','NEXT_BUILD_DIR':'.next-local',
             'NEXT_PUBLIC_API_BASE':f'http://127.0.0.1:{args.api_port}/api/v1',
             'NEXT_PUBLIC_PRODUCT_ORIGIN':f'http://127.0.0.1:{args.web_port}'}
    # Build once: two dev servers would concurrently rewrite shared TS config.
    subprocess.run([npm,'run','build'],cwd=ROOT/'frontend',env=web_env,check=True)
    children=[]
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:
        children.append(subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(args.api_port)],cwd=ROOT,env=env,start_new_session=True))
        # API bootstraps additive local tables before the worker starts.
        import urllib.request
        for _ in range(40):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{args.api_port}/health',timeout=1)
                break
            except OSError:
                if children[0].poll() is not None:
                    raise RuntimeError('API failed to start')
                time.sleep(.25)
        else:
            raise RuntimeError('API readiness timed out')
        children.append(subprocess.Popen([sys.executable,'-m','app.worker'],cwd=ROOT,env=env,start_new_session=True))
        children.append(subprocess.Popen([npm,'run','start','--','--hostname','127.0.0.1','--port',str(args.web_port)],cwd=ROOT/'frontend',env=web_env,start_new_session=True))
        children.append(subprocess.Popen([npm,'run','start','--','--hostname','127.0.0.1','--port',str(args.admin_port)],cwd=ROOT/'frontend',
            env={**web_env,'ADMIN_API_TOKEN':admin_token,'TUANHUI_ADMIN_ENABLED':'1',
                 'ADMIN_API_BASE':f'http://127.0.0.1:{args.api_port}/api/v1'},start_new_session=True))
        print(f'Product: http://127.0.0.1:{args.web_port}/',flush=True)
        print(f'Internal console: http://127.0.0.1:{args.admin_port}/workbench',flush=True)
        print(f'Admin username: admin; password file (local only): {token_file}',flush=True)
        print('Local single-user only. Ctrl+C stops these child processes; paid requests are never replayed.',flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in children:
            try:
                os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError:
                pass
        for p in children:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL)


if __name__=='__main__':
    main()
