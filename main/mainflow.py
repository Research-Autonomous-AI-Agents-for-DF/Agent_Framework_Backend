import asyncio
import streamlit as st
from typing import Dict, List, Sequence
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent, CodeExecutorAgent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.messages import ChatMessage, AgentEvent
from autogen_core import CancellationToken
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.code_executors.docker import DockerCommandLineCodeExecutor
from dotenv import load_dotenv
import os
import time

# Load environment variables
load_dotenv()
load_dotenv("../.env.local", override=True)

# Initialize model client
model_client = OpenAIChatCompletionClient(
    model="lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF/Meta-Llama-3.1-8B-Instruct-IQ4_XS.gguf",
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    seed=int(os.getenv("LLM_SEED", 25)),
    timeout=int(os.getenv("LLM_TIMEOUT", 300)),
    model_info={
        "vision": False,
        "function_calling": True,
        "json_output": False,
        "family": 'unknown',
    },
)

# Create code executor
executor = DockerCommandLineCodeExecutor(
    image="resistor52/sleuthkit:latest",
    timeout=40,
    work_dir="coding",
)

# Define agents
task_translation_agent = AssistantAgent(
    name="Task_Translation_Agent",
    system_message="""You are an expert in using the SleuthKit library. You have knowledge of all the shell commands in tsk4. You will break down complex tasks into smaller tasks that use these commands. You dont need to provide the code. Just break down the tasks according to the available commands and give the command for the task. Commands are
    blkcalc - Converts between unallocated disk unit numbers and regular disk unit numbers.
    blkcat - Display the contents of file system data unit in a disk image.
    blkls - List or output file system data units.
    blkstat - Display details of a file system data unit (i.e. block or sector).
    fcat - Output the contents of a file based on its name.
    ffind - Finds the name of the file or directory using a given inode.
    fiwalk - print the filesystem statistics and exit.
    fls - List file and directory names in a disk image.
    fsstat - Display general details of a file system.
    hfind - Lookup a hash value in a hash database.
    icat - Output the contents of a file based on its inode number.
    ifind - Find the meta-data structure that has allocated a given disk unit or file name.
    ils - List inode information.
    img_cat - Output contents of an image file.
    img_stat - Display details of an image file.
    istat - Display details of a meta-data structure (i.e. inode).
    jcat - Show the contents of a block in the file system journal.
    jls - List the contents of a file system journal.
    jpeg_extract - jpeg extractor.
    mactime - Create an ASCII time line of file activity.
    mmcat - Output the contents of a partition to stdout.
    mmls - Display the partition layout of a volume system (partition tables).
    mmstat - Display details about the volume system (partition tables).
    sigfind - Find a binary signature in a file.
    sorter - Sort files in an image into categories based on file type.
    srch_strings - Display printable strings in files.
    tsk_comparedir - compare the contents of a directory with the contents of an image or local device.
    tsk_gettimes - Collect MAC times from a disk image into a body file.
    tsk_loaddb - populate a SQLite database with metadata from a disk image.
    tsk_recover - Export files from an image into a local directory.
    """,
    model_client=model_client,
)

coder_agent = AssistantAgent(
    name="Coder_Writer_Agent",
    system_message=r"""You are a helpful AI assistant.
Solve tasks using your coding and language skills.
In the following cases, suggest python code (in a python coding block) or shell script (in a sh coding block) for the user to execute.
    1. When you need to collect info, use the code to output the info you need, for example, browse or search the web, download/read a file, print the content of a webpage or a file, get the current date/time, check the operating system. After sufficient info is printed and the task is ready to be solved based on your language skill, you can solve the task by yourself.
    2. When you need to perform some task with code, use the code to perform the task and output the result. Finish the task smartly.
Solve the task step by step if you need to. If a plan is not provided, explain your plan first. Be clear which step uses code, and which step uses your language skill.
When using code, you must indicate the script type in the code block. The user cannot provide any other feedback or perform any other action beyond executing the code you suggest. The user can't modify your code. So do not suggest incomplete code which requires users to modify. Don't use a code block if it's not intended to be executed by the user.
If you want the user to save the code in a file before executing it, put # filename: <filename> inside the code block as the first line. Don't include multiple code blocks in one response. Do not ask users to copy and paste the result. Instead, use 'print' function for the output when relevant. Check the execution result returned by the user.
If the result indicates there is an error, fix the error and output the code again. Suggest the full code instead of partial code or code changes. If the error can't be fixed or if the task is not solved even after the code is executed successfully, analyze the problem, revisit your assumption, collect additional info you need, and think of a different approach to try.
When you find an answer, verify the answer carefully. Include verifiable evidence in your response if possible.
Reply "TERMINATE" in the end when everything is done.
If you are generating a shell script, dont have any blank lines as it gets interpreted as \r in the terminal
""",
    model_client=model_client,
)

