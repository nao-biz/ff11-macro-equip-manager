"""Run the unchanged real-data isolation harness with the opt-in candidate."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scoped_save import installed
from real_writeback import main

if __name__ == '__main__':
    with installed(): main()
