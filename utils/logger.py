import logging
from datetime import datetime
import os

nowtime = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
log_dir = 'data/log'
os.makedirs(log_dir, exist_ok=True)  # Create the directory if it doesn't exist

def setup_logger(name='pipeline', level=logging.INFO, console_output=True, file_output=False):
    """Set up and return a logger instance"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Create handler if no handlers exist
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        if console_output:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        if file_output:
            file_handler = logging.FileHandler(f'{log_dir}/{name}_{nowtime}.log', mode='w', encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger 