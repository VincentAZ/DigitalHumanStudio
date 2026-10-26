# Isolated platform-marker diagnosis

This offline uv 0.11.32 test isolates the failure from Isaac, the GPU, and network package availability. It uses two synthetic metadata-only wheels named pytetwild, versions 0.2.3 and 0.3.0, with no dependencies and an empty `all` extra. These are diagnostic fixtures, not the actual library. No package was installed.

Both projects restrict supported environments to Linux x86_64 and use the same Python 3.12.13 interpreter, local wheel directory, and resolver options. The only difference is how the dependency markers express architecture:

- `substring.toml`: `platform_machine in 'x86_64 AMD64'` and `platform_machine in 'aarch64 arm64'`. Exit 1, reproducing the original impossible combined branch.
- `explicit.toml`: `(platform_machine == 'x86_64' or platform_machine == 'AMD64')` and `(platform_machine == 'aarch64' or platform_machine == 'arm64')`. Exit 0; lock selects 0.2.3 for Linux x86_64.

Exact commands and working directories are in `results.json`; stdout/stderr and the successful lock are retained alongside the inputs. Synthetic wheel fixtures remain in `.runtime/marker-repro-20261026T024641Z/wheels/`.

Conclusion: explicit architecture comparisons resolve this isolated marker failure. A candidate fix is a recorded build-time patch to the pinned Isaac Lab metadata, preserving every dependency version requirement and keeping the vendor checkout pristine. It must still be tested against the real dependency graph and runtime. This diagnostic does not establish installation, physics, or rendering compatibility. No patch has been applied to the active build recipe.
