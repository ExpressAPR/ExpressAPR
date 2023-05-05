import pathlib

D4J_PATH = [
    '/home/expapr-user/defects4j-2.0-1',
    '/home/expapr-user/defects4j-2.0-2',
    '/home/expapr-user/defects4j-2.0-3',
    '/home/expapr-user/defects4j-2.0-4',
    '/home/expapr-user/defects4j-2.0-5',
    '/home/expapr-user/defects4j-2.0-6',
    '/home/expapr-user/defects4j-2.0-7',
    '/home/expapr-user/defects4j-2.0-8',
]
N_WORKERS = 8

assert len(D4J_PATH)==len(set(D4J_PATH)), 'D4J_PATH must be unique!'
assert len(D4J_PATH)>=N_WORKERS, 'not enough D4J_PATH!'

for p in D4J_PATH:
    assert (pathlib.Path(p)/'framework/bin/defects4j').is_file(), f'{p} is not a defects4j installation path!'

for n in range(1, N_WORKERS+1):
    assert pathlib.Path(f'/sys/fs/cgroup/cpuset/expressapr-exp-{n}').is_dir(), f'cgroup #{n} not found. run ./init_cpuset.sh first!'