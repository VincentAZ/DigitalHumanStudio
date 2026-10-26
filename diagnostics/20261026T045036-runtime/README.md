# Runtime acceptance stopped

The first run in this invocation exited 1 on the cube minimum-height assertion. The wrapper exited 4, retained the container, and did not start run 2. `stopped-result.json` lists what was reached and what remains unvalidated. The command, exact test script, image metadata, process/launcher exit codes, stdout/stderr and Kit log are preserved here.

The test requires a 0.5 m cube center to remain above 0.20 m throughout the fall and finish within 0.03 m of 0.25 m. The final-height assertion passed but the minimum-height assertion failed. Numeric samples were not saved because the test writes them after its assertions. The failure is real acceptance evidence, but does not yet distinguish contact-solver behavior, simulation settings or test measurement issues. It is not evidence that reinstalling Ubuntu fixes the problem.

Before an authorized retry, preserve trajectories/scene and threshold values before assertions, then inspect timing, contact settings and pose reads. Keep the acceptance threshold unchanged unless evidence supports an explicit reviewed revision. Do not switch architecture or start Milestone 1.
