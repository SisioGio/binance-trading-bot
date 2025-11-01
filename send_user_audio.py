# Send audio
import wave
import num as np

SAMPLE_RATE = 48000
NUM_CHANNELS = 1   # LiveKit expects mono
FRAME_MS = 20     # 20 ms per frame is standard in VoIP
SAMPLES_PER_FRAME = int(SAMPLE_RATE * FRAME_MS / 1000)
audio_path = r'C:\Users\Alessio\Documents\Projects\Nova Sonic Agents\orlando-rental-scooter\Recording (2).wav'
# Check compatibility
wf = wave.open(audio_path, "rb")
print("Audio file:", wf.getframerate(), "Hz,", wf.getnchannels(), "ch")
def stereo_to_mono(frames, nframes):
    stereo = np.frombuffer(frames, dtype=np.int16).reshape(-1, 2)
    mono = stereo.mean(axis=1).astype(np.int16)
    return mono.tobytes()

# Create an audio source
source = rtc.AudioSource(SAMPLE_RATE, NUM_CHANNELS)
track = rtc.LocalAudioTrack.create_audio_track("user-audio", source)
await ctx.room.local_participant.publish_track(
    track,
    rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
)
frames = wf.readframes(SAMPLES_PER_FRAME)
silence_bytes = (np.zeros(int(0.3 * SAMPLE_RATE), dtype=np.int16)).tobytes()
frames = silence_bytes + frames
# Stream the audio
while frames:
    
    if not frames:
        break

    if wf.getnchannels() == 2:
        frames = stereo_to_mono(frames, SAMPLES_PER_FRAME)
    
    expected_len = NUM_CHANNELS * SAMPLES_PER_FRAME * 2  # bytes
    if len(frames) < expected_len:
        # pad with zeros to make up a full frame
        missing = expected_len - len(frames)
        frames = frames + b"\x00" * missing
    print(f"SAMPLE_RATE: {SAMPLE_RATE} | NUM_CHANNELS: {NUM_CHANNELS} | SAMPLES_PER_CHANNEL: {SAMPLES_PER_FRAME}")
    
    audio_frame = rtc.AudioFrame(
        data=frames,
        sample_rate=SAMPLE_RATE,
        num_channels=NUM_CHANNELS,
        samples_per_channel=SAMPLES_PER_FRAME
        
    )
    await source.capture_frame(audio_frame)
    frames = wf.readframes(SAMPLES_PER_FRAME)
silence_frame = rtc.AudioFrame(silence_bytes, SAMPLE_RATE, NUM_CHANNELS, len(silence_bytes)//2)
await source.capture_frame(silence_frame)
wf.close()