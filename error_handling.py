import logging
import time
from alpaca.common.exceptions import APIError, APIConnectionError, RateLimitError

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ErrorHandler:
    @staticmethod
    def handle_api_error(error):
        """Handle API-related errors."""
        if isinstance(error, RateLimitError):
            logging.error("Rate limit exceeded. Waiting 60 seconds before retrying...")
            time.sleep(60)  # Wait for 60 seconds before retrying
        elif isinstance(error, APIConnectionError):
            logging.error("Connection error occurred. Retrying in 10 seconds...")
            time.sleep(10)  # Wait for 10 seconds before retrying
        elif isinstance(error, APIError):
            logging.error(f"API error occurred: {error}")
            # Handle specific error codes if needed
        else:
            logging.error(f"An unexpected API error occurred: {error}")

    @staticmethod
    def handle_general_error(error):
        """Handle general errors."""
        logging.error(f"An unexpected error occurred: {error}")

    @staticmethod
    def retry_on_failure(function, *args, **kwargs):
        """Retry the function if an error occurs."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return function(*args, **kwargs)
            except Exception as error:
                logging.error(f"Attempt {attempt + 1} failed with error: {error}")
                time.sleep(5)  # Wait for 5 seconds before retrying
        logging.error("Max retries reached. Operation failed.")

    @staticmethod
    def safe_execute(function, *args, **kwargs):
        """Safely execute a function with error handling."""
        try:
            return function(*args, **kwargs)
        except APIError as api_error:
            ErrorHandler.handle_api_error(api_error)
        except Exception as general_error:
            ErrorHandler.handle_general_error(general_error)
