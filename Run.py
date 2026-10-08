#!/usr/bin/env python3
import os, sys, subprocess, shutil, json, glob, re, time

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
BUILD_DIR = os.path.join(BASE_DIR, ".build")
TORCH_WHEEL_NAME = "torch-2.1.2+cpu-cp310-cp310-linux_x86_64.whl"
TORCH_WHEEL_PATH = os.path.join(BASE_DIR, TORCH_WHEEL_NAME)
NUCTL_VERSION = "1.13.0"

def main():
    print(f"\n[SYSTEM] Initializing State Synchronization Module...")
    os.makedirs(MODELS_DIR, exist_ok=True)
    local_files = glob.glob(os.path.join(MODELS_DIR, "*.onnx"))
    local_models = {sanitize_name(f): f for f in local_files}
    print(f"[SYSTEM] Scanned local armory: {len(local_models)} payload(s) detected.")
    
    print(f"[SYSTEM] Pinging Nuclio orchestrator...")
    deployed = get_deployed_functions()
    
    to_delete = set(deployed.keys()) - set(local_models.keys())
    to_deploy = set(local_models.keys()) - set(deployed.keys())
    
    if not to_delete and not to_deploy:
        print("[SYSTEM] 100% SYNC ALIGNED. No mutations detected. Terminating...")
        sys.exit(0)
    
    if to_delete:
        print(f"[WARNING] {len(to_delete)} payload(s) untracked. Initiating purge sequence...")
        for name in to_delete:
            print(f"  [+] Purging entity: {name}...")
            delete_function(name)
        print("[SYSTEM] Rebooting Core Engine...")
        subprocess.run('docker restart nuclio', shell=True, capture_output=True, encoding='utf-8')
        time.sleep(3)
        print("[SYSTEM] Purge sequence completed.")
        
    if to_deploy:
        print(f"[SYSTEM] {len(to_deploy)} new payload(s) detected. Engaging launch protocol...")
        
        # 1. Prepare Base Image (Only takes time ONCE)
        prepare_base_image()
        
        # 2. Prepare Deployer Image (Only takes time ONCE)
        prepare_deployer_image()

        if os.path.exists(BUILD_DIR):
            shutil.rmtree(BUILD_DIR)
        os.makedirs(BUILD_DIR)
        
        for name in to_deploy:
            print(f"  [+] Injecting payload: {name}")
            prepare_build(local_models[name], name)
        
        print("[SYSTEM] Igniting Docker runtime (Hyper-Sync Mode)...")
        gen_deploy_script(to_deploy)
        success = run_docker()
        
        # Phi tang phòng chờ .build sau khi dùng xong
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
        
        if not success:
            print("[ERROR] DEPLOYMENT PROTOCOL FAILED!")
            sys.exit(1)
            
    print("[SYSTEM] PROTOCOL COMPLETE. RELOAD CVAT INTERFACE.")
    enable_cvat_serverless()
    print("[SUCCESS] You can now use the model in CVAT!")
    
    sys.exit(0)

def get_deployed_functions():
    r = subprocess.run('docker exec cvat_server curl -s http://nuclio:8070/api/functions', shell=True, capture_output=True, text=True, encoding='utf-8')
    try:
        return {n: v.get("status", {}).get("state", "?") for n, v in json.loads(r.stdout).items()}
    except Exception:
        return {}

def delete_function(name):
    subprocess.run(f'docker rm -f nuclio-nuclio-{name}', shell=True, capture_output=True, encoding='utf-8')
    subprocess.run(f'docker run --rm -v nuclio-local-storage:/data alpine sh -c "rm -f /data/functions/nuclio/{name}.json"', shell=True, capture_output=True, encoding='utf-8')

def scan_models():
    os.makedirs(MODELS_DIR, exist_ok=True)
    return sorted(glob.glob(os.path.join(MODELS_DIR, "*.pt")))

def sanitize_name(filepath):
    name = os.path.splitext(os.path.basename(filepath))[0]
    name = re.sub(r'[^a-zA-Z0-9]', '-', name)
    return re.sub(r'-+', '-', name).strip('-').lower() or "model"

def extract_labels(model_path):
    try:
        from ultralytics import YOLO
        m = YOLO(model_path)
        return [{"id": k, "name": v, "type": "rectangle"} for k, v in m.names.items()]
    except Exception:
        pass
    return [{"id": 0, "name": "object", "type": "rectangle"}]

def prepare_build(model_path, func_name):
    display = os.path.splitext(os.path.basename(model_path))[0]
    build_dir = os.path.join(BUILD_DIR, func_name)
    os.makedirs(build_dir)

    shutil.copy(model_path, os.path.join(build_dir, "best.onnx"))

    labels = extract_labels(model_path)
    spec_json = json.dumps(labels, ensure_ascii=False)

    write_file(os.path.join(build_dir, "main.py"), MAIN_PY_TEMPLATE)
    write_file(os.path.join(build_dir, "function.yaml"), FUNCTION_YAML_TEMPLATE.format(
        func_name=func_name, display_name=display, spec_json=spec_json))

def gen_deploy_script(func_names):
    deploy_cmds = ""
    for name in func_names:
        deploy_cmds += f"""
nuctl delete function {name} --platform local 2>/dev/null || true
nuctl deploy --project-name cvat \\
    --path /workspace/.build/{name} \\
    --platform local \\
    --env CVAT_FUNCTIONS_REDIS_HOST=cvat_redis_ondisk \\
    --env CVAT_FUNCTIONS_REDIS_PORT=6666 \\
    --platform-config '{{"attributes": {{"network": "cvat_cvat"}}}}'
"""
    write_file(os.path.join(BUILD_DIR, "deploy_all.sh"),
               DEPLOY_SH_TEMPLATE.format(deploy_commands=deploy_cmds),
               newline='\n')

def run_docker():
    base_unix = BASE_DIR.replace("\\", "/")
    cmd = (f'docker run --rm --dns 8.8.8.8 '
           f'-v //var/run/docker.sock:/var/run/docker.sock '
           f'-v "{base_unix}:/workspace" '
           f'cvat-deployer:latest bash /workspace/.build/deploy_all.sh')
    proc = subprocess.Popen(cmd, shell=True)
    proc.wait()
    return proc.returncode == 0

def prepare_base_image():
    r = subprocess.run('docker image inspect cvat-onnx-base', shell=True, capture_output=True, encoding='utf-8')
    if r.returncode == 0:
        return
    print("[SYSTEM] Assembling foundational matrix (cvat-onnx-base). ETA: 3 mins (One-time operation)...")
    
    if os.path.exists(TORCH_WHEEL_PATH):
        torch_install = f"COPY {TORCH_WHEEL_NAME} /tmp/\nRUN pip3 install --no-cache-dir /tmp/{TORCH_WHEEL_NAME} && rm /tmp/{TORCH_WHEEL_NAME}"
    else:
        torch_install = "RUN pip3 install --no-cache-dir torch==2.1.2+cpu -f https://download.pytorch.org/whl/torch_stable.html"
        
    dockerfile = f"""FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 python3 python3-pip python-is-python3 && rm -rf /var/lib/apt/lists/*
{torch_install}
RUN pip3 install --no-cache-dir ultralytics opencv-python-headless onnxruntime --extra-index-url https://download.pytorch.org/whl/cpu
"""
    tmp_dir = os.path.join(BASE_DIR, ".base_build")
    os.makedirs(tmp_dir, exist_ok=True)
    write_file(os.path.join(tmp_dir, "Dockerfile"), dockerfile)
    shutil.copy(TORCH_WHEEL_PATH, os.path.join(tmp_dir, TORCH_WHEEL_NAME))
    subprocess.run(f'docker build -t cvat-yolo-base "{tmp_dir}"', shell=True)
    shutil.rmtree(tmp_dir, ignore_errors=True)

