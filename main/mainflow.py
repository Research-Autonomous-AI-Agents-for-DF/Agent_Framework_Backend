from typing import Annotated
from chainlit.context import context
from fastapi import HTTPException, Request
from chainlit.server import app  # Get the underlying FastAPI app
from fastapi.responses import FileResponse
import asyncio
from logging_config import logger, update_log_file
import os
import chromadb
import chainlit as cl
import pathlib

from autogen import Agent, GroupChat, register_function
from autogen.coding import DockerCommandLineCodeExecutor
from dotenv import load_dotenv
from functions import get_tool_documentation
from autogen.agentchat.contrib.capabilities import transform_messages, transforms
from chainlit_classes import ChainlitConversableAgent, ChainlitGroupChat, \
    ChainlitGroupChatManager
from autogen.agentchat.contrib.retrieve_user_proxy_agent import RetrieveUserProxyAgent
from chainlit.context import CL_RUN_NAMES, context, local_steps
import threading
from download_server import run_download_server

# Load environment variables from .env file
load_dotenv()
load_dotenv("./.env.local", override=True)


logger.info("=== Chainlit + Autogen Logging Initialized ===")

# Start the download server in a separate thread
download_thread = threading.Thread(target=run_download_server, daemon=True)
download_thread.start()

print("Download server is running on http://127.0.0.1:8001")

TASK = """Examine the deleted files in the disk image using the sleuthkit command line tools. Come up with the list of files, the partition they are located and assign a priority to each.
image_location: ./dataset/test_image.dd"""

# Loading cocnfig list
config_list = []

for model in os.getenv("LLM_MODEL").split(","):
    config_list.append(
        {
            "model": model,
            "base_url": os.getenv("LLM_BASE_URL"),
            "api_key": os.getenv("LLM_API_KEY"),
            # Default timeout if not set
            "timeout": int(os.getenv("LLM_TIMEOUT", 300)),
        }
    )
llm_config = {
    "config_list": config_list,
}

# Setting up executor
executor = DockerCommandLineCodeExecutor(
    # Execute code using the given docker image name.
    image="resistor52/sleuthkit:latest",
    timeout=40,  # Timeout for each code execution in seconds.
    work_dir="coding",  # Use the temporary directory to store the code files.
)

# Create Task Translation Agent
task_translation_agent = ChainlitConversableAgent(
    name="Task_Translation_Agent",
    system_message=(
        """You are an expert in SleuthKit commands. Your goal is to break down the user's task into smaller actionable steps.
        Use the provided context strictly to identify commands relevant to the task and describe how to use them.
        DO NOT summarize the context or provide explanations beyond what is needed to complete the task.
        Break down the task step by step, ensuring each step uses a specific SleuthKit command from the context.
        Output one step at a time think about the result that is given to you and generate the next step.

        To analyze a disk image,
        1. Identify the offsets for each partition (Suggest using the mmls tool from TSK(The Sleuth Kit)).
        2. Using the offsets, suggest the most suitable TSK tool from the context to perform the task.

        Use the following structure to solve tasks:
            1. **Thought**: Analyze the task and determine the best SleuthKit commands or sequence to solve it.
            2. **Action**: Select the appropriate command(s) and inputs required for the command(s) to use and justify your choice.
            3. **Observation**: I will perform the action. Analyze the results. If further action is needed, continue with the next step.

        eg:
        User's question is: What can you tell me about the partitions of the disk image?
        image_location: ./dataset/my_image.dd

        Context is:<h1 id="volume-system-tools">Volume System Tools</h1>
        <p>These tools take a disk (or other media) image as input and analyze its partition structures. Examples include DOS
            partitions, BSD disk labels, and the Sun Volume Table of Contents (VTOC). These can be used find hidden data between
            partitions and to identify the file system offset for The Sleuth Kit tools. The media management tools support DOS
            partitions, BSD disk labels, Sun VTOC, and Mac partitions.</p>
        <ul>
            <li><strong>mmls</strong>: Displays the layout of a disk, including the unallocated spaces.</li>
            <li><strong>mmstat</strong>: Display details about a volume system (typically only the type).</li>
            <li><strong>mmcat</strong>: Extracts the contents of a specific volume to STDOUT.</li>
        </ul>

        **Thought**: To examine the partitions in the disk image, we need to use a tool that can give us partition data. The two relevant SleuthKit tools for this purpose are `mmls` and `mmstat`. Since `mmls` extracts the layout of the entire disk, we can use this first to get the partition details.

        **Action**: Use `mmls` to extract the partition table from the disk image. You'll need image_location: ./dataset/my_image.dd as input

        Please wait for further instructions based on the output of `mmls`.
        """
    ),
    llm_config=config_list[1],
    human_input_mode="ALWAYS"
)

