#!/usr/bin/env python3
import os, sys, subprocess, time

sys.stdout.reconfigure(encoding='utf-8')

def main():
    print("\n[SYSTEM] Initiating Cache Destruction Protocol (Purge Sequence)...")
    
    images_to_delete = ["cvat-yolo-base", "cvat-deployer"]
    
    for img in images_to_delete:
        print(f"  [+] Purging foundational matrix: {img}...")
        subprocess.run(f'docker rmi -f {img}', shell=True, capture_output=True, encoding='utf-8')
        
    print("[SYSTEM] Sweeping residual fragmented layers (Dangling images)...")
    subprocess.run('docker image prune -f', shell=True, capture_output=True, encoding='utf-8')
    
    print("[SYSTEM] STORAGE VECTORS COMPLETELY FREED. Protocol terminated.")
    time.sleep(1)

if __name__ == "__main__":
    main()
