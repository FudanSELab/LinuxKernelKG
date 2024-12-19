import logging

def setup_logger(name='pipeline', level=logging.INFO):
    """Set up and return a logger instance"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Create handler if no handlers exist
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger 