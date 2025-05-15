import logging

class BaseLLM:
    """
    Base class for LLM implementations.
    All specific LLM implementations should inherit from this class.
    """
    
    def __init__(self, config: dict):
        """
        Initialize the base LLM class.
        
        Args:
            config: Configuration dictionary for the LLM
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Configure logging if not already configured
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def get_response(self, prompt: str) -> str:
        """
        Get a response from the LLM for a given prompt.
        This method should be implemented by subclasses.
        
        Args:
            prompt: The input prompt
            
        Returns:
            The LLM's response
        """
        raise NotImplementedError("Subclasses must implement get_response method") 