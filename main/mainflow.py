import json
import os
import chromadb
import agentops

from typing import Dict, List
from autogen import Agent, GroupChat, GroupChatManager, UserProxyAgent, AssistantAgent, register_function
from autogen.coding import DockerCommandLineCodeExecutor
from autogen.agentchat.contrib.retrieve_user_proxy_agent import RetrieveUserProxyAgent
from dotenv import load_dotenv
from typing_extensions import Annotated
from functions import get_tool_documentation, parse_mmls_output

# agentops.init(
#     api_key='600f3b0c-8959-4193-b38c-ee761888360d',
#     default_tags=['autogen']
# )

# Load environment variables from .env file
load_dotenv()
load_dotenv("./.env.local", override=True)

config_list = []

for model in os.getenv("LLM_MODEL").split(","):
    config_list.append(
        {
            "model": model,
            "client_host": os.getenv("LLM_BASE_URL"),
            "api_type": "ollama",
            "timeout": int(os.getenv("LLM_TIMEOUT", 500)),  # Default timeout if not set
            "temperature": 0.0,
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
task_translation_agent = AssistantAgent(
    name="Task_Translation_Agent",
    system_message=(
        """You are an expert in The Sleuth Kit (TSK) commands. Your goal is to break down the user's task into smaller actionable steps.
        DO NOT summarize the context or provide explanations beyond what is needed to complete the task.
        Break down the task step by step, ensuring each step uses a specific SleuthKit command from the context.
        Output one step at a time think about the result that is given to you and generate the next step.
        
        To analyze a disk image follow the steps in order,
        1. Analyze Disk Image Structure (Output: Starting offsets for partitions or 0 if no partition)
        2. Identify File System Type (Input : offset for the partition, Output: File system type for each partition)
        3. Discover Deleted Files (Input : file system type and Offset to partition, Output: file names and inode numbers)
        4. Execute File Recovery (Input : file system type, offset and inode numbers, Output: recovered file)
        
        Use the following structure to solve tasks:
            1. **Thought**: Analyze the task and determine the best SleuthKit commands or sequence to solve it.
            2. **Action**: Select the appropriate command(s) and inputs required for the command(s) to use and justify your choice.
            3. **Observation**: I will perform the action. Analyze the results. If further action is needed, continue with the next step.
            
        Important:
        1. Call one tool at a time
        2. Always follow the steps in order
            """
    ),
    llm_config=config_list[0],
)

# RAG Proxy Agent setup for command retrieval
rag_proxy_agent = RetrieveUserProxyAgent(
    name="RAG_Proxy_Agent",
    human_input_mode="NEVER",
    system_message="Retrieve only the most relevant SleuthKit commands and details for solving the user's task. "
                   "Provide precise commands and their explanations without additional interpretation.",
    max_consecutive_auto_reply=3,
    retrieve_config={
        "task": "QA",
        "docs_path": [os.path.join(os.path.abspath(""), "sleuthkit_commands.txt"),
                      os.path.join(os.path.abspath(""), "sleuthkit_book.pdf")],
        "custom_text_types": ["txt", "pdf"],
        "chunk_token_size": 2000,
        "model": llm_config["config_list"][0]["model"],
        "client": chromadb.PersistentClient(path="/tmp/chromadb"),
        "embedding_model": "all-mpnet-base-v2",
        "get_or_create": True,
        "must_break_at_empty_line": False,
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
        rag_proxy_agent.n_results = n_results  # Set the number of results to be retrieved.
        rag_proxy_agent.retrieve_docs(problem=message, n_results=n_results)
        retrieved_docs = rag_proxy_agent._results
        result = [entry[0]['content'] for entry in retrieved_docs[0]]
        # ret_msg = rag_proxy_agent.message_generator(rag_proxy_agent, None, _context)
        return result or message

# Coder Agent setup
coder_agent = AssistantAgent(
    name="Coder_Writer_Agent",
    code_execution_config=False,
    human_input_mode="ALWAYS",
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
 
    For each task:
    - **Thought**: Break down the coding task into logical steps, considering dependencies and requirements.
    - **Action**: Write the code, explaining your approach to ensure clarity.
    - **Observation**: If code execution reveals any issues, analyze and iterate.
    
    Example:
    
    Task: "Extract and save deleted file names to a text file."
    Thought: "I need to list deleted files using `fls`, then write the output to a file."
    Action:
    ```sh
    # filename: deleted_files_extractor.sh
    fls -d /path/to/image > deleted_files.txt
    ```
    Observation: "Check the output file to confirm all deleted files are listed."
    """,
    llm_config=config_list[1],
)

# Create Code Executor Agent
code_executor_agent = UserProxyAgent(
    name="Code_Executor_Agent",
    code_execution_config={"executor": executor},
    default_auto_reply=
    "Please continue. If everything is done, reply 'TERMINATE'.",
)
# Create Reporter Agent
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
    llm_config=llm_config,
)

# Admin
user_proxy = UserProxyAgent(
    name="Admin",
    system_message="A human admin. Review the outputs from the agents.",
    code_execution_config=False,

)

def getImageInfo(image_location:Annotated[str, "Image Location"]) -> str:
    """Identify the partition offsets using mmls and return the results"""
    codeMessage = f"""```sh
                    mmls {image_location}
                    ```"""
    raw_output = getCodeOutput(codeMessage)
    result = parse_mmls_output(raw_output)
    json_output = json.dumps(result, indent=2)
    
    return json_output
def identifyFileSystem(image_location: Annotated[str, "Image Location"], 
                      offset: Annotated[str, "Partition Offset"]) -> str:
    """Identify file system type using fsstat and return the results"""
    codeMessage = f"""```sh
                    fsstat -o {offset} {image_location}
                    ```"""
    output = getCodeOutput(codeMessage)
    return output

def listDeletedFiles(image_location: Annotated[str, "Image Location"], 
                    offset: Annotated[str, "Partition Offset"]) -> str:
    """List deleted files using fls and return the results"""
    codeMessage = f"""```sh
                    fls -d -o {offset} {image_location}
                    ```"""
    output = getCodeOutput(codeMessage)
    return output

def recoverFile(image_location: Annotated[str, "Image Location"], 
               offset: Annotated[str, "Partition Offset"],
               inode: Annotated[str, "Inode Number"],
               output_file: Annotated[str, "Output File Name"]) -> str:
    """Recover a file using icat based on inode number"""
    codeMessage = f"""```sh
                    icat -o {offset} {image_location} {inode} > {output_file}
                    ```"""
    output = getCodeOutput(codeMessage)
    return f"File recovered to {output_file}"

def getCodeOutput(codeMessage):
    code_blocks = executor.code_extractor.extract_code_blocks(message=codeMessage)
    code_output = executor.execute_code_blocks(code_blocks=code_blocks)
    return code_output.output

# register_function(
#     get_tool_documentation,
#     caller=coder_agent,
#     executor=user_proxy,
#     name="get_tool_documentation",
#     description="Get the documentation for the Sleuth kit command line tool",
# )
# register_function(
#     retrieve_content,
#     caller=task_translation_agent,
#     executor=user_proxy,
#     name="retrieve_content",
#     description="retrieve content about TSK for code generation and question answering.",
# )
register_function(
    getImageInfo,
    caller=task_translation_agent,
    executor=user_proxy,
    name="getImageInfo",
    description="Get the partition information of the disk image.",
)
register_function(
    identifyFileSystem,
    caller=task_translation_agent,
    executor=user_proxy,
    name="identifyFileSystem",
    description="Identify the file system type of a partition.",
)

register_function(
    listDeletedFiles,
    caller=task_translation_agent,
    executor=user_proxy,
    name="listDeletedFiles",
    description="List deleted files in a partition.",
)

register_function(
    recoverFile,
    caller=task_translation_agent,
    executor=user_proxy,
    name="recoverFile",
    description="Recover a file based on its inode number.",
)
# Create a custom speaker selection function
def custom_speaker_selection_func(last_speaker: Agent, groupchat: GroupChat):
    messages = groupchat.messages

    if len(messages) <= 1:
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
    else:
        # Default fallback
        return "manual"

# Create the GroupChat with agents
groupchat = GroupChat(
    agents=[rag_proxy_agent,task_translation_agent, coder_agent, code_executor_agent, reporter_agent, user_proxy],
    messages=[],
    max_round=40,
    speaker_selection_method=custom_speaker_selection_func,
)

# Initialize GroupChatManager
manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)


# Start the conversation by sending a task to the Task Translation Agent
user_proxy.initiate_chat(
    manager, message="""Examine the deleted files in the disk image using the sleuthkit command line tools. Come up with the list of files, the partition they are located and assign a priority to each.    
image_location: ./dataset/test_image.dd"""
)