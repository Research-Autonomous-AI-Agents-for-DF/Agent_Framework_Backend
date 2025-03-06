import chainlit as cl

from typing import List, Optional, Union, Dict
from autogen import Agent, GroupChat, GroupChatManager, UserProxyAgent, AssistantAgent, ConversableAgent
from autogen.agentchat.contrib.retrieve_user_proxy_agent import RetrieveUserProxyAgent

async def ask_helper(func, **kwargs):
    res = await func(**kwargs).send()
    while not res:
        res = await func(**kwargs).send()
    return res

class ChainlitConversableAgent(ConversableAgent):
    def get_human_input(self, prompt: str) -> str:
        if "Press enter to skip and use auto-reply, or type 'exit' to end the conversation:" in prompt:
            res = cl.run_sync(
                ask_helper(
                    cl.AskActionMessage,
                    content=f'*AI Agent Framework:*\n\nContinue or provide feedback? (Next agent is {self.name})',
                    actions=[
                        cl.Action(
                            name="continue", payload={"value": "continue"}, label="✅ Continue"
                        ),
                        cl.Action(
                            name="feedback",
                            payload={"value": "feedback"},
                            label="💬 Provide feedback",
                        ),
                        cl.Action( 
                            name="exit",
                            payload={"value": "exit"}, 
                            label="🔚 Exit Conversation" 
                        ),
                    ],
                )
            )
            if res.get("payload").get("value") == "continue":
                cl.run_sync(cl.Message(content=f'Calling {self.name}', author=self.name).send())
                return ""
            if res.get("payload").get("value") == "exit":
                return "exit"

        reply = cl.run_sync(ask_helper(cl.AskUserMessage, content=prompt, timeout=60))
        return reply["output"].strip()
class ChainlitGroupChatManager(GroupChatManager):
    def _process_received_message(self, message: Union[Dict, str], sender: Agent, silent: bool):
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
        user_choice = res.get("payload").get("value")
        if user_choice == "auto":
            return None
        index = int(user_choice)
        return agents[index-1]