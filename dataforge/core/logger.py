import logging
import os
import sys
from logging.handlers import RotatingFileHandler

def setup_logger(name: str = "dataforge", log_file: str = None, level: int = logging.INFO):
    """
    Configure and return a standard logger.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers if setup needed multiple times
    if logger.handlers:
        return logger

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Console Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File Handler
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
        fh.setLevel(level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
    return logger

# Default instance
# We can determine a default log path (e.g. ~/.dataforge/app.log)
default_log_path = os.path.join(os.path.expanduser("~"), ".dataforge", "app.log")
logger = setup_logger("dataforge", default_log_path)
