import chainlit as cl
from logging_config import logger  # Import the centralized logger

from typing import List, Optional, Union, Dict
from autogen import Agent, GroupChat, GroupChatManager, ConversableAgent
from autogen.agentchat.contrib.retrieve_user_proxy_agent import RetrieveUserProxyAgent

# A simple helper function that ensures a response is received.


async def ask_helper(func, **kwargs):
    res = await func(**kwargs).send()
    while not res:
        res = await func(**kwargs).send()
    return res


class ChainlitConversableAgent(ConversableAgent):
    def get_human_input(self, prompt: str) -> str:
        logger.info(
            f"[ChainlitConversableAgent] get_human_input called with prompt: {prompt}")

        if "Press enter to skip and use auto-reply, or type 'exit' to end the conversation:" in prompt:
            logger.info(
                "[ChainlitConversableAgent] Detected skip/exit prompt context.")
            res = cl.run_sync(
                ask_helper(
                    cl.AskActionMessage,
                    content=f'*AI Agent Framework:*\n\nContinue or provide feedback? (Next agent is {self.name})',
                    actions=[
                        cl.Action(name="continue", payload={
                                  "value": "continue"}, label="✅ Continue"),
                        cl.Action(name="feedback", payload={
                                  "value": "feedback"}, label="💬 Provide feedback"),
                        cl.Action(name="exit", payload={
                                  "value": "exit"}, label="🔚 Exit Conversation"),
                    ],
                )
            )
            user_selection = res.get("payload", {}).get("value", "")
            logger.info(
                f"[ChainlitConversableAgent] User selected action: {user_selection}")
            if user_selection == "continue":
                cl.run_sync(cl.Message(content=f'Calling {self.name}', author=self.name).send())
                return ""
            if user_selection == "exit":
                return "exit"

        logger.info(
            "[ChainlitConversableAgent] Requesting text input from user.")
        reply = cl.run_sync(ask_helper(
            cl.AskUserMessage, content=prompt, timeout=60))
        user_text = reply.get("output", "").strip()
        logger.info(f"[ChainlitConversableAgent] User input: {user_text}")
        return user_text


class ChainlitGroupChatManager(GroupChatManager):
    def _process_received_message(self, message: Union[Dict, str], sender: Agent, silent: bool):
        logger.info(
            f"[ChainlitGroupChatManager] Processing message from {sender.name}, silent={silent}")
        logger.info(f"[ChainlitGroupChatManager] Message content: {message}")
        cl.run_sync(
            cl.Message(
                content=f'*{sender.name}:*\n\n{message}',
                author=sender.name,
            ).send()
        )
        super(ChainlitGroupChatManager, self)._process_received_message(
            message=message,
            sender=sender,
            silent=silent,
        )


class ChainlitGroupChat(GroupChat):
    def manual_select_speaker(self, agents: Optional[List[Agent]] = None) -> Union[Agent, None]:
        if agents is None:
            agents = self.agents
        logger.info(
            f"[ChainlitGroupChat] manual_select_speaker called with {len(agents)} agents.")

        actions = [
            cl.Action(
                name="select",
                payload={"value": str(i + 1)},
                label=f"{i + 1}: {agent.name}"
            )
            for i, agent in enumerate(agents)
        ]
        actions.append(
            cl.Action(
                name="auto",
                payload={"value": "auto"},
                label="Auto Select"
            )
        )

        res = cl.run_sync(
            ask_helper(
                cl.AskActionMessage,
                content="Select the next speaker:",
                actions=actions,
                timeout=60
            )
        )
        user_choice = res.get("payload", {}).get("value", "")
        logger.info(
            f"[ChainlitGroupChat] User selected next speaker: {user_choice}")

        if user_choice == "auto":
            logger.info(
                "[ChainlitGroupChat] 'auto' selected, returning None for auto selection.")
            return None
        index = int(user_choice)
        selected_agent = agents[index - 1]
        logger.info(
            f"[ChainlitGroupChat] Selected agent: {selected_agent.name}")
        return selected_agent
