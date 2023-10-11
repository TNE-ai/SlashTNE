from typing import Optional

from slashgpt.chat_config_with_manifests import ChatConfigWithManifests
from slashgpt.chat_session import ChatSession
from slashgpt.function.jupyter_runtime import PythonRuntime
from slashgpt.history.storage.abstract import ChatHistoryAbstractStorage
from slashgpt.llms.model import LlmModel
from slashgpt.utils.print import print_error, print_warning


class ChatApplication:
    """This instance represents an LLM application,
    which consists of multiple LLM agents."""

    def __init__(self, config: ChatConfigWithManifests, callback=None, model: Optional[LlmModel] = None, runtime: Optional[PythonRuntime] = None):
        self.config: ChatConfigWithManifests = config
        """The configuration of LLMs and manifests """
        self.llm_model: LlmModel = model or self.config.get_default_llm_model()
        """The default LLM model for this application"""
        self.runtime: Optional[PythonRuntime] = runtime
        """Python runtime"""
        self._callback = callback or self._noop
        """Callback function"""
        self.session: Optional[ChatSession] = None
        """Active session, initially None"""

    def switch_session(
        self,
        agent_name: Optional[str] = None,
        intro: bool = True,
        memory: Optional[dict] = None,
        history_engine: Optional[ChatHistoryAbstractStorage] = None,
    ):
        """
        It terminates the current chat session (if any) and start a new.

            agent_name(str): specifies the AI agent to activate
            intro(bool): specifies if it needs to add the introduction message
            memory(dict, optional): initial set of short-term memory
            history_engine(ChatHistoryAbstractStorage, optional): history_engine
        """
        if agent_name is not None:
            if self.config.has_manifest(agent_name):
                manifest = self.config.manifests.get(agent_name)
                self.session = ChatSession(
                    self.config,
                    default_llm_model=self.llm_model,
                    manifest=manifest,
                    agent_name=agent_name,
                    intro=intro,
                    memory=memory,
                    history_engine=history_engine,
                )
                if self.config.verbose:
                    self._callback(
                        "info",
                        f"Activating: {self.session.title()} (model={self.session.llm_model.name()}, temperature={self.session.temperature()}, max_token={self.session.llm_model.max_token()})",
                    )
                else:
                    self._callback("info", f"Activating: {self.session.title()}")
                if self.session.manifest.get("notebook"):
                    (result, _) = self.runtime.create_notebook(self.session.llm_model.name())
                    self._callback("info", f"Created a notebook: {result.get('notebook_name')}")

                if self.session.intro_message:
                    self._callback("bot", self.session.intro_message)
                return
            else:
                print_error(f"Invalid slash command: {agent_name}")

        print_warning("No agent_name was spacified")
        self.session = ChatSession(self.config, default_llm_model=self.llm_model, history_engine=history_engine)

    def _noop(self, callback_type, data):
        pass

    def _process_event(self, callback_type, data):
        self._callback(callback_type, data)

        if callback_type == "emit":
            # All emit methods must be processed here
            (action_method, action_data) = data

            if action_method == "switch_session":
                memory = action_data.get("memory")
                if memory is not None:
                    self.session.context.setMemory(memory, action_data.get("merge"))

                agent_to_activate = action_data.get("agent")
                if agent_to_activate:
                    self.switch_session(agent_name=agent_to_activate, memory=self.session.context.memory())
                    message_to_append = action_data.get("message")
                    if message_to_append:
                        self.session.append_user_question(message_to_append)
                    self.process_llm()

    def process_llm(self):
        """Call the LLM with the current context and process the response"""
        try:
            self.session.call_loop(self._process_event, self.config.verbose, self.runtime)
        except Exception as e:
            print_error(f"Exception: Restarting the chat :{e}")
            self.switch_session(self.session.agent_name)
            if self.config.verbose:
                raise