# RAG Proxy Agent setup for command retrieval
rag_proxy_agent = RetrieveUserProxyAgent(
    name="RAG_Proxy_Agent",
    human_input_mode="NEVER",
    system_message="Retrieve only the most relevant SleuthKit commands and details for solving the user's task. "
    "Provide precise commands and their explanations without additional interpretation.",
    max_consecutive_auto_reply=3,
    retrieve_config={
        "task": "qa",
        "docs_path": [os.path.join(os.path.abspath(""), "tsk_Tool_Overview.html")],
        "custom_text_types": ["html"],
        "chunk_token_size": 250,
        "model": llm_config["config_list"][0]["model"],
        "client": chromadb.PersistentClient(path="/tmp/chromadb"),
        "embedding_model": "all-mpnet-base-v2",
        "get_or_create": True,
        "must_break_at_empty_line": False,
        "context_max_tokens": 500
    },
    code_execution_config=False,
)

def retrieve_content(
        message: Annotated[
            str,
            "Refined message which keeps the original meaning and can be used to retrieve content for code generation and question answering.",
        ],
        n_results: Annotated[int, "number of results"] = 2,
    ) -> str:
        rag_proxy_agent.n_results = n_results
        rag_proxy_agent.retrieve_docs(problem=message, n_results=n_results)
        retrieved_docs = rag_proxy_agent._results
        result = [entry[0]['content'] for entry in retrieved_docs[0]]
        return result or message

# Coder Agent setup
coder_agent = ChainlitConversableAgent(
    name="Coder_Writer_Agent",
    llm_config=config_list[1],
    code_execution_config=False,
    human_input_mode="ALWAYS",
    system_message="""You are a helpful AI assistant.
I will give you a thought and an action that needs to be completed using a command from the sleuth kit (TSK). Solve tasks using your coding and language skills.
In the following case, suggest code (in a bash coding block) for the user to execute.
    1. When you need to perform some task with code, use the code to perform the task and output the result. Finish the task smartly.
Solve the task step by step if you need to. If a plan is not provided, explain your plan first. Be clear which step uses code, and which step uses your language skill.
When using code, you must indicate the script type in the code block. The user cannot provide any other feedback or perform any other action beyond executing the code you suggest. The user can't modify your code. So do not suggest incomplete code which requires users to modify. Don't use a code block if it's not intended to be executed by the user.
# filename: <filename> inside the code block as the first line. Don't include multiple code blocks in one response. Do not ask users to copy and paste the result. Instead, use 'echo' function for the output when relevant. Check the execution result returned by the user.
If you want the user to save the code in a file before executing it, put
If the result indicates there is an error, fix the error and output the code again. Suggest the full code instead of partial code or code changes. If the error can't be fixed or if the task is not solved even after the code is executed successfully, analyze the problem, revisit your assumption, collect additional info by asking the user if you need, and think of a different approach to try.
When you find an answer, verify the answer carefully. Include verifiable evidence in your response if possible.

Important
1. Always call get_tool_documentation to get the documentation for a TSK command line tool.
2. Use one TSK command at a time and that should be the only command in the shell script.
3. If you are generating a shell script, dont have any blank lines as it gets interpreted as \r in the terminal

Reply "TERMINATE" in the end when everything is done.
"""
)

context_handling = transform_messages.TransformMessages(
    transforms=[
        transforms.MessageHistoryLimiter(max_messages=4),
    ]
)
context_handling.add_to_agent(coder_agent)

# Create Code Executor Agent
code_executor_agent = ChainlitConversableAgent(
    name="Code_Executor_Agent",
    code_execution_config={"executor": executor},
    default_auto_reply="Please continue. If everything is done, reply 'TERMINATE'.",
)
# Create Reporter Agent
reporter_agent = ChainlitConversableAgent(
    name="Reporter_Agent",
    system_message="""
    You are a digital forensics expert responsible for generating comprehensive and accurate forensic reports. Your task is to summarize the findings, methodologies, and conclusions derived from the analysis of disk images and related data. The report should be structured as follows:

    1. **Executive Summary**: Provide a brief overview of the investigation, including the purpose, scope, and key findings.

    2. **Methodology**: Detail the tools, techniques, and commands used in the analysis, including any relevant parameters and configurations.

    3. **Findings**: Summarize the results of the analysis, including any files or data recovered, evidence of tampering or deletion, and other relevant artifacts. Include specific command outputs where necessary.

    4. **Analysis**: Provide a detailed interpretation of the findings, explaining the significance of the recovered data in the context of the investigation.

    5. **Conclusion**: Offer a summary of the conclusions drawn from the analysis, including any recommendations for further investigation or actions.

    6. **Appendices**: Include any additional materials, such as full command outputs, logs, or scripts, that support the findings and conclusions.

    Ensure that the report is clear, concise, and free of any technical jargon that might confuse a non-expert reader. Include timestamps and references to specific data sources where applicable. Aim for accuracy, clarity, and thoroughness in every section of the report.
    """,
    llm_config=llm_config,
)
# Admin
user_proxy = ChainlitConversableAgent(
    name="Admin",
    system_message="A human admin. Review the outputs from the agents.",
    code_execution_config=False,
    human_input_mode="ALWAYS",
)

