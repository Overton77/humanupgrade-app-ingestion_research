import logging
from research_agent.common.logging_utils import get_logger, configure_logging

# Configure logging when this module is first imported
# This ensures logging works even if logger is imported before run_workflow.py
# configure_logging checks for existing handlers, so it's safe to call multiple times
configure_logging(
    level=logging.INFO,
    logger_name=None,  # Root logger - all child loggers inherit
)

logger = get_logger(__name__) 