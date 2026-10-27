import logging, sys, os
from config.settings import LOG_LEVEL, LOG_FILE

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.stream = open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    if LOG_FILE:
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger
