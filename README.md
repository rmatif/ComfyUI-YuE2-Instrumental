# ComfyUI YuE2 Instrumental

Converts a native YuE2 ABC score into instrumental conditioning. No additional dependencies or model downloads.

Clone this repository into ComfyUI's `custom_nodes` directory and restart ComfyUI.

Connect `YuE2 Generate ABC` to `YuE2 Instrumental Score`, then connect both its `abc` and `lyrics` outputs to `YuE2 Generate Music`. Use an instrumental style prompt with no vocals. For score planning, use section-only lyrics such as `[Intro]`, `[Verse]`, `[Chorus]`, and `[Outro]`.

The node moves vocal notes into the instrumental voice, retains non-overlapping instrumental notes, and replaces the vocal melody with rests while preserving chords and timing. It accepts native YuE2 two-voice notation, not arbitrary ABC dialects. Instrumental conditioning does not guarantee that the model never produces vocal sounds.

Adapted from the YuE project's [instrumental scripts](https://github.com/multimodal-art-projection/YuE/tree/0495110587a44ed00278929a63cb14a618da8992/skills/yue2-music/instrumental), under the MIT license.
