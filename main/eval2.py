
import json
import os
from autogen.agentchat import groupchat
from typing import List, Dict
import chainlit as cl
import autogen
from autogen.agentchat.contrib.agent_eval.agent_eval import generate_criteria, quantify_criteria
from autogen.agentchat.contrib.agent_eval.criterion import Criterion
from autogen.agentchat.contrib.agent_eval.task import Task
from pydantic import ValidationError

from main.mainflow import rag_proxy_agent, manager
# Function to remove ground truth from test cases

config_list = [{
    "model": os.getenv("LLM_MODEL"),
    "base_url": os.getenv("LLM_BASE_URL"),
    "api_key": os.getenv("LLM_API_KEY"),
}]


def remove_ground_truth(test_case):
    test_details = json.loads(test_case)
    correctness = test_details.pop("is_correct", None)
    test_details.pop("correct_ans", None)
    test_details.pop("check_result", None)
    return json.dumps(test_details), correctness

# Load successful and failed examples
success_str = open("D:\\4thYear\\Research\\Devlopment\\git_2\\Agent_Framework_Backend\\Evaluation\\sample_forensic_response_successful.txt", "r").read()
response_successful, _ = remove_ground_truth(success_str)

failed_str = open("D:\\4thYear\\Research\\Devlopment\\git_2\\Agent_Framework_Backend\\Evaluation\\sample_forensic_response_failed.txt", "r").read()
response_failed, _ = remove_ground_truth(failed_str)

# Define the task
task = Task(
    **{
        "name": "Forensic Analysis",
        "description": "Analyze disk images using SleuthKit to recover deleted files and identify partitions",
        "successful_response": response_successful,
        "failed_response": response_failed,
    }
)

criteria = generate_criteria(task=task, llm_config={"config_list": config_list}, max_round=8)




# Save criteria to a file
current_task_name = "_".join(task.name.split()).lower()
print(current_task_name)
cr_file = open(f"D:\\4thYear\\Research\\Devlopment\\git_2\\Agent_Framework_Backend\\Evaluation\\{current_task_name}_criteria.json", "w")
cr_file.write(Criterion.write_json(criteria))
print(f"Criteria saved to {current_task_name}_criteria.json")
cr_file.close()
    # cr_file.write(json.dumps(criteria, indent=2))


import os
from pathlib import Path

# Directory containing test case logs
log_path = "D:\\4thYear\\Research\\Devlopment\\git_2\\Agent_Framework_Backend\\Evaluation\\Logs"

# Ensure the log path exists
assert Path(log_path).exists(), f"The log path '{log_path}' does not exist."

# Load criteria
criteria_file = f"D:\\4thYear\\Research\\Devlopment\\git_2\\Agent_Framework_Backend\\Evaluation\\{current_task_name}_criteria.json"
criteria = open(criteria_file, "r").read()
criteria = Criterion.parse_json_str(criteria)
# with open(criteria_file, "r") as f:
#     criteria = json.load(f)

criteria_file = f"D:\\4thYear\\Research\\Devlopment\\git_2\\Agent_Framework_Backend\\Evaluation\\{current_task_name}_criteria.json"
criteria = open(criteria_file, "r").read()
criteria = Criterion.parse_json_str(criteria)

test_case = open("D:\\4thYear\\Research\\Devlopment\\git_2\\Agent_Framework_Backend\\Evaluation\\sample_forensic_response_successful.txt", "r").read()
test_case, ground_truth = remove_ground_truth(test_case)
quantifier_output = quantify_criteria(
    llm_config={"config_list": config_list},
    criteria=criteria,
    task=task,
    test_case=test_case,
    ground_truth=ground_truth,
)
print("actual correctness:", quantifier_output["actual_success"])
print("predicted correctness:\n", quantifier_output["estimated_performance"])

log_path = "D:\\4thYear\\Research\\Devlopment\\git_2\\Agent_Framework_Backend\\Evaluation\\Logs"
assert Path(log_path).exists(), f"The log path '{log_path}' does not exist."

criteria_file = f"D:\\4thYear\\Research\\Devlopment\\git_2\\Agent_Framework_Backend\\Evaluation\\{current_task_name}_criteria.json"
criteria = Criterion.parse_json_str(open(criteria_file, "r").read())

