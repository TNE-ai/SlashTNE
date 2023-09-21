import json
from typing import List

import requests

from slashgpt.llms.engine.base import LLMEngineBase
from slashgpt.manifest import Manifest
from slashgpt.utils.print import print_debug, print_error
from slashgpt.llms.engine.replicate import message_to_prompt

class LLMEngineHosted(LLMEngineBase):
    def __init__(self, llm_model):
        self.llm_model = llm_model
        self.api_key = self.llm_model.get_api_key_value()
        self.header_key = self.llm_model.llm_model_data.get("header_api_key")
        self.url = self.llm_model.llm_model_data.get("url")
        return

    def chat_completion(self, messages: List[dict], manifest: Manifest, verbose: bool):
        # temperature = manifest.temperature()
        prompt = message_to_prompt(messages, manifest)

        if verbose:
            print_debug("calling *** local")

        # print("calling *** local", self.url)
        arguments = {"inputs": [{"name": "input-0", "data": [prompt], "datatype": "BYTES", "shape": [-1]}]}
        headers = {"Content-Type": "application/json", self.header_key: self.api_key}
        response = requests.post(self.url, headers=headers, json=arguments)
        if verbose:
            print("***response.status_code", response.status_code)
            print("***response.text", response.text)

        output = []
        if response.status_code < 300:
            # print("*** success")
            json_data = json.loads(response.text)
            # print(json.dumps(json_data, indent=2))
            outputs = json_data.get("outputs")
            if outputs:
                # print("*** found outputs")
                data = outputs[0].get("data")
                if data:
                    # print("*** found data", data[0])
                    json_data2 = json.loads(data[0])
                    if json_data2:
                        # print("*** found json_data2", json.dumps(json_data2, indent=2))
                        output = json_data2.get("message")
        else:
            print_error(f"Error:{response.status_code}\n{response.text}")

        res = "\n" + "".join(output)
        function_call = self._extract_function_call(messages[-1], manifest, res)

        role = "assistant"
        if function_call:
            return (role, None, function_call)
        else:
            return (role, res, None)
