import inspect

from bridge.fake_device import FakeDevice
from bridge.device import BrainBitDevice, CHANNELS

REQUIRED = ["contact", "battery", "start", "stop"]


def test_same_public_contract():
    """Мост не должен знать, кто перед ним: генератор или живой прибор."""
    for name in REQUIRED:
        assert hasattr(BrainBitDevice, name), f"нет метода {name}"
        real = inspect.signature(getattr(BrainBitDevice, name))
        fake = inspect.signature(getattr(FakeDevice, name))
        assert list(real.parameters) == list(fake.parameters), name


def test_channel_order_is_fixed():
    assert CHANNELS == ["T3", "T4", "O1", "O2"]
