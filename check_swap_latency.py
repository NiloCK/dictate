#!/usr/bin/env python3
"""Measure how much having the model swapped out costs a transcription, and
whether the record-start prefetch hides it.

Usage (venv python, so faster-whisper is importable):
    /opt/dictation_venv/bin/python check_swap_latency.py [model] [--speak SECONDS]

Re-runs itself in its own transient systemd scope, so pushing memory to swap
(via the cgroup's memory.reclaim) only affects this process, never the daemon.
Decoding is pinned (greedy, no temperature fallback, capped tokens) so timings
reflect the encoder/weights cost rather than how chatty the decode was.
"""
import argparse
import os
import sys
import time

if os.environ.get('SWAP_BENCH_SCOPED') != '1':
    os.environ['SWAP_BENCH_SCOPED'] = '1'
    os.environ['XDG_CACHE_HOME'] = '/var/cache/whisper'  # the daemon's model cache (see dictation.service)
    os.execvp('systemd-run', ['systemd-run', '--user', '--scope', '-q',
                              sys.executable, os.path.abspath(__file__), *sys.argv[1:]])

import numpy as np
from faster_whisper import WhisperModel

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))
from dictation_daemon import prefetch_swapped_memory, swapped_mb
import logging
logging.getLogger().setLevel(logging.INFO)  # daemon module defaults to DEBUG
logging.getLogger('faster_whisper').setLevel(logging.WARNING)

parser = argparse.ArgumentParser()
parser.add_argument('model', nargs='?', default='base')
parser.add_argument('--speak', type=float, default=3.0,
                    help='simulated seconds of speaking between prefetch and transcription')
parser.add_argument('--rounds', type=int, default=3)
args = parser.parse_args()

CGROUP = '/sys/fs/cgroup' + open('/proc/self/cgroup').read().strip().split('::')[1]
DECODE = dict(language='en', temperature=0.0, beam_size=1, without_timestamps=True,
              max_new_tokens=10, condition_on_previous_text=False)
audio = (np.random.default_rng(0).standard_normal(16000 * 8) * 0.01).astype(np.float32)


def swap_out():
    try:
        with open(os.path.join(CGROUP, 'memory.reclaim'), 'w') as f:
            f.write('8G')
    except OSError:
        pass  # EAGAIN when it couldn't reclaim the full amount; whatever it got is fine
    return swapped_mb()


def transcribe():
    start = time.time()
    list(model.transcribe(audio, **DECODE)[0])
    return time.time() - start


print(f"model {args.model}, 8s clip, {args.rounds} rounds, simulated speaking {args.speak}s")
model = WhisperModel(args.model, device='auto', compute_type='int8', local_files_only=True)
transcribe()  # first call has one-off setup cost

results = {'warm': [], 'cold': [], 'cold + prefetch': []}
for i in range(args.rounds):
    results['warm'].append(transcribe())

    pushed = swap_out()
    results['cold'].append(transcribe())

    swap_out()
    prefetch_swapped_memory()
    time.sleep(args.speak)
    results['cold + prefetch'].append(transcribe())
    print(f"  round {i + 1}: pushed {pushed}MB to swap, {swapped_mb()}MB still swapped at end")

for label, times in results.items():
    print(f"{label:16} median {np.median(times):5.2f}s   runs: {' '.join(f'{t:.2f}' for t in times)}")
