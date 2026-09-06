// docker subprocess helper — port of `hermes-plugin/mcpclient.py :: _docker`.
// One async function that runs a docker sub-command and returns
// (returncode, combined stdout/stderr). Never throws.
import { execFile } from "node:child_process";
export function docker(args, timeoutMs) {
    return new Promise((resolve) => {
        execFile("docker", args, { timeout: timeoutMs }, (err, stdout, stderr) => {
            const out = (stdout ?? "").trim() || (stderr ?? "").trim() || "";
            if (!err) {
                resolve({ code: 0, out });
                return;
            }
            // `execFile` exposes the exit code on err.code when the child exited.
            const code = typeof err.code === "number"
                ? err.code
                : -1;
            if (code === -1) {
                // The command never ran — `docker` missing, killed by a signal, or
                // the timeout fired. Surface a useful error.
                const msg = err.message ?? String(err);
                if (msg.includes("ENOENT")) {
                    resolve({ code: -1, out: "[ERROR] 'docker' executable not found in PATH" });
                    return;
                }
                if (msg.toLowerCase().includes("timed out")) {
                    resolve({ code: -1, out: `[ERROR] docker command timed out after ${timeoutMs}ms` });
                    return;
                }
                resolve({ code: -1, out: `[ERROR] ${msg}` });
                return;
            }
            resolve({ code, out: out || String(err) });
        });
    });
}
export async function dockerRunning(container) {
    const r = await docker(["inspect", "-f", "{{.State.Running}}", container], 15_000);
    return r.code === 0 && r.out.trim() === "true";
}
