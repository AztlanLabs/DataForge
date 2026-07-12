import hashlib

BLOCK_SIZE = 65536  # 64kb chunks

# Digest algorithms the app supports everywhere (CLI, GUI, forensics, integrity).
SUPPORTED_ALGORITHMS = ('md5', 'sha1', 'sha256', 'sha512', 'blake2b')

def get_file_hash(filepath: str, algo: str = 'md5', cancel_token=None) -> str:
    """
    Calculate the hash of a file using the specified algorithm.
    Supported algorithms: md5, sha1, sha256, sha512, blake2b.
    """
    if algo not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"Unsupported hash algorithm: {algo}")
    
    hasher = getattr(hashlib, algo)()
    
    try:
        with open(filepath, 'rb') as f:
            while True:
                if cancel_token and cancel_token.is_set():
                    return ""
                
                data = f.read(BLOCK_SIZE)
                if not data:
                    break
                hasher.update(data)
        return hasher.hexdigest()
    except OSError:
        return ""

def get_hashes(filepath: str, algos: list[str]) -> dict[str, str]:
    """Calculate multiple hashes in one pass."""
    hashers = {algo: getattr(hashlib, algo)() for algo in algos}
    
    try:
        with open(filepath, 'rb') as f:
            while True:
                data = f.read(BLOCK_SIZE)
                if not data:
                    break
                for h in hashers.values():
                    h.update(data)
        return {algo: h.hexdigest() for algo, h in hashers.items()}
    except OSError:
        return {algo: "" for algo in algos}
