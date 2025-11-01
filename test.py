from livekit.agents import AgentSession

from livekit.plugins import (
    aws,
    noise_cancellation,
)
from agent import Assistant
import pytest
@pytest.mark.asyncio
async def test_assistant_greeting() -> None:
    async with (
        aws.LLM(
        model="anthropic.claude-3-5-sonnet-20240620-v1:0",
        temperature=0.8,
        region='eu-central-1'
    ) as llm,
        AgentSession(llm=llm) as session,
    ):
        await session.start(Assistant())
        
        result = await session.run(user_input="I want to talk to a human")
        
        await result.expect.next_event().is_message(role="assistant").judge(
            llm, intent="Makes a friendly introduction and offers assistance."
        )
        
        result.expect.no_more_events()