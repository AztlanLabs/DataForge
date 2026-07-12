"""
Password analysis and recovery tools module.

Provides password hash extraction, dictionary/brute-force attacks
via external tools (hashcat/john), and password strength analysis.
"""
import os
import subprocess
import platform
import re
import tempfile
import time
import zipfile



# ---------------------------------------------------------------------------
# External tool detection
# ---------------------------------------------------------------------------

def _command_available(cmd):
    try:
        which = "which" if platform.system() != "Windows" else "where"
        result = subprocess.run([which, cmd], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def check_hashcat_available():
    return _command_available("hashcat")


def check_john_available():
    return _command_available("john")


def _find_first_available(candidates):
    for cmd in candidates:
        if _command_available(cmd):
            return cmd
    return None


def check_zip2john_available():
    """zip2john ships with John the Ripper (jumbo builds put it on PATH)."""
    return _find_first_available(["zip2john"]) is not None


def check_pdf2john_available():
    """pdf2john is distributed as either a `pdf2john` binary or the
    `pdf2john.pl` script bundled with John the Ripper (jumbo builds)."""
    return _find_first_available(["pdf2john", "pdf2john.pl"]) is not None


# Common system wordlist locations across mainstream Linux distros and
# security-focused distros (Kali/Parrot ship rockyou.txt under wordlists/).
_COMMON_WORDLIST_PATHS = [
    "/usr/share/wordlists/rockyou.txt",
    "/usr/share/john/password.lst",
    "/usr/share/dict/words",
    "/usr/share/dict/american-english",
    "/usr/share/wordlists/fasttrack.txt",
]


def list_common_wordlists():
    """Returns existing well-known system wordlist paths, for a UI quick-pick
    list. Never raises — a missing/unreadable path is just skipped."""
    found = []
    for path in _COMMON_WORDLIST_PATHS:
        try:
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                found.append(path)
        except OSError:
            continue
    return found


# ---------------------------------------------------------------------------
# Password hash extraction
# ---------------------------------------------------------------------------

def extract_password_hashes(source_path, source_type="auto"):
    """
    Extract password hashes from various sources.

    Args:
        source_path: Path to source file.
        source_type: "linux_shadow", "zip", "pdf", or "auto".

    Returns:
        list of dicts with extracted hashes.
    """
    if source_type == "auto":
        source_type = _detect_source_type(source_path)

    if source_type == "linux_shadow":
        return _extract_shadow_hashes(source_path)
    elif source_type == "zip":
        return _extract_zip_info(source_path)
    elif source_type == "pdf":
        return _extract_pdf_info(source_path)
    else:
        return [{"error": f"Unsupported source type: {source_type}"}]


def _detect_source_type(path):
    """Auto-detect source type."""
    basename = os.path.basename(path).lower()
    if basename == "shadow" or basename.endswith("/shadow"):
        return "linux_shadow"

    ext = os.path.splitext(path)[1].lower()
    if ext == ".zip":
        return "zip"
    elif ext == ".pdf":
        return "pdf"

    return "unknown"


def _extract_shadow_hashes(path):
    """Extract hashes from Linux /etc/shadow file."""
    hashes = []
    try:
        with open(path, "r") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) >= 2 and parts[1] and parts[1] not in ("*", "!", "!!", "x"):
                    hash_str = parts[1]
                    hash_type = "unknown"
                    if hash_str.startswith("$1$"):
                        hash_type = "MD5"
                    elif hash_str.startswith("$5$"):
                        hash_type = "SHA-256"
                    elif hash_str.startswith("$6$"):
                        hash_type = "SHA-512"
                    elif hash_str.startswith("$y$") or hash_str.startswith("$gy$"):
                        hash_type = "yescrypt"
                    elif hash_str.startswith("$2"):
                        hash_type = "bcrypt"

                    hashes.append({
                        "username": parts[0],
                        "hash": hash_str,
                        "hash_type": hash_type,
                        "source": path,
                    })
    except (OSError, IOError) as exc:
        hashes.append({"error": str(exc)})

    return hashes


