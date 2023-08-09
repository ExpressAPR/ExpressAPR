# ExpressAPR

**Efficient Patch Validation for Java Automated Program Repair Systems**



## ✨ Highlights

- **Equipped with mutation testing accerelation techniques**
  - Mutant Schemata + Mutant Deduplication + Test Virtualization + Test Case Prioritization + Parallelization
  - ~100x faster than `defects4j compile && defects4j test` (experimented with four APR systems)

- **A user-friendly command-line interface**
  - Out-of-the-box support of Defects4J and Maven
  - Can be configured for other benchmarks




## 👨‍🏫 Quick demo with Docker

- Clone this respository
- Download the Docker image [from FigShare](https://doi.org/10.6084/m9.figshare.21559650)
- `docker load -i expapr-cli.tar.gz`
- `./demo.sh`
  - Only during the first run, it takes 1~3 minutes to instrument the project under validation
  - Then it loads the three sample patch sets (105 patches in total) in the `demo-patches/` folder, and validate them in several seconds
  - It prints the validation result (`F` = test failure, `C` = compile error, `s` = success) onto the screen



## 📚 Usage

### Step 1. Preparation

- Use Linux (we have tested on Ubuntu 18.04 and 22.04)
- Install Git, JDK ≥1.8, and Python ≥3.7
- Install [Defects4J](https://github.com/rjust/defects4j) and/or Maven if you want to validate patches with them
- Clone this repository
- `pip3 install -r requirements.txt`

### Step 2. Initialize ExpressAPR for a project (`init`)

Say that you want to work with the bug Math-65 from Defects4J with the degree of parallelization as 3.

1. Find an empty directory for ExpressAPR to work with (say, `/path/to/workdir`). Projects will be checked out in this directory. Validation results will be saved there as well.
2. Execute `./expapr-cli init -i defects4j -b Math-65 -w /path/to/workdir -j 3 -d trivial`, which may take up to several minutes.
   - `-i defects4j` and `-b Math-65` specify the project to validate.
   - `-w /path/to/workdir` tells ExpressAPR to initialize the proejct into this directory.
   - `-j 3` enables parallel patch validation (in Step 4) with 3 processes. The initialization step itself is not parallelized.
   - `-d trivial` turns on basic mutant deduplication.

*The initialization step does not depend on patches, so it can be done prior to the repair process.*

### Step 3. Generate candidate patches

Run your APR tool to generate candidate patches to be validated.

It should store candidate patches in JSON format, each JSON file corresponding to a patch set containing all patches to the same location.

Below is an example patch set (don't include the comments):

```json
{
    "manifest_version": 3,
    // the version of this json data file.
    // set it to 3 for now.
    
    "interface": "defects4j",
    "bug": "Math-65",
    // the bug you are working on.
    // must be consistent with what you have typed in the `init` command.
    
    "filename": "src/main/java/path/to/Modified.java",
    // path of the patched source file, relative to the project root.
    
    "context_above": "public class Modified { void foo() { int x =",
    "unpatched": "Integer.MAX_VALUE",
    "context_below": "; int y = x + 1; } }",
    // this marks the patch location of this patch set.
    // context_above + unpatched + context_below should be the original content of the file.
    
    "patches": [
        "-100",
        "-100; x++",
        "Integer.MAX_VALUE; return"
    ]
    // the generated patches. each of them replaces the "unpatched" part.
    // for the best acceleration, keep the "unpatched" part as short as possible.
    //   e.g., as all patches do not touch "int x =", it is put to "context_above".
}
```

*The [demo-patches/](demo-patches/) folder contains three real patch sets collected from our experiment for demonstration.*

### Step 4. Run ExpressAPR to validate them (`run`)

Say that all patch sets are stored in the `/path/to/patches/` folder.

1. Execute `./expapr-cli run -w /tmp/workdir "/tmp/patches/*.json"`
   - `-w /tmp/workdir` specifies the working directory initialized by the `init` command.
   - `"/tmp/patches/*.json"` specifies the glob pattern to find the patch sets to be validated (make sure to quote this pattern, or it will be expanded by your shell).
2. Inspect validation result at `/path/to/workdir/result.jsonl`

Each line of that file (in JSON format) corresponds to the result for one patch set. Below is an example result:

```json
{
    "patches_path": "/tmp/patches/1.json",
    // the filename of the patch set.
    
    "technique": "expapr",
    // "expapr" if it is successfully validated by ExpressAPR.
    // "fallback" if ExpressAPR reports a validation failure so the fallback technique is used.
    // null if both techniques fail.
    
    "succlist": "FFFFFFFCFFFFFFCCCFFCCFCCCFFCFCFC",
    // the validation result of each patch in the patch set.
    // lowercase "s" (not in this example) means a plausible patch.
    // other letters mean an implausible patch.
    //   some examples: "F": test failed. "C": compile failed. "T": timed out.
    
    "extra": {...}
    // some telemetry numbers.
}
```

### Command-line options

Both `init` and `run` command support command-line options to tweak some behaviors. Use `--help` to see the full list of options.



## 🛠 Configuring for other benchmarks

We provide out-of-the-box support for Defects4J (`-i defects4j -b Math-65`) and Maven (`-i maven -b /path/to/maven-project`). To add support for other benchmarks, you need to provide an **interface** (as a Python class) so that the CLI know how to check out the project and get information about the bug.

Please inherit the `class Interface` in `cli/interface/__init__.py` to provide the interface for the new benchmark. Refer to `cli/interface/defects4j.py` for our implementation of Defects4J.



## 💊 Troubleshooting

### Q1. Problems when using a large `-j` parameter

Most Linux distributions (e.g., Ubuntu) limit the maximum number of processes a user can use. This may cause problems with some projects (e.g., Closure) if you are running with a large number of threads. Get the current limit with these two commands:

- `sudo cat /proc/sys/kernel/pid_max` (kernel limit)
- `sudo cat /sys/fs/cgroup/pids/user.slice/user-$(id -u).slice/pids.max` (systemd limit)

Increase the limit by modifying the files above.

### Q2. Patch validation results are wrong

**Step 1: Use `--no-dedup` flag.** The Mutant Deduplication technique used in ExpressAPR assumes that tests are *stable* (not flaky, fuzzy, or concurrent). Although ExpressAPR tries to detect unstability, it may fails to detect some unstable tests, resulting in incorrect results. If this is the case, pass `--no-dedup` to the `expapr-cli run` command to opt-out Mutant Deduplication.

**Step 2: Use `-t fallback` flag.** If the result is still wrong with `--no-dedup`, it may be a problem in [VMVM](https://github.com/Programming-Systems-Lab/vmvm), a third-party Test Virtualization dependency of ExpressAPR (similar to the JVM Reset component in UniAPR). We have [already fixed a few problems we encounter](https://github.com/ExpressAPR/VMVM/compare/07a36dc21373147c50ceacd7bff2b2e7a86c8780...master) in our VMVM fork, but there may be more problems. You may investigate the problem, or pass `-t fallback` to the `expapr-cli run` command to disable Test Virtualization (and also Mutant Deduplication that depends on it).

### Q3. Cannot `init` for a Maven project

We currently don't support validating patches to submodules. If this is the case, please directly validate the submodule (set `-b` to the directory of the submodule), not the parent module.



## 🔗 Other resources

- [📄 arxiv.org/abs/2305.03955](https://arxiv.org/abs/2305.03955): Our research paper describing the implementation of ExpressAPR

- 🎞 ASE2023 *(TODO link)*: The tool demonstration paper

- [💾 src/](src/): The source code of ExpressAPR Core with some documentation
- [📊 github.com/ExpressAPR/experiment](https://github.com/ExpressAPR/experiment): Stuff to reproduce the experiment in the research paper, and raw results