# Evaluate all test cases in the log directory
outcome = {}
for prefix in os.listdir(log_path):
    for file_name in os.listdir(log_path + "/" + prefix):
        gameid = prefix + "_" + file_name
        if file_name.endswith(".json"):
            test_case, ground_truth = remove_ground_truth(open(log_path + "/" + prefix + "/" + file_name, "r").read())
            quantifier_output = quantify_criteria(
                llm_config={"config_list": config_list},
                criteria=criteria,
                task=task,
                test_case=test_case,
                ground_truth=ground_truth,
            )
            outcome[gameid] = quantifier_output

# Save evaluation results
with open("D:\\4thYear\\Research\\Devlopment\\git_2\\Agent_Framework_Backend\\Evaluation\\evaluated_forensic_problems.json", "w") as file:
    json.dump(outcome, file, indent=2)


#
# import numpy as np
# import scipy.stats as stats
# import matplotlib
# matplotlib.use("TkAgg")  # Change backend if needed
# import matplotlib.pyplot as plt
#
# # Load criteria
# try:
#     criteria = Criterion.parse_json_str(open(criteria_file, "r").read())
# except:  # noqa: E722
#     criteria = []  # Ensure criteria is at least an empty list
#
# nl2int = {}
# for criterion in criteria:
#     score = 0
#     for v in criterion.accepted_values:
#         nl2int[v] = score
#         score += 1
#
# average_s, average_f = {}, {}
# conf_interval_s, conf_interval_f = {}, {}
#
# for criterion in criteria:
#     task = {"s": [], "f": []}
#
#     for game in outcome:
#         try:
#             tmp_dic = eval(outcome[game]["estimated_performance"])
#             if outcome[game]["actual_success"] == "false":
#                 task["f"].append(nl2int[tmp_dic[criterion.name]])
#             else:
#                 task["s"].append(nl2int[tmp_dic[criterion.name]])
#         except:  # noqa: E722
#             pass
#
#     average_f[criterion.name] = np.mean(task["f"]) if task["f"] else np.nan
#     average_s[criterion.name] = np.mean(task["s"]) if task["s"] else np.nan
#
#     if task["s"]:
#         average_s[criterion.name] = np.mean(task["s"])
#         conf_interval_s[criterion.name] = stats.norm.interval(0.95, loc=np.mean(task["s"]), scale=stats.sem(task["s"]))
#     else:
#         average_s[criterion.name] = 0  # Assign 0 or another default value
#         conf_interval_s[criterion.name] = (0, 0)
#
#     if task["f"]:
#         average_f[criterion.name] = np.mean(task["f"])
#         conf_interval_f[criterion.name] = stats.norm.interval(0.95, loc=np.mean(task["f"]), scale=stats.sem(task["f"]))
#     else:
#         average_f[criterion.name] = 0
#         conf_interval_f[criterion.name] = (0, 0)
#
#     plt.figure(figsize=(12, 8))
#     bar_width = 0.1
#     index = np.arange(len(criteria))
#
#     valid_criteria = list(average_s.keys())  # Only those with valid data
#     index = np.arange(len(valid_criteria))
#
#     plt.bar(
#         index,
#         [average_s[c] for c in valid_criteria],
#         bar_width,
#         label=f"success ({len(task['s'])} samples)",
#         color="darkblue",
#         yerr=[(average_s[c] - conf_interval_s[c][0]) for c in valid_criteria],
#         capsize=5,
#     )
#
#     plt.bar(
#         index + bar_width,
#         [average_f[c] for c in valid_criteria],
#         bar_width,
#         label=f"failed ({len(task['f'])} samples)",
#         color="lightblue",
#         yerr=[(average_f[c] - conf_interval_f[c][0]) for c in valid_criteria],
#         capsize=5,
#     )
#
#     plt.xticks(index + bar_width / 2, valid_criteria, rotation=45, fontsize=14)
#
#     plt.ylabel("Score")
#     plt.title("Comparison of Success and Failure Scores")
#     plt.legend()
#     plt.tight_layout()
#     plt.show()
#     plt.close()
#