def _extract_zip_info(path):
    """Check if ZIP file is password-protected."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            encrypted_files = []
            for info in zf.infolist():
                if info.flag_bits & 0x1:  # Encrypted flag
                    encrypted_files.append({
                        "filename": info.filename,
                        "compressed_size": info.compress_size,
                        "size": info.file_size,
                    })

            return [{
                "source": path,
                "type": "zip",
                "encrypted": len(encrypted_files) > 0,
                "encrypted_files": encrypted_files,
                "total_files": len(zf.infolist()),
            }]
    except (zipfile.BadZipFile, OSError) as exc:
        return [{"error": str(exc)}]


def _extract_pdf_info(path):
    """Check if PDF is password-protected."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        return [{
            "source": path,
            "type": "pdf",
            "encrypted": reader.is_encrypted,
            "pages": len(reader.pages) if not reader.is_encrypted else "unknown",
        }]
    except ImportError:
        return [{"error": "pypdf not installed"}]
    except Exception as exc:
        return [{"error": str(exc)}]


def generate_crackable_hash(source_path, output_dir=None):
    """
    Produces a hash file in the format hashcat/john actually need to run a
    dictionary attack, by shelling out to the `zip2john`/`pdf2john` helper
    tools bundled with John the Ripper (jumbo builds).

    These formats (ZipCrypto vs. AES-encrypted ZIP; PDF's RC4/AES variants
    with revision-specific O/U/OE/UE fields) are intentionally NOT
    reimplemented by hand here: they're intricate, versioned, and John's own
    extractors are the actively-maintained reference implementation. Calling
    them is both more correct and far less code than re-deriving the exact
    byte layout hashcat/john expect.

    Returns {"hash_file": path, "tool_used": "zip2john"} on success, or
    {"error": "..."} if the required helper isn't installed or extraction
    produced nothing (e.g. the file isn't actually encrypted).
    """
    source_type = _detect_source_type(source_path)
    if source_type == "zip":
        helper = _find_first_available(["zip2john"])
        install_hint = "Install John the Ripper (jumbo build) to get zip2john."
    elif source_type == "pdf":
        helper = _find_first_available(["pdf2john", "pdf2john.pl"])
        install_hint = "Install John the Ripper (jumbo build) to get pdf2john."
    else:
        return {"error": f"Don't know how to generate a crackable hash for: {source_path}"}

    if not helper:
        return {"error": f"{'zip2john' if source_type == 'zip' else 'pdf2john'} not found on PATH. {install_hint}"}

    try:
        result = subprocess.run([helper, source_path], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": f"Failed to run {helper}: {exc}"}

    hash_line = (result.stdout or "").strip()
    if not hash_line or result.returncode != 0:
        detail = (result.stderr or "no output").strip()
        return {"error": f"{helper} produced no hash (file may not be encrypted): {detail}"}

    out_dir = output_dir or tempfile.gettempdir()
    os.makedirs(out_dir, exist_ok=True)
    hash_file = os.path.join(out_dir, f"{os.path.basename(source_path)}.hash")
    try:
        fd = os.open(hash_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(hash_line + "\n")
    except OSError as exc:
        return {"error": f"Could not write hash file: {exc}"}

    return {"hash_file": hash_file, "tool_used": helper, "source": source_path}


# ---------------------------------------------------------------------------
# Password attacks via external tools
# ---------------------------------------------------------------------------

DEFAULT_ATTACK_TIMEOUT = 3600  # 1 hour safety ceiling; cancel_token stops it earlier


def _run_cancellable(cmd, timeout, cancel_token, progress_callback, label):
    """
    Runs `cmd`, polling instead of blocking for the whole timeout window like
    subprocess.run(timeout=...) would — the difference matters here because a
    dictionary attack can legitimately run for a long time, and the app's
    Stop button (which sets cancel_token) needs to actually interrupt it
    instead of the UI being stuck until a 1-hour timeout fires.
    """
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except OSError as exc:
        return {"error": str(exc), "cancelled": False}

    start = time.monotonic()
    poll_interval = 0.5
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=poll_interval)
            return {"returncode": proc.returncode, "stdout": stdout, "stderr": stderr, "cancelled": False}
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            if cancel_token is not None and cancel_token.is_set():
                proc.kill()
                proc.communicate()
                return {"error": "Cancelled by user.", "cancelled": True}
            if elapsed > timeout:
                proc.kill()
                proc.communicate()
                return {"error": f"{label} timed out after {int(timeout)}s.", "cancelled": False}
            if progress_callback:
                progress_callback(int(elapsed), 0, f"{label} running... ({int(elapsed)}s elapsed, Stop to cancel)")


def run_dictionary_attack(
    hash_file,
    wordlist,
    hash_type=None,
    tool="auto",
    timeout=DEFAULT_ATTACK_TIMEOUT,
    progress_callback=None,
    cancel_token=None,
):
    """
    Run a dictionary attack using hashcat or john. `wordlist` may be a
    user-supplied file or one of list_common_wordlists()'s auto-detected
    system wordlists — both are just a path to this function.

    Args:
        hash_file: Path to file containing hashes (see generate_crackable_hash).
        wordlist: Path to wordlist file.
        hash_type: Hash type identifier (hashcat -m mode or john --format).
        tool: "hashcat", "john", or "auto".
        timeout: Safety ceiling in seconds if cancel_token is never set.
        progress_callback: Progress callback (current_seconds, 0, message).
        cancel_token: threading.Event; setting it stops the attack early.

    Returns:
        dict with attack results.
    """
    if not os.path.isfile(hash_file):
        return {"error": f"Hash file not found: {hash_file}"}
    if not os.path.isfile(wordlist):
        return {"error": f"Wordlist not found: {wordlist}"}

    if tool == "auto":
        if check_hashcat_available():
            tool = "hashcat"
        elif check_john_available():
            tool = "john"
        else:
            return {"error": "Neither hashcat nor john the ripper is installed."}

    if tool == "hashcat":
        return _run_hashcat_dictionary(hash_file, wordlist, hash_type, timeout, cancel_token, progress_callback)
    elif tool == "john":
        return _run_john_dictionary(hash_file, wordlist, hash_type, timeout, cancel_token, progress_callback)

    return {"error": f"Unknown tool: {tool}"}


def _run_hashcat_dictionary(hash_file, wordlist, hash_type, timeout, cancel_token, progress_callback):
    """Run hashcat dictionary attack (-a 0 = straight/dictionary mode)."""
    cmd = ["hashcat", "-a", "0"]
    if hash_type:
        cmd.extend(["-m", str(hash_type)])
    cmd.extend([hash_file, wordlist, "--potfile-disable", "--quiet"])

    outcome = _run_cancellable(cmd, timeout, cancel_token, progress_callback, "hashcat")
    if "error" in outcome:
        outcome["tool"] = "hashcat"
        return outcome
    return {
        "tool": "hashcat",
        "returncode": outcome["returncode"],
        "stdout": outcome["stdout"][:5000],
        "stderr": outcome["stderr"][:2000],
        # hashcat's dictionary-mode output is the cracked "hash:password" line(s).
        "cracked": outcome["stdout"][:5000] if outcome["returncode"] == 0 else "",
        "success": outcome["returncode"] == 0,
    }


def _run_john_dictionary(hash_file, wordlist, hash_type, timeout, cancel_token, progress_callback):
    """Run john the ripper dictionary attack."""
    cmd = ["john"]
    if hash_type:
        cmd.extend([f"--format={hash_type}"])
    cmd.extend([f"--wordlist={wordlist}", hash_file])

    outcome = _run_cancellable(cmd, timeout, cancel_token, progress_callback, "john")
    if "error" in outcome:
        outcome["tool"] = "john"
        return outcome

    # john writes cracked passwords into its pot file, not stdout; --show reads them back.
    try:
        show_result = subprocess.run(["john", "--show", hash_file], capture_output=True, text=True, timeout=30)
        cracked = show_result.stdout[:5000] if show_result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        cracked = ""

    return {
        "tool": "john",
        "returncode": outcome["returncode"],
        "stdout": outcome["stdout"][:5000],
        "cracked": cracked,
        # john exits 0 on a clean run; report success only when it ran cleanly
        # and actually recovered something (mirrors the hashcat path).
        "success": outcome["returncode"] == 0 and bool(cracked.strip()),
    }


# ---------------------------------------------------------------------------
# Password strength analysis
# ---------------------------------------------------------------------------

def analyze_password_strength(passwords):
    """
    Analyze the strength of passwords.

    Args:
        passwords: list of password strings.

    Returns:
        list of dicts with strength analysis.
    """
    results = []

    for pwd in passwords:
        analysis = {
            "password": "*" * len(pwd),
            "length": len(pwd),
            "has_upper": bool(re.search(r"[A-Z]", pwd)),
            "has_lower": bool(re.search(r"[a-z]", pwd)),
            "has_digit": bool(re.search(r"\d", pwd)),
            "has_special": bool(re.search(r"[!@#$%^&*(),.?\":{}|<>]", pwd)),
            "issues": [],
        }

        # Score
        score = 0
        if len(pwd) >= 8:
            score += 1
        if len(pwd) >= 12:
            score += 1
        if len(pwd) >= 16:
            score += 1
        if analysis["has_upper"]:
            score += 1
        if analysis["has_lower"]:
            score += 1
        if analysis["has_digit"]:
            score += 1
        if analysis["has_special"]:
            score += 1

        # Common patterns
        if len(pwd) < 8:
            analysis["issues"].append("Too short (< 8 chars)")
        if pwd.lower() in _COMMON_PASSWORDS:
            analysis["issues"].append("Common password")
            score = max(score - 3, 0)
        if re.match(r"^[a-z]+$", pwd) or re.match(r"^[A-Z]+$", pwd):
            analysis["issues"].append("Single case only")
        if re.match(r"^\d+$", pwd):
            analysis["issues"].append("Numbers only")
        if _has_sequential(pwd):
            analysis["issues"].append("Sequential characters detected")
        if _has_repeated(pwd):
            analysis["issues"].append("Repeated characters detected")

        analysis["score"] = min(score, 7)
        analysis["strength"] = (
            "Very Weak" if score <= 1 else
            "Weak" if score <= 2 else
            "Fair" if score <= 3 else
            "Good" if score <= 5 else
            "Strong" if score <= 6 else
            "Very Strong"
        )

        results.append(analysis)

    return results


def _has_sequential(pwd):
    """Check for 3+ sequential characters."""
    for i in range(len(pwd) - 2):
        if ord(pwd[i + 1]) == ord(pwd[i]) + 1 and ord(pwd[i + 2]) == ord(pwd[i]) + 2:
            return True
    return False


def _has_repeated(pwd):
    """Check for 3+ repeated characters."""
    for i in range(len(pwd) - 2):
        if pwd[i] == pwd[i + 1] == pwd[i + 2]:
            return True
    return False


_COMMON_PASSWORDS = {
    "password", "123456", "12345678", "qwerty", "abc123",
    "monkey", "1234567", "letmein", "trustno1", "dragon",
    "baseball", "iloveyou", "master", "sunshine", "ashley",
    "michael", "password1", "shadow", "123123", "654321",
    "superman", "qazwsx", "michael", "football", "password123",
    "admin", "root", "toor", "pass", "test",
}
