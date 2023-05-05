This folder contains the user-friendly ExpressAPR command-line interface.

Defects4J and Maven are supported out-of-the-box. Configuration is required for other benchmarks (see instruction below).



# Demonstration

You can use the pre-built docker image and the shell script to quickly showcase ExpressAPR on two example patch sets.

- Download the pre-built image [from FigShare](https://figshare.com/s/7b31e3bb6ccadd135125)
- `docker load -i expapr-cli.tar.gz`
- `chmod +x demo.sh`
- `./demo.sh`
  - During the first run, it may take about 2~5 minutes to initialize the project-under-validation
  - Then it validates the 2 sample patch sets under the `demo-patches/` folder in generally 4~10 seconds
  - It prints the validation result (`F` = test failure, `C` = compile error, `s` = success)




# Using the CLI with Docker

**Building the container:**

- Execute `docker build -t expapr-cli .`

**Initialize for a bug:**

Say that you want to initialize the CLI for the Defects4J bug Math-65 with 2 tasks running in parallel.

- Prepare an empty temp directory for the CLI to use (say, `/path/to/workdir`).
  - Projects will be checked out in this directory. Validation results will be saved there as well.
- Execute `docker run -v /path/to/workdir:/tmp/workdir expapr-cli init -i defects4j -b Math-65 -w /tmp/workdir -j 2 -d trivial`
  - It may take up to several minutes to compile the project, profile the tests and inject the runtime files.

*This step does not depend on patches so it can be done prior to the repair process.*

*Note that `-j 2` means that 2 tasks will be run in parallel in the future when validating patches in this temp directory. The initialization step is not parallelized.*

**Prepare candidate patches:**

Your patch generator should output patches in JSON format, each JSON file corresponding to a patch set. Below is an example patch set (don't include the comments):

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

**Validate candidate patches:**

Say that you want to validate all patch sets in the `/path/to/demo-patches/` folder.

- Execute `docker run -v /path/to/workdir:/tmp/workdir -v /path/to/demo-patches:/tmp/patches --pids-limit -1 expapr-cli run -w /tmp/workdir "/tmp/patches/*.json"`
- The result will be written to `/path/to/workdir/result.jsonl`

Each line in the file (in JSON format) corresponds to the result for one patch set. Below is an example result:

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



# Using the CLI without Docker

It is fine if you want to run the CLI directly on your machine. Below are commands that do not use Docker.

**Install dependencies:**

Refer to the commands in `Dockerfile`. Basically you emulate every `RUN`, `ENV` and `COPY` command on your own machine.

The CLI should be compatible with Python 3.7+.

**Initialize for a bug:**

- Execute `python3 -m cli init -i defects4j -b Math-65 -w /path/to/workdir -j 2 -d trivial`

**Validate patches:**

- Execute `python3 -m cli run -w /path/to/workdir "/path/to/demo-patches/*.json"`



Note that systemd may limit the maximum number of processes per user. This may cause problems with a large project (e.g., Closure) if you are running with a large number of threads. Get the current limit with this command:

- `sudo cat /sys/fs/cgroup/pids/user.slice/user-$(id -u).slice/pids.max`

Change this limit by modifying the `pids.max` file above.



# Configuring for other benchmarks

The CLI needs to know how to check out the project and get information about the bug (e.g. path of test classes) through an **interface** (basically a Python class).

We have implemented interfaces for Defects4J (`-i defects4j -b Math-65`) and Maven (`-i maven -b /path/to/project`). You can subclass the `class Interface` in `cli/interface/__init__.py`. Refer to `cli/interface/defects4j.py` for our implementation.

If you are using Docker, remember to rebuild the container afterward.