#!/bin/sh

workdir=$(pwd)/expapr-cli-workdir

echo "===== initializing (this is a one-time procedure for this project and not related to patches)"
docker run --rm -v "$workdir":/tmp/workdir expapr-cli init -i defects4j -b Math-65 -w /tmp/workdir -j 3 -d trivial --reuse-workdir

echo "===== validating demo-patches"
docker run -v "$workdir":/tmp/workdir -v "$(pwd)/demo-patches":/tmp/patches --pids-limit -1 expapr-cli run -w /tmp/workdir "/tmp/patches/*.json" --continue NO

echo "===== below are validation results"
cat "$workdir/result.jsonl"
