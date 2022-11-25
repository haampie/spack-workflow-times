Script to download the spack/spack github action workflow runs to plot timings

Usage:

```
 export GITHUB_TOKEN=...
python3 spack-workflow-time.py --update --since 2022-09-01 --job-name clingo-cffi --step-name 'Run unit tests' | tee out
```

The file `out` contains lines with `<jobid> <timestamp> <duration>`.

Since only completed workflow runs are downloaded, everything is cached on the filesystem, so a second run should be faster:

```
python3 spack-workflow-time.py --job-name '(build|macos) \((3.8|3.10)\)' --step-name 'Run unit tests' | tee macos
```

Both `--job-name` and `--step-name` take regexes.

