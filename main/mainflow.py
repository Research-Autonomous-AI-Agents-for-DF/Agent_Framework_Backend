import autogen
from typing import Dict, List
from autogen import Agent, GroupChat, GroupChatManager, UserProxyAgent, AssistantAgent
from autogen.agentchat.contrib.retrieve_user_proxy_agent import RetrieveUserProxyAgent
from autogen.coding import DockerCommandLineCodeExecutor
import os
import chromadb
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
load_dotenv("../.env.local", override=True)

# Define the LLM configuration
llm_config = {
    "config_list": [
        {
            "model": os.getenv("LLM_MODEL"),
            "base_url": os.getenv("LLM_BASE_URL"),
            "api_key": os.getenv("LLM_API_KEY"),
            "seed": int(os.getenv("LLM_SEED", 25)),  # Default seed if not set
            "timeout": int(os.getenv("LLM_TIMEOUT", 300))  # Default timeout if not set
        }
    ]
}
executor = DockerCommandLineCodeExecutor(
    image="resistor52/sleuthkit:latest",  # Execute code using the given docker image name.
    timeout=40,  # Timeout for each code execution in seconds.
    work_dir="coding",  # Use the temporary directory to store the code files.
)

# Create Task Translation Agent
task_translation_agent = AssistantAgent(
    name="Task_Translation_Agent",
    system_message="""
    You are an expert in SleuthKit commands. Your goal is to break down the user's task into smaller actionable steps. "
        "Use the provided context strictly to identify commands relevant to the task and describe how to use them. "
        "DO NOT summarize the context or provide explanations beyond what is needed to complete the task. "
        "Break down the task step by step, ensuring each step uses a specific SleuthKit command from the context.
    
    
    You are an expert in using the SleuthKit library. You are knowledgeable about SleuthKit 
    commands and can reason through complex forensic tasks.
    
    Use the following structure to solve tasks:
    
    1. **Thought**: Analyze the task and determine the best SleuthKit commands or sequence to solve it.
    2. **Action**: Select the appropriate command(s) to use and justify your choice.
    3. **Observation**: After performing the action, analyze the results. If further action is needed, continue with the next step.
    
    Example:
    
    Task: "Identify deleted files in a disk image."
    Thought: "To find deleted files, I should use `fls` to list files, including deleted entries."
    Action: "I will run `fls -d /path/to/image` to list deleted files."
    Observation: "After listing, I will check if any recovered file names match the case requirements."
    .
""",
    llm_config=llm_config,
)

# RAG Proxy Agent setup for command retrieval
rag_proxy_agent = RetrieveUserProxyAgent(
    name="RAG_Proxy_Agent",
    human_input_mode="NEVER",
    system_message="""
    You are an expert in retrieving relevant information for digital forensic tasks using Sleuth Kit commands.
    Use the ReAct framework to reason through the task, identify the most relevant sections of the documents, 
    and provide precise information to support the task.
    
    Follow these steps:
    1. **Thought**: Analyze the task and determine the key information needed.
    2. **Action**: Formulate a retrieval query or select specific sections of the documents.
    3. **Observation**: Review the retrieved content for relevance and ensure it addresses the task.
    4. If necessary, iterate on the process to improve the results.
    
    Example:
    Task: "Retrieve the most relevant commands for listing deleted files."
    Thought: "To list deleted files, commands like `fls -d` and `ils` might be relevant."
    Action: "Retrieve sections related to `fls` and `ils` from the documents."
    Observation: "The retrieved sections include syntax and examples for these commands."
    
    Provide your results clearly, focusing only on the requested context.
    """,
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

# Coder Agent setup
coder_agent = AssistantAgent(
    name="Coder_Writer_Agent",
    llm_config=llm_config,
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


# Create a custom speaker selection function
def custom_speaker_selection_func(last_speaker: Agent, groupchat: GroupChat):
    messages = groupchat.messages
    if len(messages) <= 1:
        # Extract the 'content' field from the first message
        first_message_content = messages[0].get('content', '')

        # Retrieve documents
        rag_proxy_agent.retrieve_docs(problem=first_message_content)
        retrieved_docs = rag_proxy_agent.results
        # `retrieved_contents` contains all the extracted 'content' strings from retrivd_docs
        retrieved_contents = [entry[0]['content'] for entry in retrieved_docs[0]]

        print("retrieved_contents:", retrieved_contents)

        groupchat.messages.append({
            "content": f"Retrieved Context:\n{retrieved_contents}",
            "role": "agent",
            "name": "RAG_Proxy_Agent"
        })
        # print('after append the group massage', groupchat.messages)

        # Next speaker: Task Translation Agent
        return task_translation_agent

    if last_speaker is task_translation_agent:
        return coder_agent

    elif last_speaker is coder_agent:
        # After Coder Agent, human input is required
        if "Human" in messages[-1]["content"]:
            return "manual"  # Switch to manual mode for human input
        return code_executor_agent

    elif last_speaker is code_executor_agent:

        if "execution failed" in messages[-1]["content"] or "failed" in messages[-1]["content"] or "change" in \
                messages[-1]["content"]:
            print("It works")
            return coder_agent
        return reporter_agent

    elif last_speaker is reporter_agent:
        return "manual"  # End the chat, switch to manual for final review

    else:
        return "random"  # Default fallback


# Create the GroupChat with agents
groupchat = GroupChat(
    agents=[rag_proxy_agent, task_translation_agent, coder_agent, code_executor_agent, reporter_agent],
    messages=[],
    max_round=20,
    speaker_selection_method=custom_speaker_selection_func,
)

# Initialize GroupChatManager
manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)

# Start the conversation by sending a task to the Task Translation Agent
user_proxy = UserProxyAgent(
    name="Admin",
    system_message="A human admin. Review the outputs from the agents.",
    code_execution_config=False,

)

user_proxy.initiate_chat(
    manager, message="Examine the disk image in the dataset folder of the current working directory named "
                     "'dfr-01-ntfs.dd' using the sleuthkit commands. Use the tsk 4 and tsk 3 command lists and come up "
                     "with a list of deleted file names. Store them in file named 'deleted_files.txt'."
)
