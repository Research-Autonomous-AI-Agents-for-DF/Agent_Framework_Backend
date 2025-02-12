import asyncio
import os
import chromadb
import chainlit as cl

from autogen import Agent, GroupChat, GroupChatManager, UserProxyAgent, AssistantAgent, register_function, \
    ConversableAgent
from autogen.coding import DockerCommandLineCodeExecutor
from dotenv import load_dotenv
from functions import get_tool_documentation, ask_human_expert
from autogen.agentchat.contrib.capabilities import transform_messages, transforms
from chainlit_classes import ChainlitAssistantAgent, ChainlitRagProxyAgent, ChainlitUserProxyAgent, ChainlitGroupChat, \
    ChainlitGroupChatManager

# Load environment variables from .env file
load_dotenv()
load_dotenv("./.env.local", override=True)

TASK = """Examine the deleted files in the disk image using the sleuthkit command line tools. Come up with the list of files, the partition they are located and assign a priority to each.
image_location: ./dataset/test_image.dd"""


@cl.on_chat_start
async def on_chat_start():
    await cl.Message(
        content="### 🌟 Welcome to the AI Agent Framework! \n\n"
                "This tool allows you to interact with AI-driven agents to perform various tasks."
    ).send()

    action = await cl.AskActionMessage(
        content="Click the button below to start.",
        actions=[
            cl.Action(name="start_chat", payload={"value": "start_chat"}, label="🚀 Start Chat")
        ]
    ).send()

    if action.get("name") == "start_chat":
        await cl.Message(content=f"🔄 Starting agents on task: {TASK}...").send()

        # Se,perate process to start agents to avoid blocking the main process
        asyncio.create_task(start_agents())


