"""
Wraps per-chat conversation memory and builds the final system prompt sent
to the AI provider (base tutor prompt + detailed-mode + group-scope notes).
"""
from pathlib import Path

from storage import repositories as repo

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "study_tutor.txt"
_BASE_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
_PERSONA = (Path(__file__).parent.parent / "prompts" / "spark_persona.txt").read_text(encoding="utf-8")


def chat_key(chat_id: int) -> str:
    return str(chat_id)


async def remember_turn(chat_id: int, role: str, content: str):
    await repo.remember(chat_key(chat_id), role, content)


async def get_history(chat_id: int) -> list:
    return await repo.get_memory(chat_key(chat_id))


async def clear(chat_id: int):
    await repo.clear_memory(chat_key(chat_id))


def build_system_prompt(detailed_mode: bool, is_group: bool, is_owner: bool = False,
                        speaker_name: str = "") -> str:
    prompt = _BASE_PROMPT + _PERSONA
    prompt = prompt.replace("{{DETAILED_MODE}}", "enabled" if detailed_mode else "disabled")
    if detailed_mode:
        prompt += ("\n\nThis student has detailed/step-by-step mode ON — always explain your "
                   "full reasoning and working, not just the final answer.")
    else:
        prompt += "\n\nKeep the answer reasonably concise unless the student explicitly asks for more detail."
    if is_group:
        prompt += ("\n\nThis is a group chat. Only answer the specific question you were asked; "
                   "don't address unrelated messages in the group.")
    safe_name = (speaker_name or "").replace("\n", " ")[:40]
    prompt += (f"\n\nCURRENT SPEAKER IS THE OWNER = {'YES' if is_owner else 'NO'}"
               f"\nCURRENT SPEAKER NAME = {safe_name or 'unknown'}")
    return prompt
