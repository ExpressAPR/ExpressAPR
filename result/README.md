This folder contains experiment results.



# RQ1

The result figure for the fixable dataset and the random dataset:

- [fig-rq1-fixable.pdf](fig-rq1-fixable.pdf)
- [fig-rq1-random.pdf](fig-rq1-random.pdf)

Each point means a project under validation. Y-axis shows number of seconds used to validate the project. These figures show that ExpressAPR is significantly faster than baseline methods for most projects.

Raw data behind both figures:

[rq1-overall.csv](rq1-overall.csv)



# RQ2

The result figure for the fixable dataset and the random dataset:

- [fig-rq2-fixable.pdf](fig-rq2-fixable.pdf)
- [fig-rq2-random.pdf](fig-rq2-random.pdf)

Each line is a baseline setup by removing techniques from ExpressAPR or adding techniques into D4J. Each point (x%, y) in the line means this step finishes in y seconds for x% of patch sets. These figures show that all techniques are effective on their own.

Raw data behind both figures:

[rq2-technique.csv](rq2-technique.csv)



# RQ3

The result table:

| Category             | Reason             | % in fixable | % in random |
| -------------------- | ------------------ | ------------ | ----------- |
| Correct result       |                    | 97.197%      | 98.782%     |
| Validation failure   | (patch limitation) | 1.882%       | 0.693%      |
|                      | (test limitation)  | 0.886%       | 0.524%      |
| Result misclassified | (as plausible)     | 0.018%       | 0.000%      |
|                      | (as implausible)   | 0.017%       | 0.001%      |

Raw data behind the table:

[rq3-feasibility.csv](rq3-feasibility.csv)

