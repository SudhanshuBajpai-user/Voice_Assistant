def report_action_result(intent, outcome):
    """Report the result of one executed action."""
    outcome = outcome or {
        "success": None,
        "message": "The action result was unavailable.",
    }
    success = outcome.get("success")
    message = outcome.get("message", "")

    if success is True:
        print(message or f"Completed: {intent}.")
    elif success is False:
        print(f"Failed: {intent}.")
        if message:
            print(f"Reason: {message}")
    else:
        print(f"Dispatched but not verified: {intent}.")
        if message:
            print(message)


def report_plan_summary(results):
    """Summarize a sequence of planned actions."""
    completed = sum(
        result.get("success") is True for result in results
    )
    failed = sum(
        result.get("success") is False for result in results
    )
    pending = len(results) - completed - failed

    print("\n--- Execution Summary ---")
    print(f"Completed: {completed}")
    print(f"Failed: {failed}")
    print(f"Not completed: {pending}")
