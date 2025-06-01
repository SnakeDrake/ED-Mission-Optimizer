#!/usr/bin/env python3
import logging
import logging.handlers
from constants import LOG_FILE

def setup_logging():
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
    
    # Configure file handler
    log_file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=1024*1024, backupCount=5, encoding='utf-8'
    )
    log_file_handler.setFormatter(log_formatter)
    log_file_handler.setLevel(logging.DEBUG) # Capture all levels in the file

    # Configure console handler (optional, for more immediate feedback during development)
    # console_handler = logging.StreamHandler()
    # console_handler.setFormatter(log_formatter)
    # console_handler.setLevel(logging.INFO) # Show INFO and above on console

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) # Set root logger to lowest level

    # Clear existing handlers (if any, to prevent duplicate logging if re-configured)
    # for handler in root_logger.handlers[:]:
    #     root_logger.removeHandler(handler)
        
    if not root_logger.handlers: # Add handlers only if they haven't been added
        root_logger.addHandler(log_file_handler)
        # root_logger.addHandler(console_handler) # Uncomment to add console output

    logging.info("Logging configured.")