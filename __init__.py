from comfy_api.latest import ComfyExtension, io

from .yue2_instrumental import convert_score


class YuE2InstrumentalScore(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="YuE2InstrumentalScore",
            display_name="YuE2 Instrumental Score",
            category="model/conditioning/yue2",
            description="Moves the vocal melody into the instrumental voice, preserving harmony and timing. Connect both outputs to YuE2 Generate Music.",
            inputs=[io.String.Input("abc", multiline=True)],
            outputs=[io.String.Output(display_name="abc"), io.String.Output(display_name="lyrics")],
        )

    @classmethod
    def execute(cls, abc):
        score, lyrics = convert_score(abc)
        return io.NodeOutput(score, lyrics)


class YuE2InstrumentalExtension(ComfyExtension):
    async def get_node_list(self):
        return [YuE2InstrumentalScore]


async def comfy_entrypoint():
    return YuE2InstrumentalExtension()
