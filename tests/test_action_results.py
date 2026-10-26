import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import action
import execution_logger
from command_router import prepare_command
from entity_extractor import extract_arguments
from planner import plan_command
from response import report_action_result
from session_controller import SessionController


class ActionOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.original_actions = action.ACTIONS.copy()

    def tearDown(self):
        action.ACTIONS.clear()
        action.ACTIONS.update(self.original_actions)

    def test_success_is_reported_only_for_true_return_contract(self):
        action.ACTIONS["TEST"] = Mock(return_value=True)

        self.assertTrue(action.execute_intent("TEST"))
        action.ACTIONS["TEST"].assert_called_once_with()
        self.assertEqual(action.get_last_action_outcome()["success"], True)
        self.assertEqual(action.get_last_action_outcome()["status"], "completed")

    def test_false_action_failure_does_not_stop_loop(self):
        action.ACTIONS["TEST"] = Mock(return_value=False)

        self.assertTrue(action.execute_intent("TEST"))
        outcome = action.get_last_action_outcome()
        self.assertEqual(outcome["success"], False)
        self.assertEqual(outcome["status"], "failed")

    def test_action_exception_is_recorded_and_does_not_stop_loop(self):
        action.ACTIONS["TEST"] = Mock(side_effect=RuntimeError("simulated failure"))

        self.assertTrue(action.execute_intent("TEST"))
        outcome = action.get_last_action_outcome()
        self.assertEqual(outcome["success"], False)
        self.assertEqual(outcome["status"], "exception")
        self.assertIn("simulated failure", outcome["message"])

    def test_unsupported_intent_is_safe_and_clears_previous_outcome(self):
        action.ACTIONS["TEST"] = Mock(return_value=True)
        action.execute_intent("TEST")

        self.assertTrue(action.execute_intent("NOT_SUPPORTED"))
        outcome = action.get_last_action_outcome()
        self.assertEqual(outcome["intent"], "NOT_SUPPORTED")
        self.assertEqual(outcome["status"], "unsupported")
        self.assertFalse(outcome["success"])

    def test_stop_assistant_stops_loop_without_treating_failure_as_stop(self):
        action.ACTIONS["STOP_ASSISTANT"] = Mock(return_value=False)

        self.assertFalse(action.execute_intent("STOP_ASSISTANT"))
        outcome = action.get_last_action_outcome()
        self.assertEqual(outcome["status"], "stop_requested")
        self.assertTrue(outcome["success"])


class PlannerTests(unittest.TestCase):
    def test_open_edge_and_search_is_ordered_two_step_plan(self):
        self.assertEqual(
            plan_command("Open Edge and search for GPT"),
            ["Open Edge", "search the web for GPT"],
        )

    def test_cpu_and_gpu_is_two_step_plan(self):
        self.assertEqual(
            plan_command("Check CPU and check GPU"),
            ["Check CPU", "check GPU"],
        )

    def test_search_for_cats_and_dogs_is_one_request(self):
        self.assertEqual(
            plan_command("Search for cats and dogs"),
            ["search the web for cats and dogs"],
        )


class RouterAndEntityTests(unittest.TestCase):
    def test_valid_search_extracts_query(self):
        result = prepare_command("SEARCH_WEB", "search for cats")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["arguments"]["query"], "cats")

    def test_five_minute_timer_extracts_300_seconds(self):
        result = extract_arguments("SET_TIMER", "set a timer for five minutes")
        self.assertEqual(result["duration_seconds"], 300)
        self.assertFalse(result["needs_clarification"])

    def test_incomplete_note_requests_content(self):
        result = prepare_command("MAKE_NOTES", "make a note")
        self.assertEqual(result["status"], "needs_clarification")
        self.assertTrue(result["arguments"]["needs_clarification"])

    def test_intent_transcript_mismatch_is_rejected(self):
        result = prepare_command("OPEN_EDGE", "search for cats")
        self.assertEqual(result["status"], "needs_clarification")

    def test_repetitive_transcript_is_rejected(self):
        repetitive = " ".join(["open"] * 20)
        result = prepare_command("OPEN_EDGE", repetitive)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("repetitive", result["message"].lower())


