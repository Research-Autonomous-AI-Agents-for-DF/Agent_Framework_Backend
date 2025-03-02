import logging
import os

# Create a logger for tool integrity (audit logging)
logger = logging.getLogger("chainlit_audit_logger")
logger.setLevel(logging.INFO)  # INFO level for audit logging

# Remove any existing handlers to avoid duplicates
if logger.hasHandlers():
    logger.handlers.clear()


def setup_default_handler():
    """Sets up a default file handler writing to a default log file."""
    default_filename = "chainlit_integrity_default.log"
    file_handler = logging.FileHandler(default_filename, mode="a")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)-25s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


# Set up the default handler on module load.
setup_default_handler()


def update_log_file(thread_id: str):
    """
    Updates the log file name based on the thread ID.
    Removes any existing FileHandler and adds a new one that writes
    to a file in the 'session_logs' folder named using the thread ID.
    """
    # Create the folder if it doesn't exist
    log_folder = "session_logs"
    os.makedirs(log_folder, exist_ok=True)

    # Create new file name based solely on thread_id
    new_filename = os.path.join(log_folder, f"thread_{thread_id}.log")

    # Remove all existing file handlers
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)

    # Create and add a new file handler with the new file name
    new_handler = logging.FileHandler(new_filename, mode="a")
    new_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    new_handler.setFormatter(formatter)
    logger.addHandler(new_handler)

    logger.info(f"Log file updated to {new_filename}")