code_executor_agent = CodeExecutorAgent(
    name="Code_Executor_Agent",
    code_executor=executor
)

reporter_agent = AssistantAgent(
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
    model_client=model_client,
)

# Streamlit UI customization - moved outside of agent definition for clarity
user_proxy_description = """Human user. Please provide feedback on the task translation.
Type 'approve' to continue to code writing, 'redo' to revise the task translation."""


# UserProxyAgent with custom description for UI
user_proxy = UserProxyAgent(
    name="User_Proxy",
    description=user_proxy_description,
    input_func=lambda prompt: st.session_state.get('user_input_streamlit', ''),
)


def custom_speaker_selection(messages: Sequence[ChatMessage | AgentEvent]) -> str | None:
    print("--- custom_speaker_selection called ---")
    print(f"Message count: {len(messages)}")
    if len(messages) <= 1:
        print(f"  Initial message, returning: {task_translation_agent.name}")
        return task_translation_agent.name

    last_speaker = messages[-1].source if hasattr(
        messages[-1], "source") else None
    print(f"  Last speaker: {last_speaker}")

    if last_speaker == task_translation_agent.name:
        print(
            f"  Last speaker was Task_Translation_Agent. Setting get_input_flag=True, returning: {user_proxy.name}")
        st.session_state['get_input_flag'] = True
        return user_proxy.name

    if last_speaker == user_proxy.name:
        user_feedback = st.session_state.get(
            'user_input_streamlit')  # Get feedback - do NOT strip yet
        print(
            f"  Last speaker was User_Proxy. User feedback (raw): '{user_feedback}'")

        if user_feedback is not None and user_feedback.strip() != '':  # Check for None and empty string
            user_feedback_stripped = user_feedback.strip()  # Now strip for processing
            print(
                f"  User feedback provided: '{user_feedback_stripped}'. Clearing input_streamlit, resetting get_input_flag.")
            st.session_state['user_input_streamlit'] = ''
            st.session_state['get_input_flag'] = False
            if "approve" in user_feedback_stripped.lower():
                print(f"    Feedback 'approve', returning: {coder_agent.name}")
                return coder_agent.name
            elif "redo" in user_feedback_stripped.lower():
                print(
                    f"    Feedback 'redo', returning: {task_translation_agent.name}")
                return task_translation_agent.name
            else:
                print(
                    f"    Feedback (no keyword), returning: {coder_agent.name}")
                return coder_agent.name
        else:
            # More explicit message
            print(
                f"    No VALID user feedback yet (None or empty). Returning: None (pause)")
            return None  # Return None to pause when user_feedback is truly absent or empty

    if last_speaker == coder_agent.name:
        print(
            f"  Last speaker was Coder_Agent, returning: {code_executor_agent.name}")
        return code_executor_agent.name

    if last_speaker == code_executor_agent.name:
        if any(err in messages[-1].content.lower() for err in ["failed", "error", "change"]):
            print(
                f"  Last speaker was Code_Executor_Agent with error, returning: {coder_agent.name}")
            return coder_agent.name
        print(
            f"  Last speaker was Code_Executor_Agent, returning: {reporter_agent.name}")
        return reporter_agent.name

    if last_speaker == reporter_agent.name:
        print(f"  Last speaker was Reporter_Agent, returning: TERMINATE")
        return "TERMINATE"

    print(f"  No specific speaker condition met, returning: None (default pause - SHOULD NOT REACH HERE)")
    return None


