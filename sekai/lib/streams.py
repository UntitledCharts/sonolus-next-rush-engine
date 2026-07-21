from sonolus.script.array import Dim
from sonolus.script.containers import VarArray
from sonolus.script.stream import Stream, StreamGroup, streams

from sekai.lib.connector import ConnectorKind, ConnectorSfxTimes, ConnectorVisualState


@streams
class Streams:
    empty_input_lanes: Stream[VarArray[float, Dim[16]]]
    connector_visual_states: StreamGroup[ConnectorVisualState, Dim[1_000_000]]
    connector_effect_kinds: StreamGroup[ConnectorKind, Dim[1_000_000]]
    connector_normal_sfx_times: StreamGroup[ConnectorSfxTimes, Dim[1_000_000]]
    connector_critical_sfx_times: StreamGroup[ConnectorSfxTimes, Dim[1_000_000]]
