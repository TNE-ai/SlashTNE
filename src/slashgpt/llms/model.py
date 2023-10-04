import importlib
import inspect
import os
from typing import List

from slashgpt.manifest import Manifest
from slashgpt.utils.print import print_error


class LlmModel:
    """It represents a LLM model such as Llama2 and GPT3.5"""

    def __init__(self, llm_model_data: dict, llm_engine_configs: dict):
        """Although it is possible to create LlmModel object directly,
        it is a lot easier to create it using one of helper functions (in model_utils.py)

        Args:

            llm_model_data (dict): parameters to the LLM model (dict)
            llm_engine_configs (dict): dictionary of LLM engines
        """
        self.llm_model_data = llm_model_data
        """
        Parameters to the LLM model (dict):
        
            engine_name (str): name of the engine (e.g, openai-gpt')
            model_name (str): specific model name (e.g, 'gpt-3.5-turbo-0613')
            api_key (str): name of the env. variable which holds a secret key (e.g, 'OPENAI_API_KEY')
            max_token (str): maximum token length (e.g, 4096)
            default (boolean, optional): True if this is the default model
        """
        self.engine = self.__get_engine(llm_engine_configs)
        """A subclass of LLEngineBase, 
        which implements chat_completion method for a particular LLM
        """

    def get(self, key: str):
        """Returns the specified property of the model data"""
        return self.llm_model_data.get(key)

    def name(self):
        """Returns the model name"""
        return self.get("model_name")

    def max_token(self):
        """Returns the maximum token length"""
        return self.get("max_token") or 4096

    def engine_name(self):
        """Returns the engine name (key to the llm_engine_configs)"""
        return self.get("engine_name")

    def check_api_key(self):
        """Returns if the required api key is specified in the environment"""
        if self.get("api_key"):
            return os.getenv(self.get("api_key"), None) is not None
        return True

    def get_api_key_value(self):
        """Returns the api key specified in the eivironment"""
        return os.getenv(self.get("api_key"), "")

    def replicate_model(self):
        """Returns the replicate model (WHY HERE?)"""
        if self.get("replicate_model"):
            return self.get("replicate_model")

        # TODO default replicate model
        return "a16z-infra/llama7b-v2-chat:a845a72bb3fa3ae298143d13efa8873a2987dbf3d49c293513cd8abf4b845a83"

    def __get_engine(self, llm_engine_configs: dict):
        class_data = llm_engine_configs.get(self.engine_name())

        if class_data:
            if inspect.isclass(class_data):
                return class_data(self)
            else:
                module = importlib.import_module(class_data["module_name"])
                my_class = getattr(module, class_data["class_name"])
                return my_class(self)
        else:
            print_error("No engine name: " + self.engine_name())
            return None

    def generate_response(self, messages: List[dict], manifest: Manifest, verbose: bool):
        """It calls the engine's chat_completion method

        Args:

            messages (list of dict): chat messages
            manifest (Manifest): it specifies the behavior of the LLM agent
            verbose (bool): True if it's in verbose mode.
        """
        return self.engine.chat_completion(messages, manifest, verbose)
