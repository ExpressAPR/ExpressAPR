#!/bin/bash
CPU_BASE=-1
NUMA=0
for i in {1..8}
do
  sudo cgcreate -a "$(whoami)" -t "$(whoami)" -g cpuset:expressapr-exp-"$i"
  echo $((CPU_BASE + i)) > /sys/fs/cgroup/cpuset/expressapr-exp-"$i"/cpuset.cpus
  echo $NUMA > /sys/fs/cgroup/cpuset/expressapr-exp-"$i"/cpuset.mems
  sudo chown -R "$(whoami)" /sys/fs/cgroup/cpuset/expressapr-exp-"$i"
done
echo DONE