# Create termination conditions
termination_conditions = (
    TextMentionTermination("TERMINATE") |
    MaxMessageTermination(max_messages=20)
)

# Create group chat
group_chat = SelectorGroupChat(
    participants=[
        task_translation_agent,
        coder_agent,
        code_executor_agent,
        reporter_agent,
        user_proxy
    ],
    selector_func=custom_speaker_selection,
    termination_condition=termination_conditions,
    model_client=model_client,
)


async def run_chat(task_description):
    # Initialize chat history for each run
    st.session_state['full_chat_history'] = []
    stream = group_chat.run_stream(task=task_description)
    async for item in stream:
        st.session_state['full_chat_history'].append(
            item)  # Append all message events to history
        yield item  # Yield each item for stream processing in UI


# --- Asynchronous UI Streaming Function ---
async def stream_to_ui(chat_transcript):
    chat_stream_gen = st.session_state.get('chat_stream_gen', None)
    if chat_stream_gen:
        async for item in chat_stream_gen:
            # Append the item to full chat history.
            st.session_state['full_chat_history'].append(item)
            with chat_transcript:
                # Try to display the item; if it lacks 'source', assume it contains a list of messages.
                if hasattr(item, "source") and hasattr(item, "content"):
                    st.markdown(f"**{item.source}:** {item.content}")
                elif hasattr(item, "messages"):
                    for m in item.messages:
                        st.markdown(f"**{m.source}:** {m.content}")
                else:
                    st.markdown(f"**Item:** {item}")
            # Check for termination (assuming a message with content "TERMINATE" signals termination)
            if hasattr(item, "content") and item.content == "TERMINATE":
                st.session_state['chat_task_running'] = False

# --- Main Function ---


def main():
    st.title("SleuthKit Forensics Agent Chat")

    # Initialize session state variables if not already set.
    if 'full_chat_history' not in st.session_state:
        st.session_state['full_chat_history'] = []
    if 'user_input_streamlit' not in st.session_state:
        st.session_state['user_input_streamlit'] = None  # Initialize to None
    if 'get_input_flag' not in st.session_state:
        st.session_state['get_input_flag'] = False
    if 'chat_task_running' not in st.session_state:
        st.session_state['chat_task_running'] = False
    if 'chat_stream_gen' not in st.session_state:
        st.session_state['chat_stream_gen'] = None

    # Create containers for the chat transcript and input area.
    chat_transcript = st.container()
    input_area = st.empty()

    # Display the current chat transcript.
    with chat_transcript:
        for item in st.session_state['full_chat_history']:
            if hasattr(item, "source") and hasattr(item, "content"):
                st.markdown(f"**{item.source}:** {item.content}")
            elif hasattr(item, "messages"):
                for m in item.messages:
                    st.markdown(f"**{m.source}:** {m.content}")
            else:
                st.markdown(f"**Item:** {item}")

    # If waiting for human input, show a text input widget and a submit button.
    if st.session_state['get_input_flag']:
        with input_area:
            user_input = st.text_input(
                "Please provide feedback (e.g., approve/redo):", key="user_input")
            if st.button("Submit Feedback"):
                if user_input and user_input.strip():  # Check for non-empty input
                    st.session_state['user_input_streamlit'] = user_input
                    st.experimental_rerun()
                else:
                    # Optional warning
                    st.warning("Please provide feedback before submitting.")

    else:
        # When not waiting for human feedback and if no chat task is running, show the task input area.
        if not st.session_state['chat_task_running']:
            task_input = st.text_area(
                "Enter your forensics task for SleuthKit:", height=100, key="task_input_area")
            if st.button("Start Task"):
                if task_input.strip():
                    st.session_state['chat_task_running'] = True
                    st.session_state['full_chat_history'] = []
                    st.session_state['chat_stream_gen'] = run_chat(task_input)
                    chat_transcript.empty()
                    asyncio.run(stream_to_ui(chat_transcript))


if __name__ == "__main__":
    main()
