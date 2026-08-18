#!/usr/bin/env python3
from __future__ import annotations
import json, os, signal, subprocess, sys, time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path("/workspaces/TechScope")
RG = "rg-techscope-dev-239bd206"
SEARCH_SERVICE = "srch-techscope-dev-239bd206-b1"
SEARCH_INDEX = "techscope-chunks"
OPENAI_ACCOUNT = "aoai-techscope-dev-239bd206"
GENERATION_DEPLOYMENT = "techscope-gpt-4-1-mini"
EMBEDDING_DEPLOYMENT = "techscope-embedding-3-small"
LOG = Path("/tmp/techscope-p3b-clean-v7-fastapi.log")

def run(cmd, check=True, timeout=90, env=None):
    cp = subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True,
                        check=False, timeout=timeout)
    if check and cp.returncode != 0:
        raise RuntimeError("COMMAND_FAILED\n" + " ".join(cmd) +
                           "\nSTDOUT:\n" + (cp.stdout or "")[-4000:] +
                           "\nSTDERR:\n" + (cp.stderr or "")[-4000:])
    return cp

def az_tsv(args):
    return run(["az", *args, "-o", "tsv", "--only-show-errors"]).stdout.strip()

def get_json(url, timeout=5):
    with urlopen(Request(url, method="GET"), timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))

def ready():
    try:
        h,_ = get_json("http://127.0.0.1:8000/health")
        c,cosmos = get_json("http://127.0.0.1:8000/demo/cosmos-runtime")
        g,grounding = get_json("http://127.0.0.1:8000/demo/grounding-runtime")
        return (h == 200 and c == 200 and cosmos.get("version") == "p3a2-v1"
                and cosmos.get("data_plane") is True and g == 200
                and grounding.get("version") == "v6"
                and grounding.get("ask_guard_wrapped") is True)
    except Exception:
        return False

def proc_cmd(pid):
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return " ".join(x.decode("utf-8", "ignore") for x in raw.split(b"\0") if x)
    except Exception:
        return ""

def uvicorn_pids():
    out=[]
    for p in Path("/proc").iterdir():
        if not p.name.isdigit(): continue
        pid=int(p.name); cmd=proc_cmd(pid)
        if "uvicorn" in cmd.lower() and "backend.app.main" in cmd.lower():
            toks=cmd.split(); port=8000
            for i,t in enumerate(toks):
                if t=="--port" and i+1<len(toks):
                    try: port=int(toks[i+1])
                    except: pass
            if port==8000: out.append(pid)
    return out

def build_env():
    if run(["az","account","show","-o","none"], check=False, timeout=30).returncode != 0:
        raise RuntimeError("AZURE_LOGIN_REQUIRED_IN_CONTAINER")
    endpoint = az_tsv(["cognitiveservices","account","show",
                       "--name",OPENAI_ACCOUNT,"--resource-group",RG,
                       "--query","properties.endpoint"])
    if not endpoint:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT_RECOVERY_FAIL")
    env=os.environ.copy()
    env["TECHSCOPE_SEARCH_ENDPOINT"]=f"https://{SEARCH_SERVICE}.search.windows.net"
    env["TECHSCOPE_SEARCH_INDEX"]=SEARCH_INDEX
    env["TECHSCOPE_AZURE_OPENAI_ENDPOINT"]=endpoint
    env["TECHSCOPE_GENERATION_DEPLOYMENT"]=GENERATION_DEPLOYMENT
    env["TECHSCOPE_EMBEDDING_DEPLOYMENT"]=EMBEDDING_DEPLOYMENT
    print("RUNTIME_ENV_RECOVERY=PASS", flush=True)
    print("RUNTIME_SECRET_VALUES_PRINTED=NO", flush=True)
    print("RUNTIME_SECRET_VALUES_PERSISTED=NO", flush=True)
    return env

def stop_stale():
    pids=uvicorn_pids()
    if not pids:
        print("STALE_UVICORN_8000=NONE", flush=True); return
    for pid in pids:
        if pid==1: raise RuntimeError("UVICORN_PID_1_SAFE_STOP")
        try: os.kill(pid, signal.SIGTERM)
        except ProcessLookupError: pass
    end=time.monotonic()+15
    while time.monotonic()<end:
        if not uvicorn_pids():
            print("STALE_UVICORN_8000=STOPPED", flush=True); return
        time.sleep(1)
    raise RuntimeError("STALE_UVICORN_STOP_TIMEOUT")

def start_backend(env):
    LOG.unlink(missing_ok=True)
    log=LOG.open("a", encoding="utf-8")
    p=subprocess.Popen([sys.executable,"-m","uvicorn","backend.app.main:app",
                        "--host","0.0.0.0","--port","8000"],
                       cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                       start_new_session=True, text=True)
    end=time.monotonic()+120
    while time.monotonic()<end:
        if p.poll() is not None:
            log.flush()
            txt=LOG.read_text("utf-8","ignore") if LOG.exists() else ""
            raise RuntimeError(f"FASTAPI_PROCESS_EXITED rc={p.returncode}\n{txt[-6000:]}")
        if ready():
            print(f"FASTAPI_RECOVERY_PID={p.pid}", flush=True)
            print("FASTAPI_INTERNAL_HEALTH=PASS", flush=True)
            print("COSMOS_RUNTIME=PASS p3a2-v1", flush=True)
            print("GROUNDING_RUNTIME=PASS v6", flush=True)
            return
        time.sleep(2)
    txt=LOG.read_text("utf-8","ignore") if LOG.exists() else ""
    raise RuntimeError("FASTAPI_RECOVERY_TIMEOUT\n"+txt[-6000:])

print("P3B_CLEAN_V7_BACKEND_RECOVERY=START", flush=True)
print("AI_ASK_CALLS=0", flush=True)
print("AZURE_RESOURCE_MUTATION=NO", flush=True)
if ready():
    print("FASTAPI_INTERNAL=PASS_ALREADY_RUNNING", flush=True)
    print("P3B_CLEAN_V7_BACKEND_RECOVERY=PASS", flush=True)
    raise SystemExit(0)
env=build_env()
stop_stale()
start_backend(env)
if not ready():
    raise RuntimeError("FASTAPI_POST_RECOVERY_VERIFY_FAIL")
print("P3B_CLEAN_V7_BACKEND_RECOVERY=PASS", flush=True)
