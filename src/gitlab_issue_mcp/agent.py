"""Microsoft AutoGen-powered question-answering agent for GitLab issues.

The agent receives a natural-language question together with a JSON-formatted
summary of GitLab issues and returns a natural-language answer.  It is
intentionally model-agnostic: any OpenAI-compatible endpoint (including
LiteLLM, Ollama, Azure OpenAI, etc.) can be used by setting ``llm_base_url``
in the configuration.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import autogen

logger = logging.getLogger(__name__)

_SYSTEM_MESSAGE = """You are an expert GitLab project manager assistant.
Your job is to analyse a collection of GitLab issues provided in JSON format
and answer the user's question clearly and concisely.

Guidelines:
- Reference specific issue numbers (IID) when relevant.
- Consider issue state (opened / closed), assignees, labels, and milestones.
- If the question asks for a summary, keep it brief but informative.
- If no issues match the question's intent, say so explicitly.
- Do NOT invent issues or data that is not present in the provided list.
"""


class IssueQAAgent:
    """AutoGen-based agent that answers questions about GitLab issues.

    Parameters
    ----------
    llm_config:
        AutoGen LLM configuration dict.  Must contain a ``config_list`` entry
        with at least one provider block, e.g.::

            {
                "config_list": [
                    {
                        "model": "gpt-4o",
                        "api_key": "sk-...",
                        "base_url": "http://localhost:4000",
                    }
                ],
                "temperature": 0,
            }
    """

    def __init__(self, llm_config: Dict[str, Any]) -> None:
        self._llm_config = llm_config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def answer_question(
        self,
        question: str,
        issues: List[Dict[str, Any]],
        max_issues: int = 50,
    ) -> str:
        """Answer *question* using the supplied *issues* as context.

        Parameters
        ----------
        question:
            The natural-language question to answer.
        issues:
            List of issue dicts as returned by :class:`GitLabClient`.
        max_issues:
            Maximum number of issues forwarded to the agent.  Issues beyond
            this limit are silently dropped to avoid context-window overflow.

        Returns
        -------
        str
            The agent's natural-language answer.

        Raises
        ------
        RuntimeError
            If the underlying AutoGen conversation fails.
        """
        truncated = issues[:max_issues]
        total = len(issues)
        shown = len(truncated)

        issues_block = self._format_issues(truncated)

        header = ""
        if total > shown:
            header = (
                f"Note: {shown} of {total} issues shown "
                "(oldest issues omitted to fit context).\n\n"
            )

        prompt = (
            f"Please answer the following question about the GitLab issues listed below.\n\n"
            f"Question: {question}\n\n"
            f"{header}"
            f"Issues:\n{issues_block}"
        )

        return self._run_conversation(prompt)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_conversation(self, prompt: str) -> str:
        """Drive a single-round AutoGen conversation and return the answer."""
        assistant = autogen.AssistantAgent(
            name="gitlab_assistant",
            llm_config=self._llm_config,
            system_message=_SYSTEM_MESSAGE,
        )

        # UserProxyAgent with no human input, no code execution.
        # is_termination_msg=lambda _: True stops the loop immediately after
        # the first assistant reply.
        user_proxy = autogen.UserProxyAgent(
            name="user_proxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1,
            code_execution_config=False,
            is_termination_msg=lambda _: True,
        )

        try:
            user_proxy.initiate_chat(
                assistant,
                message=prompt,
                clear_history=True,
            )
        except Exception as exc:
            logger.error("AutoGen conversation failed: %s", exc)
            raise RuntimeError(f"Agent conversation failed: {exc}") from exc

        # Extract the last assistant message.
        history: List[Dict[str, Any]] = user_proxy.chat_messages.get(
            assistant, []
        )
        for msg in reversed(history):
            if msg.get("role") == "assistant" and msg.get("content"):
                return str(msg["content"])

        return "The agent did not produce an answer."

    @staticmethod
    def _format_issues(issues: List[Dict[str, Any]]) -> str:
        """Serialise issues to a compact JSON-lines string for the prompt."""
        if not issues:
            return "No issues found."

        lines: List[str] = []
        for issue in issues:
            entry = {
                "iid": issue.get("iid"),
                "title": issue.get("title", ""),
                "state": issue.get("state", ""),
                "assignees": [
                    a.get("username", "")
                    for a in (issue.get("assignees") or [])
                ],
                "author": (issue.get("author") or {}).get("username", ""),
                "labels": issue.get("labels", []),
                "milestone": (
                    (issue.get("milestone") or {}).get("title")
                ),
                "created_at": issue.get("created_at", ""),
                "updated_at": issue.get("updated_at", ""),
                "description": (issue.get("description") or "")[:300],
                "web_url": issue.get("web_url", ""),
            }
            lines.append(json.dumps(entry, default=str))

        return "\n".join(lines)