class MultiStepExecutionTests(unittest.TestCase):
    def setUp(self):
        self.original_actions = action.ACTIONS.copy()

    def tearDown(self):
        action.ACTIONS.clear()
        action.ACTIONS.update(self.original_actions)

    def _run_plan(self, command, fail_intent=None):
        calls = []
        outcomes = []
        for step in plan_command(command):
            intent = "CHECK_CPU" if "cpu" in step.lower() else "CHECK_GPU"
            action.ACTIONS[intent] = Mock(
                side_effect=lambda intent=intent: (
                    calls.append(intent) or (intent != fail_intent)
                )
            )
            prepared = prepare_command(intent, step)
            if prepared["status"] != "ready":
                outcomes.append({"status": "rejected", "success": False})
                break
            loop_result = action.execute_intent(intent, step, prepared["arguments"])
            outcome = action.get_last_action_outcome()
            outcomes.append(outcome)
            if outcome["success"] is False or loop_result is False:
                break
        return calls, outcomes

    def test_both_successful_steps_run_in_order(self):
        calls, outcomes = self._run_plan("check cpu and check gpu")
        self.assertEqual(calls, ["CHECK_CPU", "CHECK_GPU"])
        self.assertEqual([item["success"] for item in outcomes], [True, True])

    def test_failed_second_step_stops_with_partial_result(self):
        calls, outcomes = self._run_plan(
            "check cpu and check gpu",
            fail_intent="CHECK_GPU",
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(outcomes), 2)
        self.assertFalse(outcomes[-1]["success"])

    def test_rejected_step_is_not_dispatched(self):
        action.ACTIONS["CHECK_CPU"] = Mock(return_value=True)
        prepared = prepare_command("OPEN_EDGE", "search for cats")
        self.assertNotEqual(prepared["status"], "ready")
        action.ACTIONS["CHECK_CPU"].assert_not_called()

    def test_ordinary_failure_keeps_assistant_running(self):
        action.ACTIONS["CHECK_CPU"] = Mock(return_value=False)
        self.assertTrue(action.execute_intent("CHECK_CPU"))


class SessionAndLoggingTests(unittest.TestCase):
    def test_pending_follow_up_answers_for_timer_note_and_search(self):
        cases = [
            ("SET_TIMER", "five minutes", {"duration_seconds": 300}),
            ("MAKE_NOTES", "buy a keyboard", {"content": "buy a keyboard"}),
            ("SEARCH_WEB", "cats", {"query": "cats"}),
        ]
        for intent, answer, expected in cases:
            with self.subTest(intent=intent):
                session = SessionController()
                session.set_pending(intent, f"initial {intent}")
                if intent == "MAKE_NOTES":
                    arguments = {
                        "content": answer,
                        "needs_clarification": not bool(answer.strip()),
                    }
                else:
                    arguments = extract_arguments(intent, answer)
                self.assertFalse(arguments["needs_clarification"])
                for key, value in expected.items():
                    self.assertEqual(arguments[key], value)
                session.clear_pending()
                self.assertFalse(session.has_pending())

    def test_cancellation_clears_pending_state(self):
        session = SessionController()
        session.set_pending("MAKE_NOTES", "make a note")
        session.clear_pending()
        self.assertFalse(session.has_pending())
        self.assertIsNone(session.get_pending())

    def test_log_contains_metadata_and_redacts_note_content(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "events.jsonl"
            with patch.object(execution_logger, "LOG_FILE", log_path):
                execution_logger.log_event(
                    command="make a note saying private note content",
                    intent="MAKE_NOTES",
                    confidence=0.91,
                    status="completed",
                    action_outcome={
                        "intent": "MAKE_NOTES",
                        "success": True,
                        "status": "completed",
                        "message": "Note saved.",
                    },
                )
            event = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertIn("timestamp", event)
            self.assertEqual(event["intent"], "MAKE_NOTES")
            self.assertEqual(event["status"], "completed")
            self.assertEqual(event["action_outcome"]["success"], True)
            self.assertNotIn("private note content", log_path.read_text())

    def test_logging_failure_does_not_raise(self):
        with patch.object(Path, "open", side_effect=OSError("read-only")):
            with patch("builtins.print") as printer:
                execution_logger.log_event(intent="CHECK_CPU")
        printer.assert_called_once()

    def test_response_reports_unverified_actions_without_success_claim(self):
        with patch("builtins.print") as printer:
            report_action_result(
                "TEST",
                {
                    "success": None,
                    "status": "dispatched_unverified",
                    "message": "Completion could not be verified.",
                },
            )
        output = " ".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("not verified", output.lower())
        self.assertNotIn("completed successfully", output.lower())


if __name__ == "__main__":
    unittest.main()
