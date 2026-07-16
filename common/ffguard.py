#!/usr/bin/env python3
"""ffguard — watchdog wrapper for ffmpeg (or any) renders that can hang.

Why: a 45s 1080x1920 H.264 clip should be ~20-90MB and finish in well under a
minute. A render that blows past a size ceiling or a wall-clock cap is hung
(classic cause: unbounded `-loop 1` image inputs with no `-t`/`-shortest`).
This wrapper polls the output file while the render runs and, the moment it
looks runaway, SIGKILLs the whole process group, DELETES the partial output,
and fails loudly instead of letting it burn cores for 40 minutes.

Library use (preferred — wrap the ffmpeg call in your render script):
    import sys, os
    sys.path.insert(0, os.path.expanduser("~/Claude"))
    from ffguard import run_ffmpeg_guarded
    run_ffmpeg_guarded(cmd_list, out_path, expected_seconds=total)

CLI use (guard any ad-hoc ffmpeg call from bash):
    python3 ~/Claude/ffguard.py --out OUT.mp4 --expected 45 -- ffmpeg -y -i ... OUT.mp4

Thresholds (per expected clip length; generous but firm):
    size cap  = max(size_floor_mb, expected_seconds * mb_per_sec)   default 100MB floor, 3 MB/s
    wall cap  = max(wall_floor_s,  expected_seconds * wall_factor)  default 180s floor, 6x
For a 45s clip that's a 135MB / 270s ceiling — the 248MB/45s runaway trips at 135MB.
"""
import os, sys, time, signal, subprocess, argparse


def run_ffmpeg_guarded(cmd, out_path, expected_seconds,
                       mb_per_sec=3.0, size_floor_mb=100.0,
                       wall_factor=6.0, wall_floor_s=180.0,
                       poll_s=2.0, verbose=True):
    """Run `cmd` (list, no shell), watching `out_path`. Kill+dump if runaway.
    Returns 0 on success. Raises RuntimeError if killed, CalledProcessError on
    a normal nonzero exit."""
    size_cap = int(max(size_floor_mb, expected_seconds * mb_per_sec) * 1024 * 1024)
    wall_cap = max(wall_floor_s, expected_seconds * wall_factor)
    start = time.monotonic()
    # start_new_session so the whole tree (ffmpeg + any children) is one group
    proc = subprocess.Popen(cmd, start_new_session=True)

    def _killtree():
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    tripped = None
    while True:
        rc = proc.poll()
        if rc is not None:
            break
        elapsed = time.monotonic() - start
        size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
        if size > size_cap:
            tripped = (f"output {size/1048576:.0f}MB exceeded {size_cap/1048576:.0f}MB "
                       f"ceiling for a ~{expected_seconds:.0f}s clip")
            break
        if elapsed > wall_cap:
            tripped = f"runtime {elapsed:.0f}s exceeded {wall_cap:.0f}s cap"
            break
        time.sleep(poll_s)

    if tripped:
        _killtree()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        dumped = False
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
                dumped = True
            except Exception:
                dumped = False
        msg = (f"[ffguard] KILLED runaway render: {tripped}. "
               f"Partial output {'dumped' if dumped else 'not found'}: {out_path}")
        if verbose:
            print(msg, file=sys.stderr)
        raise RuntimeError(msg)

    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd)
    if verbose:
        mb = os.path.getsize(out_path) / 1048576 if os.path.exists(out_path) else 0
        print(f"[ffguard] ok: {os.path.basename(out_path)} "
              f"({mb:.0f}MB, {time.monotonic()-start:.0f}s)")
    return 0


def _cli():
    ap = argparse.ArgumentParser(description="Run a render with a runaway watchdog.")
    ap.add_argument("--out", required=True, help="output file to watch")
    ap.add_argument("--expected", type=float, required=True, help="expected clip seconds")
    ap.add_argument("--mb-per-sec", type=float, default=3.0)
    ap.add_argument("--size-floor-mb", type=float, default=100.0)
    ap.add_argument("--wall-factor", type=float, default=6.0)
    ap.add_argument("--wall-floor-s", type=float, default=180.0)
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="-- ffmpeg ...")
    a = ap.parse_args()
    cmd = a.cmd[1:] if (a.cmd and a.cmd[0] == "--") else a.cmd
    if not cmd:
        print("ffguard: no command after --", file=sys.stderr)
        sys.exit(2)
    try:
        run_ffmpeg_guarded(cmd, a.out, a.expected, mb_per_sec=a.mb_per_sec,
                           size_floor_mb=a.size_floor_mb, wall_factor=a.wall_factor,
                           wall_floor_s=a.wall_floor_s)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _cli()
