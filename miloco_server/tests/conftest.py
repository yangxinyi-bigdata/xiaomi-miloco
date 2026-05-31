import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MIOT_KIT_ROOT = REPO_ROOT / "miot_kit"
if str(MIOT_KIT_ROOT) not in sys.path:
    sys.path.insert(0, str(MIOT_KIT_ROOT))

try:
    import thespian.actors  # noqa: F401
except ModuleNotFoundError:
    thespian_module = types.ModuleType("thespian")
    actors_module = types.ModuleType("thespian.actors")

    class ActorSystem:  # pylint: disable=too-few-public-methods
        pass

    class ActorAddress:  # pylint: disable=too-few-public-methods
        pass

    class ActorExitRequest:  # pylint: disable=too-few-public-methods
        pass

    class Actor:  # pylint: disable=too-few-public-methods
        pass

    actors_module.ActorSystem = ActorSystem
    actors_module.ActorAddress = ActorAddress
    actors_module.ActorExitRequest = ActorExitRequest
    actors_module.Actor = Actor
    thespian_module.actors = actors_module
    sys.modules["thespian"] = thespian_module
    sys.modules["thespian.actors"] = actors_module
