"""Phase F scheduling wrapper; shared pinned inference is unchanged."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.research.score import worker

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('detector',choices=['desklib','vanguard'])
    p.add_argument('--shard',type=int,default=0);p.add_argument('--count',type=int,default=1)
    p.add_argument('--seconds',type=int,default=7200);p.add_argument('--drain',action='store_true');a=p.parse_args()
    worker(a.detector,a.shard,a.count,a.seconds,phase='F',drain=a.drain)
