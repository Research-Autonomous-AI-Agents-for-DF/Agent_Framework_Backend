# evaluation_module.py
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
import logging

from autogen.agentchat.contrib.agent_eval.agent_eval import generate_criteria, quantify_criteria
from autogen.agentchat.contrib.agent_eval.criterion import Criterion
from autogen.agentchat.contrib.agent_eval.task import Task

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ForensicEvaluator:
    """Evaluator for forensic analysis tasks performed by the agent framework."""

    def __init__(self, config_list: List[Dict[str, Any]], eval_dir: str = "evaluation"):
        """
        Initialize the ForensicEvaluator.

        Args:
            config_list: LLM configuration list
            eval_dir: Directory to store evaluation files
        """
        self.config_list = config_list
        self.eval_dir = eval_dir
        self.criteria = None
        self.task = None

        # Create evaluation directory if it doesn't exist
        os.makedirs(self.eval_dir, exist_ok=True)
        os.makedirs(os.path.join(self.eval_dir, "logs"), exist_ok=True)

    def initialize_task(self, task_name: str, task_description: str,
                        successful_example_path: str, failed_example_path: str) -> None:
        """
        Initialize the task and generate criteria.

        Args:
            task_name: Name of the forensic task
            task_description: Description of the task
            successful_example_path: Path to successful example response
            failed_example_path: Path to failed example response
        """
        logger.info(f"Initializing task: {task_name}")

        # Load examples
        successful_example = self._load_and_clean_example(successful_example_path)
        failed_example = self._load_and_clean_example(failed_example_path)

        # Create task
        self.task = Task(
            name=task_name,
            description=task_description,
            successful_response=successful_example,
            failed_response=failed_example
        )

        # Generate criteria
        logger.info("Generating evaluation criteria...")
        self.criteria = generate_criteria(
            task=self.task,
            llm_config={"config_list": self.config_list},
            max_round=8
        )

        # Save criteria
        criteria_path = self._get_criteria_path(task_name)
        with open(criteria_path, "w") as f:
            f.write(Criterion.write_json(self.criteria))
        logger.info(f"Criteria saved to {criteria_path}")

    def _load_and_clean_example(self, example_path: str) -> str:
        """Load and clean an example by removing ground truth."""
        with open(example_path, "r") as f:
            example_str = f.read()

        example_details = json.loads(example_str)
        # Remove ground truth fields
        example_details.pop("is_correct", None)
        example_details.pop("correct_ans", None)
        example_details.pop("check_result", None)

        return json.dumps(example_details)

    def _get_criteria_path(self, task_name: str) -> str:
        """Get path for saving criteria."""
        return os.path.join(self.eval_dir, f"{task_name.lower().replace(' ', '_')}_criteria.json")

    def load_criteria(self, task_name: str) -> List[Criterion]:
        """Load criteria for a task."""
        criteria_path = self._get_criteria_path(task_name)
        if not os.path.exists(criteria_path):
            raise FileNotFoundError(f"Criteria file not found: {criteria_path}")

        with open(criteria_path, "r") as f:
            criteria_str = f.read()

        return Criterion.parse_json_str(criteria_str)

    def save_session_result(self, task_name: str, session_id: str,
                            conversation_json: Dict[str, Any],
                            ground_truth: bool = None) -> str:
        """
        Save a session result for later evaluation.

        Args:
            task_name: Name of the task
            session_id: Unique identifier for the session
            conversation_json: JSON of the conversation
            ground_truth: Whether the session was successful (if known)

        Returns:
            Path to the saved log file
        """
        # Create session directory
        log_dir = os.path.join(self.eval_dir, "logs", task_name.lower().replace(' ', '_'))
        os.makedirs(log_dir, exist_ok=True)

        # Add ground truth if provided
        if ground_truth is not None:
            conversation_json["is_correct"] = str(ground_truth).lower()

        # Save session result
        log_path = os.path.join(log_dir, f"{session_id}.json")
        with open(log_path, "w") as f:
            json.dump(conversation_json, f, indent=2)

        logger.info(f"Session result saved to {log_path}")
        return log_path

    def evaluate_session(self, task_name: str, conversation_json: Dict[str, Any],
                         ground_truth: Optional[bool] = None) -> Dict[str, Any]:
        """
        Evaluate a single session against criteria.

        Args:
            task_name: Name of the task
            conversation_json: JSON of the conversation
            ground_truth: Whether the session was successful (if known)

        Returns:
            Evaluation results
        """
        # Load criteria if not already loaded
        if self.criteria is None:
            self.criteria = self.load_criteria(task_name)

        # Prepare test case
        test_case = json.dumps(conversation_json)
        ground_truth_str = str(ground_truth).lower() if ground_truth is not None else None

        # Evaluate
        quantifier_output = quantify_criteria(
            llm_config={"config_list": self.config_list},
            criteria=self.criteria,
            task=self.task,
            test_case=test_case,
            ground_truth=ground_truth_str
        )

        return quantifier_output

    def evaluate_all_logs(self, task_name: str) -> Dict[str, Dict[str, Any]]:
        """
        Evaluate all logs for a specific task.

        Args:
            task_name: Name of the task

        Returns:
            Dictionary mapping session IDs to evaluation results
        """
        # Load criteria
        self.criteria = self.load_criteria(task_name)

        # Get log directory
        log_dir = os.path.join(self.eval_dir, "logs", task_name.lower().replace(' ', '_'))
        if not os.path.exists(log_dir):
            logger.warning(f"No logs found for task: {task_name}")
            return {}

        # Evaluate all logs
        outcome = {}
        for file_name in os.listdir(log_dir):
            if file_name.endswith(".json"):
                session_id = file_name.replace(".json", "")

                # Load and evaluate
                with open(os.path.join(log_dir, file_name), "r") as f:
                    test_case = f.read()

                # Extract ground truth if present
                test_json = json.loads(test_case)
                ground_truth = test_json.pop("is_correct", None)
                test_case = json.dumps(test_json)

                # Evaluate
                try:
                    quantifier_output = quantify_criteria(
                        llm_config={"config_list": self.config_list},
                        criteria=self.criteria,
                        task=self.task,
                        test_case=test_case,
                        ground_truth=ground_truth
                    )
                    outcome[session_id] = quantifier_output
                    logger.info(f"Evaluated session: {session_id}")
                except Exception as e:
                    logger.error(f"Error evaluating session {session_id}: {str(e)}")

        # Save results
        results_path = os.path.join(self.eval_dir, f"evaluated_{task_name.lower().replace(' ', '_')}.json")
        with open(results_path, "w") as f:
            json.dump(outcome, f, indent=2)

        logger.info(f"Evaluation results saved to {results_path}")
        return outcome

    def generate_report(self, task_name: str, output_format: str = "text") -> str:
        """
        Generate an evaluation report.

        Args:
            task_name: Name of the task
            output_format: Format of the report ("text" or "html")

        Returns:
            Report content
        """
        # Load evaluation results
        results_path = os.path.join(self.eval_dir, f"evaluated_{task_name.lower().replace(' ', '_')}.json")
        if not os.path.exists(results_path):
            return "No evaluation results found. Run evaluate_all_logs first."

        with open(results_path, "r") as f:
            results = json.load(f)

        if not results:
            return "No evaluations to report."

        # Calculate statistics
        total_sessions = len(results)
        successful_sessions = sum(1 for r in results.values() if r.get("actual_success") == "true")
        success_rate = (successful_sessions / total_sessions) * 100 if total_sessions > 0 else 0

        # Generate report
        if output_format == "text":
            report = [
                f"# Evaluation Report for {task_name}",
                f"Total sessions: {total_sessions}",
                f"Successful sessions: {successful_sessions}",
                f"Success rate: {success_rate:.2f}%",
                "\n## Criteria Performance",
            ]

            # Analyze criteria performance
            criteria_performance = {}
            for session_id, evaluation in results.items():
                try:
                    if "estimated_performance" in evaluation:
                        perf = eval(evaluation["estimated_performance"])
                        for criterion, score in perf.items():
                            if criterion not in criteria_performance:
                                criteria_performance[criterion] = []
                            criteria_performance[criterion].append(score)
                except:
                    continue

            # Add criteria statistics to report
            for criterion, scores in criteria_performance.items():
                avg_score = sum(1 for s in scores if s == "Yes") / len(scores) if scores else 0
                report.append(f"- {criterion}: {avg_score:.2f} average score ({len(scores)} evaluations)")

            return "\n".join(report)
        else:
            # HTML report could be implemented here
            return "HTML reports not yet implemented"