# Create a custom speaker selection function


def custom_speaker_selection_func(last_speaker: Agent, groupchat: GroupChat):
    messages = groupchat.messages

    if last_speaker is rag_proxy_agent:
        return task_translation_agent
    #direct all function calls to user_proxy
    if messages[-1].get("tool_calls") is not None:
        return user_proxy
    #direct all function results to the agent that called the tool
    if messages[-1].get("role") == "tool":
        caller_agent_name = messages[-2]["name"]
        #get index from agent_names
        index = groupchat.agent_names.index(caller_agent_name)
        #apply that index to agents
        return groupchat.agents[index]
    elif last_speaker is code_executor_agent:
        # Check if execution was successful or failed
        if "execution failed" in messages[-1]["content"] or "failed" in messages[-1]["content"] or "change" in messages[-1]["content"] or "Error" in messages[-1]["content"]:
            return coder_agent  # Retry with the Coder Agent if failed

        # If successful, go back to Task Translation Agent for the next task
        if "execution successful" in messages[-1]["content"] or "success" in messages[-1]["content"] or "succeed" in messages[-1]["content"]:
            return task_translation_agent
    # elif last_speaker is coder_agent:
    #     # If coder agent is used, go back to Task Translation Agent for the next task
    #     return task_translation_agent
    # elif last_speaker is reporter_agent:
    #     # Once all tasks are completed, switch to manual mode for final review
    #     return "manual"

    else:
        # Default fallback
        return "manual"


# Create the GroupChat with agents
groupchat = ChainlitGroupChat(
    agents=[rag_proxy_agent, task_translation_agent, coder_agent,
            code_executor_agent, reporter_agent, user_proxy],
    messages=[],
    max_round=40,
    speaker_selection_method=custom_speaker_selection_func,
)

# Initialize GroupChatManager
manager = ChainlitGroupChatManager(groupchat=groupchat, llm_config=llm_config)

register_function(
    get_tool_documentation,
    caller=coder_agent,
    executor=user_proxy,
    name="get_tool_documentation",
    description="Get the documentation for the Sleuth kit command line tool",
)
register_function(
    retrieve_content,
    caller=coder_agent,
    executor=user_proxy,
    name="retrieve_content",
    description="retrieve content about TSK for code generation and question answering.",
)
@cl.password_auth_callback
def auth_callback(username: str, password: str):
    if (username, password) == ("admin", "admin"):
        return cl.User(
            identifier="admin", metadata={"role": "admin", "provider": "credentials"}
        )
    else:
        return None


@cl.on_chat_start
async def on_chat_start():
    logger.info("[CHAINLIT] Chat session started.")
    # Ask for the case number before starting
    await cl.Message(
        content="### 🌟 Welcome to the AI Agent Framework! \n\nThis tool allows you to interact with AI-driven agents to perform various tasks."
    ).send()
    res = await cl.AskUserMessage(
        content="📝 Please enter the case number for this chat:",
    ).send()

    case_number = None
    if res:
        case_number = res["output"].strip()

    if not case_number:
        await cl.Message(content="⚠️ A case number is required to start a chat.").send()
        return

    # Format case number
    if case_number.isdigit():
        case_number = f"{int(case_number):02d}"

    # Store the case number in the session
    cl.user_session.set("case_number", case_number)

    await cl.Message(
        content=f"✅ Case **{case_number}** recorded. You can now start chatting."
    ).send()
    message = await cl.Message(content="Loading agents....").send()
    await cl.sleep(5)
    message.content = """Type the task the framework should execute in the text box below. Follow this format
<Your query>
image_location: <image location>"""
    await message.update()


@cl.on_message
async def main(message: cl.Message):
    
    # Extract thread info from the Chainlit context.
    # Adjust cl.context retrieval if needed.
    chainlit_ctx = cl.context  # or cl.get_context() if that's your API
    thread_id = chainlit_ctx.session.thread_id
    logger.info(f"Thread ID: {thread_id}")

    # Update the log file for the current thread.
    update_log_file(thread_id)

    logger.info(f"[CHAINLIT] Received user message: {message.content}")
    message_content = message.content
    logger.info(f"[CHAINLIT] Processing user message: {message_content}")
    await cl.make_async(rag_proxy_agent.initiate_chat)(
        manager,
        message=rag_proxy_agent.message_generator,
        problem=message_content
    )
    logger.info("Finished processing the message")

@cl.on_chat_end
async def end():
    print("goodbye", cl.user_session.get("id"))
