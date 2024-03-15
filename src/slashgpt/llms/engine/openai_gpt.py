from __future__ import annotations

import sys
from typing import TYPE_CHECKING, List, AsyncGenerator

from openai import OpenAI, AsyncOpenAI
import tiktoken  # for counting tokens

from slashgpt.function.function_call import FunctionCall
from slashgpt.llms.engine.base import LLMEngineBase
from slashgpt.utils.print import print_debug, print_error


if TYPE_CHECKING:
    from slashgpt.llms.model import LlmModel
    from slashgpt.manifest import Manifest


class LLMEngineOpenAIGPT(LLMEngineBase):
    def __init__(self, llm_model: LlmModel):
        super().__init__(llm_model)
        key = llm_model.get_api_key_value()
        if key == "":
            print_error("OPENAI_API_KEY environment variable is missing from .env")
            sys.exit()

        self.client = OpenAI(api_key=key)
        self.async_client = AsyncOpenAI(api_key=key)

        # Override default openai endpoint for custom-hosted models
        api_base = llm_model.get_api_base()
        if api_base:
            self.async_client.api_base = api_base

        return

    def image_completion(self, messages: List[dict], manifest: Manifest, verbose: bool) -> string:
        params = {
            "model": manifest.model().get("model_name"),
            # Prompt taken from the OpenAI guide
            "prompt": f"I NEED to test how the tool works with extremely simple prompts. DO NOT add any detail, just use it AS-IS\n{messages}",
            "size": "1024x1792",
            "quality": "standard",
            "n": 1,
        }
        response = self.client.images.generate(**params)
        if response:
            image_url = response.data[0].url
            return image_url

        return None

    async def chat_completion(self, messages: List[dict], manifest: Manifest, verbose: bool) -> AsyncGenerator:
        model_name = self.llm_model.name()
        temperature = manifest.temperature()
        functions = manifest.functions()
        stream = manifest.stream()
        num_completions = manifest.num_completions()
        # max_tokens = manifest.max_tokens()

        # TODO: parse each message to see if it contains an image URL
        if model_name == "gpt-4-vision-preview":
            img_text_content = {"type": "text"}
            img_url_content = {"type": "image_url"}
            for message in messages:
                # System prompt becomes text input to the model
                if message.get("role") == "system":
                    img_text_content["text"] = message.get("content")
                # Now we extract the image url from the user content
                elif message.get("role") == "user":
                    url_ind = message.get("content").find("https://")
                    if url_ind >= 0:
                        img_url = message.get("content")[url_ind:].split(" ")[0]
                        # TODO(lucas): Expose detail parameter in manifest
                        img_url_content["image_url"] = {"url": img_url, "detail": "low"}
                    else:
                        raise ValueError("No image URL detected")
            messages = [{"role": "user", "content": [img_text_content, img_url_content]}]
            params = {"model": model_name, "messages": messages, "stream": stream}
        else:
            params = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "stream": stream,
                "n": num_completions,
            }

        if not stream:
            # Make a non-streaming API call
            if model_name == "dall-e-3":
                response = self.async_client.images.generate(**params)
            else:
                if functions:
                    tools_list = []
                    for function in functions:
                        tools_list.append({"type": "function", "function": function})
                    params.update({"tools": tools_list, "tool_choice": "auto"})
                response = await self.async_client.chat.completions.create(**params)

            answer = response.choices[0].message

            res = answer.content

            if answer.tool_calls:
                function_call = FunctionCall(answer.tool_calls[0].function, manifest)
                yield function_call
            else:
                yield res

        else:
            # TODO(lucas): Support streaming and function calls (this only processes the text)
            stream_keys = ["model", "stream", "messages"]
            stream_params = {k: params[k] for k in stream_keys}

            stream = self.async_client.chat.completions.create(**stream_params)

            collected_messages = []
            async for chunk in await stream:
                message = chunk.choices[0].delta.content
                function_call = chunk.choices[0].delta.tool_calls
                if function_call:
                    yield function_call
                if message:
                    collected_messages.append(message)
                    yield message

    def __num_tokens(self, text: str):
        model_name = self.llm_model.name()
        encoding = tiktoken.encoding_for_model(model_name)
        return len(encoding.encode(text))

    def is_within_budget(self, text: str, verbose: bool = False):
        token_budget = self.llm_model.max_token() - 500
        return self.__num_tokens(text) <= token_budget
