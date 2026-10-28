"""Create the local CPython environment without changing system packages."""
import argparse,os,subprocess,sys,venv
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cpu-only',action='store_true');args=parser.parse_args()
    if os.name!='nt' or sys.version_info[:2]!=(3,12):raise SystemExit('Use native Windows CPython 3.12 with Tk support.')
    target=ROOT/'.venv';python=target/'Scripts/python.exe'
    if not python.exists():venv.EnvBuilder(with_pip=True).create(target)
    subprocess.run([str(python),'-m','pip','install','-r',str(ROOT/'requirements.txt')],check=True)
    subprocess.run([str(python),str(ROOT/'tools/install_engine.py')],check=True)
    if not args.cpu_only:
        subprocess.run([str(python),'-m','pip','install','--no-deps','--target',str(ROOT/'connector/gpu-runtime'),'onnxruntime-directml==1.24.4'],check=True)
    print('Setup complete. Open 启动斗牛犬.bat.')

if __name__=='__main__':main()