def prepare_deployer_image():
    r = subprocess.run('docker image inspect cvat-deployer', shell=True, capture_output=True, encoding='utf-8')
    if r.returncode == 0:
        return
    print("[SYSTEM] Constructing deployment vessel (cvat-deployer). One-time operation...")
    dockerfile = f"""FROM ubuntu:22.04
RUN apt-get update -qq && apt-get install -y wget docker.io -qq
RUN wget -qO /usr/local/bin/nuctl https://github.com/nuclio/nuclio/releases/download/{NUCTL_VERSION}/nuctl-{NUCTL_VERSION}-linux-amd64 && chmod +x /usr/local/bin/nuctl
"""
    tmp_dir = os.path.join(BASE_DIR, ".deployer_build")
    os.makedirs(tmp_dir, exist_ok=True)
    write_file(os.path.join(tmp_dir, "Dockerfile"), dockerfile)
    subprocess.run(f'docker build -t cvat-deployer "{tmp_dir}"', shell=True)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    
    # Fix alpine just in case during setup
    try:
        r = subprocess.run('docker image inspect gcr.io/iguazio/alpine:3.17', shell=True, capture_output=True, encoding='utf-8')
        if r.returncode != 0:
            subprocess.run('docker pull alpine:3.17', shell=True)
            subprocess.run('docker tag alpine:3.17 gcr.io/iguazio/alpine:3.17', shell=True)
    except Exception:
        pass

def write_file(path, content, newline=None):
    kw = {"encoding": "utf-8"}
    if newline: kw["newline"] = newline
    with open(path, "w", **kw) as f: f.write(content)

MAIN_PY_TEMPLATE = r'''import json, base64, io
from PIL import Image
from ultralytics import YOLO

def init_context(context):
    model = YOLO("/opt/nuclio/best.onnx")
    context.user_data.model = model
    context.user_data.names = model.names

def handler(context, event):
    data = event.body
    buf = io.BytesIO(base64.b64decode(data["image"]))
    image = Image.open(buf).convert("RGB")
    threshold = float(data.get("threshold", 0.1))
    results = context.user_data.model(image, verbose=False)
    detections = []
    for r in results:
        for box in r.boxes:
            conf = float(box.conf[0])
            if conf < threshold: continue
            b = box.xyxy[0].tolist()
            cls_id = int(box.cls[0])
            detections.append({
                "confidence": str(conf),
                "label": context.user_data.names.get(cls_id, f"class_{cls_id}"),
                "points": [b[0], b[1], b[2], b[3]],
                "type": "rectangle",
            })
    return context.Response(body=json.dumps(detections), headers={},
                            content_type="application/json", status_code=200)
'''

FUNCTION_YAML_TEMPLATE = """metadata:
  name: {func_name}
  namespace: cvat
  annotations:
    name: {display_name}
    type: detector
    framework: pytorch
    spec: |
      {spec_json}

spec:
  description: "{display_name}"
  runtime: "python:3.9"
  handler: main:handler
  eventTimeout: 30s
  build:
    image: cvat.serverless.{func_name}
    baseImage: cvat-onnx-base
  triggers:
    myHttpTrigger:
      numWorkers: 1
      kind: 'http'
      workerAvailabilityTimeoutMilliseconds: 10000
      attributes:
        maxRequestBodySize: 33554432
"""

DEPLOY_SH_TEMPLATE = """#!/bin/bash
nuctl create project cvat --platform local || true
{deploy_commands}
"""

def enable_cvat_serverless():
    print("\n[SYSTEM] Checking if CVAT AI/Serverless mode is enabled...")
    r = subprocess.run('docker inspect cvat_server', shell=True, capture_output=True, encoding='utf-8')
    if r.returncode != 0:
        print("  [-] CVAT is not running. Please start CVAT manually first.")
        return
        
    try:
        data = json.loads(r.stdout)
        working_dir = data[0]['Config']['Labels']['com.docker.compose.project.working_dir']
    except Exception:
        print("  [-] Could not auto-detect CVAT directory.")
        return
        
    print(f"  [+] Found CVAT installation at: {working_dir}")
    print("  [+] Injecting Serverless modules and rebooting CVAT (this is safe)...")
    
    compose_cmd = 'docker compose -f docker-compose.yml -f components/serverless/docker-compose.serverless.yml up -d'
    subprocess.run(compose_cmd, shell=True, cwd=working_dir)
    print("  [+] CVAT AI/Serverless mode is now ONLINE!")

if __name__ == "__main__":
    main()