async def start_agents():
    await cl.Message(content=f"Starting agents on task: {TASK}...").send()
    config_list = []

    for model in os.getenv("LLM_MODEL").split(","):
        config_list.append(
            {
                "model": model,
                "base_url": os.getenv("LLM_BASE_URL"),
                "api_key": os.getenv("LLM_API_KEY"),
                "timeout": int(os.getenv("LLM_TIMEOUT", 300)),  # Default timeout if not set
            }
        )
    llm_config = {
        "config_list": config_list,
    }
    executor = DockerCommandLineCodeExecutor(
        image="resistor52/sleuthkit:latest",  # Execute code using the given docker image name.
        timeout=40,  # Timeout for each code execution in seconds.
        work_dir="coding",  # Use the temporary directory to store the code files.
    )
    # Create Task Translation Agent
    task_translation_agent = ChainlitAssistantAgent(
        name="Task_Translation_Agent",
        system_message=(
            """You are an expert in SleuthKit commands. Your goal is to break down the user's task into smaller actionable steps.
            Use the provided context strictly to identify commands relevant to the task and describe how to use them.
            DO NOT summarize the context or provide explanations beyond what is needed to complete the task.
            Break down the task step by step, ensuring each step uses a specific SleuthKit command from the context.
            Output one step at a time think about the result that is given to you and generate the next step.

            To analyze a disk image,
            1. Identify the offsets for each partition (Write a bash code block using the mmls tool from TSK(The Sleuth Kit)).
            2. Using the offsets, use a bash code block of the TSK tool to perform the task.

            Use the following structure to solve tasks:
                1. **Thought**: Analyze the task and determine the best SleuthKit commands or sequence to solve it.
                2. **Action**: Select the appropriate command(s) to use and justify your choice.
                3. **Observation**: After performing the action, analyze the results. If further action is needed, continue with the next step.
            """
        ),
        llm_config=config_list[0],
        human_input_mode="ALWAYS"
    )
    # RAG Proxy Agent setup for command retrieval
    rag_proxy_agent = ChainlitRagProxyAgent(
        name="RAG_Proxy_Agent",
        human_input_mode="NEVER",
        system_message="Retrieve only the most relevant SleuthKit commands and details for solving the user's task. "
                       "Provide precise commands and their explanations without additional interpretation.",
        max_consecutive_auto_reply=3,
        retrieve_config={
            "task": "qa",
            "docs_path": [os.path.join(os.path.abspath(""), "sleuthkit_commands.txt"),
                          os.path.join(os.path.abspath(""), "tsk_Tool_Overview.html")],
            "custom_text_types": ["txt", "html"],
            "chunk_token_size": 100,
            "model": llm_config["config_list"][0]["model"],
            "client": chromadb.PersistentClient(path="/tmp/chromadb"),
            "embedding_model": "all-mpnet-base-v2",
            "get_or_create": True,
            "must_break_at_empty_line": False,
            "context_max_tokens": 1000
        },
        code_execution_config=False,
    )

    # Coder Agent setup
    coder_agent = ChainlitAssistantAgent(
        name="Coder_Writer_Agent",
        llm_config=config_list[0],
        code_execution_config=False,
        human_input_mode="ALWAYS",
        system_message="""You are a helpful AI assistant.
    Solve tasks using your coding and language skills.
    In the following case, suggest a shell script (in a bash coding block) for the user to execute.
        1. When you need to perform some task with code, use the code to perform the task and output the result. Finish the task smartly.
    Solve the task step by step if you need to. If a plan is not provided, explain your plan first. Be clear which step uses code, and which step uses your language skill.
    When using code, you must indicate the script type in the code block. The user cannot provide any other feedback or perform any other action beyond executing the code you suggest. The user can't modify your code. So do not suggest incomplete code which requires users to modify. Don't use a code block if it's not intended to be executed by the user.
    If you want the user to save the code in a file before executing it, put # filename: <filename> inside the code block as the first line. Don't include multiple code blocks in one response. Do not ask users to copy and paste the result. Instead, use 'print' function for the output when relevant. Check the execution result returned by the user.
    If the result indicates there is an error, fix the error and output the code again. Suggest the full code instead of partial code or code changes. If the error can't be fixed or if the task is not solved even after the code is executed successfully, analyze the problem, revisit your assumption, collect additional info by asking the user if you need, and think of a different approach to try.
    When you find an answer, verify the answer carefully. Include verifiable evidence in your response if possible.

    Call get_tool_documentation to get the documentation for a sleuth kit command line tool.
    Reply "TERMINATE" in the end when everything is done.
        """
    )

    context_handling = transform_messages.TransformMessages(
        transforms=[
            transforms.MessageHistoryLimiter(max_messages=3),
        ]
    )
    context_handling.add_to_agent(coder_agent)

    # Create Code Executor Agent
    code_executor_agent = ChainlitUserProxyAgent(
        name="Code_Executor_Agent",
        code_execution_config={"executor": executor},
        default_auto_reply=
        "Please continue. If everything is done, reply 'TERMINATE'.",
    )
    # Create Reporter Agent
    reporter_agent = ChainlitAssistantAgent(
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
    user_proxy = ChainlitUserProxyAgent(
        name="Admin",
        system_message="A human admin. Review the outputs from the agents.",
        code_execution_config=False,

    )

    # Create a custom speaker selection function
    def custom_speaker_selection_func(last_speaker: Agent, groupchat: GroupChat):
        messages = groupchat.messages

        if last_speaker is rag_proxy_agent:
            return task_translation_agent
        # direct all function calls to user_proxy
        if messages[-1].get("tool_calls") is not None:
            return user_proxy
        # direct all function results to task_translation_agent
        if messages[-1].get("role") == "tool":
            return coder_agent
        if last_speaker is task_translation_agent:
            if "UPDATE CONTEXT" in messages[-1]["content"]:
                return rag_proxy_agent;
            return code_executor_agent
        # elif last_speaker is code_executor_agent:
        #     # Check if execution was successful or failed
        #     if "execution failed" in messages[-1]["content"] or "failed" in messages[-1]["content"] or "change" in messages[-1]["content"] or "Error" in messages[-1]["content"]:
        #         return coder_agent  # Retry with the Coder Agent if failed

        #     # If successful, go back to Task Translation Agent for the next task
        #     if "execution successful" in messages[-1]["content"] or "success" in messages[-1]["content"] or "succeed" in messages[-1]["content"]:
        #         return task_translation_agent
        elif last_speaker is coder_agent:
            # If coder agent is used, go back to Task Translation Agent for the next task
            return task_translation_agent
        # elif last_speaker is reporter_agent:
        #     # Once all tasks are completed, switch to manual mode for final review
        #     return "manual"

        else:
            # Default fallback
            return "manual"

    # Create the GroupChat with agents
    groupchat = ChainlitGroupChat(
        agents=[rag_proxy_agent, task_translation_agent, coder_agent, code_executor_agent, reporter_agent, user_proxy],
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
    # register_function(
    #     ask_human_expert,
    #     caller=task_translation_agent,
    #     executor=user_proxy,
    #     name="ask_human_expert",
    #     description="Ask human expert for help in the task"
    # )

    await cl.make_async(rag_proxy_agent.initiate_chat)(
        manager,
        message=rag_proxy_agent.message_generator,
        problem=TASK
    )
