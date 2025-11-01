from dotenv import load_dotenv
from livekit import api
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions,function_tool, RunContext,JobContext, get_job_context,ChatContext,ChatContent,ChatItem,ChatRole, RoomInputOptions,UserInputTranscribedEvent
from livekit.plugins import (
    aws,
    noise_cancellation,
)
from livekit.agents import voice
from livekit.plugins.turn_detector.multilingual import MultilingualModel

import pprint
import logging
from tools import create_order
import os
from typing import Any
from livekit.protocol.sip import TransferSIPParticipantRequest
import asyncio
from livekit import rtc
import uuid
import wave
import numpy as np
from pathlib import Path
load_dotenv()
logger = logging.getLogger("rental-orlando")
logger.setLevel(logging.WARNING)
logging.getLogger("livekit.plugins.aws").setLevel(logging.WARNING)
def load_system_prompt():
    base_dir = os.path.dirname(__file__)  # This gets the folder where agent.py is
    file_path = os.path.join(base_dir, "instructions.txt")
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()
    

class Assistant(Agent):
    def __init__(self,context:JobContext) -> None:
        self.job_context = context
        self.caller_phone_no = None
        super().__init__(instructions=load_system_prompt())

    
    @function_tool()
    async def add_sip_participant(self, context: RunContext, phone_number: str):
       
        if not self.job_context:
            logger.error("No job context available")
            await self.session.say("I'm sorry, I can't add participants at this time.")
            return None, "Failed to add SIP participant: No job context available"
            
        room_name = self.job_context.room.name
        
        identity = f"sip_{uuid.uuid4().hex[:8]}"
        
        sip_trunk_id = os.environ.get('SIP_TRUNK_ID')
        
        logger.info(f"Adding SIP participant with phone number {phone_number} to room {room_name}")
        
        try:
            response = await self.job_context.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    sip_trunk_id=sip_trunk_id,
                    sip_call_to=phone_number,
                    room_name=room_name,
                    participant_identity=identity,
                    participant_name=f"SIP Participant {phone_number}",
                    krisp_enabled=True
                )
            )
            
            logger.info(f"Successfully added SIP participant: {response}")
            return None, f"Added SIP participant {phone_number} to the call."
            
        except Exception as e:
            logger.error(f"Error adding SIP participant: {e}")
            await self.session.say(f"I'm sorry, I couldn't add {phone_number} to the call.")
            return None, f"Failed to add SIP participant: {e}"
    
    @function_tool
    async def end_call(self, context: RunContext):
        """
        End the current call by deleting the room.
        """
        if not self.job_context:
            logger.error("No job context available")
            await self.session.say("I'm sorry, I can't end the call at this time.")
            return None, "Failed to end call: No job context available"
            
        room_name = self.job_context.room.name
        logger.info(f"Ending call by deleting room {room_name}")
        
        try:
            await context.session.generate_reply(
                instructions="Thank you for your time. I'll be ending this call now. Goodbye!"
            )
            await self.job_context.api.room.delete_room(
                api.DeleteRoomRequest(room=room_name)
            )
            
            logger.info(f"Successfully deleted room {room_name}")
            return None, "Call ended successfully."
            
        except Exception as e:
            logger.error(f"Error ending call: {e}")
            return None, f"Failed to end call: {e}"
    
    
    @function_tool
    async def log_participants(self, context: RunContext):
        """
        Log all participants in the current room.
        """
        if not self.job_context:
            logger.error("No job context available")
            await self.session.say("I'm sorry, I can't list participants at this time.")
            return None, "Failed to list participants: No job context available"
            
        room_name = self.job_context.room.name
        logger.info(f"Logging participants in room {room_name}")
        
        try:
            response = await self.job_context.api.room.list_participants(
                api.ListParticipantsRequest(room=room_name)
            )
            
            participants = response.participants
            participant_info = []
            
            for p in participants:
                participant_info.append({
                    "identity": p.identity,
                    "name": p.name,
                    "state": p.state,
                    "is_publisher": p.is_publisher
                })
            
            logger.info(f"Participants in room {room_name}: {participant_info}")
            
            await self.session.say(f"There are {len(participants)} participants in this call.")
            
            return None, f"Listed {len(participants)} participants in the room."
            
        except Exception as e:
            logger.error(f"Error listing participants: {e}")
            return None, f"Failed to list participants: {e}"
    
    def set_caller_phone_number(self,phone_no):
        self.caller_phone_no = phone_no
        print(f"📝  Customer phone number: {phone_no}")
    async def on_enter(self):
        # self.session.generate_reply()
        logger.info("Assistant agent has entered the session.")
        
        
    @function_tool()
    async def create_order(
        self,
        context: RunContext,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Create a new order from a list of items.

        Args:
            items: A list of dictionaries, each representing an ordered item.
                   Required keys: 'product_name', 'quantity'

        Returns:
            A dict with 'order_id' and a success message, or an error message on failure.
        """
        try:
            order_id, _ = create_order(items)
            return {
                "order_id": order_id,
                "message": f"Order {order_id} has been successfully created with {len(items)} item(s)."
            }
        except Exception as e:
            context.logger.error(f"Error creating order: {e}")
            return {
                "error": "Something went wrong while creating the order. Please try again later."
            }

    async def transfer_call_to_human(self,participant_identity: str, room_name: str) -> None:
        async with api.LiveKitAPI() as livekit_api:
            transfer_to = 'tel:+4915224878669'
    
            # Create transfer request
            transfer_request = TransferSIPParticipantRequest(
                participant_identity=participant_identity,
                room_name=room_name,
                transfer_to=transfer_to,
                play_dialtone=False
            )
            logger.debug(f"Transfer request: {transfer_request}")
            
            # Transfer caller
            await livekit_api.sip.transfer_sip_participant(transfer_request)
            logger.info(f"Successfully transferred participant {participant_identity} to {transfer_to}")

    @function_tool()
    async def transfer_call(self, ctx: RunContext):
        """Transfer the call to a human agent, called after confirming with the user"""
        job_ctx = get_job_context()
        print(job_ctx)
        room_name = self.job_context.room.name
        caller_identity = self.caller_phone_no
        await self.transfer_call_to_human(caller_identity,room_name)
        
        return f"Transferring to human."

    async def testing_around(self,ctx:RunContext):
   
        print("Testing around...")
        print(f"Context: {ctx}")
        print(f"Session: {self.session}")
        print(f"Job Context: {self.job_context}")
        print(f"Room: {self.job_context.room.name if self.job_context else 'No room context'}")
        print(f"Participants: {self.job_context.room.remote_participants if self.job_context else 'No participants'}")
        
        # Retrieved context
        ret_context = get_job_context()
        print(f"Retrieved Job Context: {ret_context}")
        
        print(f"Retrieved Room: {ret_context.room.name if ret_context else 'No room context'}")
        print(f"Retrieved Participants: {ret_context.room.remote_participants if ret_context else 'No participants'}")
        
        # await self.session.say("This is a test message to check the context and session.")


    async def on_user_turn_completed(self, ctx: JobContext, messages):
        """
        Called when the agent detects a user turn is completed.
        `messages` contains transcripts or text messages from that user turn.
        """
        for m in messages:
            if m.type == "transcript":
                print("User said:", m.alternatives[0].text)



            
            
async def entrypoint(ctx: agents.JobContext):
    session = AgentSession(
        llm=aws.realtime.RealtimeModel(voice='tiffany',region='us-east-1'),
        tts=aws.TTS(voice='Amy',speech_engine="generative",language='en-US',region='us-east-1'),
        turn_detection=MultilingualModel(),
        preemptive_generation=True
        
    )

        
    agent = Assistant(context=ctx)

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )
    agent.session.say("Hi!")
    
    def on_participant_connected_handler(participant: rtc.RemoteParticipant):
        asyncio.create_task(async_on_participant_connected(participant))
    def on_participant_attributes_changed_handler(changed_attributes: dict, participant: rtc.Participant):
        asyncio.create_task(async_on_participant_attributes_changed(changed_attributes, participant))
    
   
            
    
    async def async_on_participant_connected(participant: rtc.RemoteParticipant):
            logger.info(f"Participant {participant.identity} connected with metadata: {participant.metadata}")
            logger.info(f"Participant {participant.identity} attributes: {participant.attributes}")
            # await agent.testing_around(ctx)
            # await agent.session.say(f"Welcome, {participant.name or participant.identity}! I can help you add a participant to this call or end the call.")
            
            await agent.set_caller_phone_number(participant.identity)

    async def async_on_participant_attributes_changed(changed_attributes: dict, participant: rtc.Participant):
        logger.info(f"Participant {participant.identity} attributes changed: {changed_attributes}")
        
        
        # Check if this is a SIP participant and if call status has changed
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            # Check if sip.callStatus is in the changed attributes
            if 'sip.callStatus' in changed_attributes:
                call_status = changed_attributes['sip.callStatus']
                logger.info(f"SIP Call Status updated: {call_status}")

                # Log specific call status information
                if call_status == 'active':
                    logger.info("Call is now active and connected")
                elif call_status == 'automation':
                    logger.info("Call is now connected and dialing DTMF numbers")
                elif call_status == 'dialing':
                    logger.info("Call is now dialing and waiting to be picked up")
                elif call_status == 'hangup':
                    logger.info("Call has been ended by a participant")
                elif call_status == 'ringing':
                    logger.info("Inbound call is now ringing for the caller")

    async def on_user_turn_completed(self, ctx: agents.JobContext, messages):
        """
        Called when the agent detects that a user turn has completed.
        `messages` contains transcripts or text messages from that user turn.
        """
        print("🔔 on_user_turn_completed triggered!")
        print(f"Context room: {ctx.room.name if ctx.room else 'No room context'}")
        print(f"Number of messages received: {len(messages)}")
    ctx.room.on("participant_connected", on_participant_connected_handler)
   
    ctx.room.on("participant_attributes_changed", on_participant_attributes_changed_handler)
    ctx.room.on("user_turn_completed",on_user_turn_completed)


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint,agent_name="Rent Orlando Scooter"))
    # agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))