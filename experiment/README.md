This folder contains the necessary files to reproduce the experiment.

Normal users don't need this unless you want to benchmark against baselines.



## Dependencies

- A Linux machine with at least 8 CPU cores
  - We tested on Ubuntu 20.04 and 16.04.
  - ***Why 8 cores?***
    In our experiment 8 workers are run in parallel, each using an exclusive core.
    If your machine doesn't have enough cores, change `N_WORKERS` in `runner/const.py`.
- JDK 1.8
  - `apt install openjdk-8-jdk`
- Python 3.7+
  - `apt install python3 python3-pip` (on Ubuntu 20.04)
- CGroup
  - `apt install cgroup-bin cgroup-tools`
- 8 copies of Defects4J
  - Follow [their setup instruction](https://github.com/rjust/defects4j) and copy the installed path to 8 locations.
  - ***Why 8 copies?***
    To compile runtime files, the script modifies classpath in `build.xml`, which is  located in the global Defects4J path.
    Therefore, Defects4J path should be distinct for each worker.
- UniAPR, as one of our baseline techniques
  - Follow [their setup instruction](https://github.com/lingming/UniAPR).
- Maven 3.3.9
  - We experienced issues with UniAPR on the latest Maven version (reported to UniAPR authors). Maven 3.3.9 seems fine.

## Reproducing the Experiment 

Extract collected candidate patches:
- `apt install p7zip-full`
- `cd apr_tools && 7za x collected_patches.7z && cd ..`

Execute the Plain and SOTA baseline:

- `cd runner && pip3 install -r requirements.txt`
- Edit `const.py`
  - Change `D4J_PATH` to your Defects4J installation path. 
- `./init_cpuset.sh`
- `./run_naive.sh`
  - Result will be saved to `res-out/<APR_NAME>-naive-uniform-res.csv`.
- `./run_uniapr.sh`
  - Result will be saved to `res-out/<APR_NAME>-uniapr-res.csv`.

To execute ExpressAPR on these patches, [use the CLI](../expapr-cli/).

Note that it may take several months to evaluate on all collected patches. It is possible to run experiments on a subset. To do so, manually delete some files in `apr_tools/` and re-run the scripts above.

